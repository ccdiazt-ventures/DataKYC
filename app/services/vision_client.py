"""HTTP client for Vision AI models on DGX Spark.

Two models available:
- Granite Vision 4.1 4B (Spark :8004) — primary OCR extraction engine
- Gemma 4 26B (Spark :8003) — cross-validation and reasoning
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from httpx import HTTPStatusError, TimeoutException

from app.config import get_settings
from app.core.constants import DocumentType

settings = get_settings()

# ---------------------------------------------------------------------------
# Structured prompts per document type — tuned for Mexican documents in Spanish
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPTS: dict[DocumentType, str] = {
    DocumentType.INE_FRONT: """\
Eres un sistema de OCR especializado en documentos de identidad mexicanos.
Analiza la imagen del FRENTE de una INE (credencial para votar) mexicana y extrae TODOS los datos visibles.

Devuelve ÚNICAMENTE un objeto JSON con esta estructura exacta:
{
  "nombre": "",
  "apellido_paterno": "",
  "apellido_materno": "",
  "curp": "",
  "clave_elector": "",
  "seccion": "",
  "vigencia": "",
  "domicilio": {
    "calle": "",
    "numero": "",
    "colonia": "",
    "codigo_postal": "",
    "municipio": "",
    "estado": ""
  },
  "fecha_nacimiento": "",
  "sexo": "",
  "emision": "",
  "anio_registro": ""
}

REGLAS:
- Si un campo no es visible, déjalo como string vacío ""
- CURP: 18 caracteres alfanuméricos
- Clave de elector: formato de 18 caracteres (ej. CSLRDS97111719H700)
- Vigencia: formato "2024-2034" o similar
- NO inventes datos — solo extrae lo visible en la imagen
- Responde SOLO con el JSON, sin texto adicional""",

    DocumentType.INE_BACK: """\
Eres un sistema de OCR especializado en documentos de identidad mexicanos.
Analiza la imagen del REVERSO de una INE (credencial para votar) mexicana y extrae TODOS los datos visibles.

Devuelve ÚNICAMENTE un objeto JSON con esta estructura exacta:
{
  "cic": "",
  "mrz_linea1": "",
  "mrz_linea2": "",
  "mrz_linea3": "",
  "anio_registro": "",
  "localidad": ""
}

REGLAS:
- CIC: código de identificación de credencial (números)
- MRZ: las líneas OCR de la parte inferior (pueden ser 2 o 3)
- Si un campo no es visible, déjalo como string vacío ""
- NO inventes datos
- Responde SOLO con el JSON, sin texto adicional""",

    DocumentType.CURP: """\
Eres un sistema de OCR especializado en documentos oficiales mexicanos.
Analiza la imagen de una CURP (Clave Única de Registro de Población) mexicana y extrae TODOS los datos visibles.

Devuelve ÚNICAMENTE un objeto JSON con esta estructura exacta:
{
  "curp": "",
  "nombre": "",
  "apellido_paterno": "",
  "apellido_materno": "",
  "fecha_nacimiento": "",
  "sexo": "",
  "entidad_nacimiento": "",
  "nacionalidad": "",
  "documento_probatorio": ""
}

REGLAS:
- CURP: 18 caracteres alfanuméricos
- Si un campo no es visible, déjalo como string vacío ""
- NO inventes datos
- Responde SOLO con el JSON, sin texto adicional""",

    DocumentType.PASSPORT: """\
Eres un sistema de OCR especializado en documentos de identidad.
Analiza la imagen de un PASAPORTE mexicano y extrae TODOS los datos visibles.

Devuelve ÚNICAMENTE un objeto JSON con esta estructura exacta:
{
  "numero_pasaporte": "",
  "nombre": "",
  "apellidos": "",
  "nacionalidad": "",
  "fecha_nacimiento": "",
  "sexo": "",
  "fecha_emision": "",
  "fecha_expiracion": "",
  "autoridad_emisora": "",
  "mrz_linea1": "",
  "mrz_linea2": ""
}

REGLAS:
- Número de pasaporte: alfanumérico, usualmente en la esquina superior derecha
- MRZ: las 2 líneas de la zona de lectura mecánica en la parte inferior
- Si un campo no es visible, déjalo como string vacío ""
- NO inventes datos
- Responde SOLO con el JSON, sin texto adicional""",

    DocumentType.RFC: """\
Eres un sistema de OCR especializado en documentos fiscales mexicanos.
Analiza la imagen de una Cédula de Identificación Fiscal (RFC) mexicana y extrae TODOS los datos visibles.

Devuelve ÚNICAMENTE un objeto JSON con esta estructura exacta:
{
  "rfc": "",
  "nombre": "",
  "apellido_paterno": "",
  "apellido_materno": "",
  "fecha_emision": "",
  "regimen_fiscal": ""
}

REGLAS:
- RFC: 13 caracteres para personas físicas, 12 para morales
- Régimen fiscal: puede ser múltiple, separa con comas
- Si un campo no es visible, déjalo como string vacío ""
- NO inventes datos
- Responde SOLO con el JSON, sin texto adicional""",

    DocumentType.COMPROBANTE_DOMICILIO: """\
Eres un sistema de OCR especializado en documentos mexicanos.
Analiza la imagen de un COMPROBANTE DE DOMICILIO mexicano (recibo de CFE, agua, teléfono, predial) y extrae TODOS los datos visibles.

Devuelve ÚNICAMENTE un objeto JSON con esta estructura exacta:
{
  "nombre": "",
  "direccion_completa": "",
  "codigo_postal": "",
  "municipio": "",
  "estado": "",
  "tipo_comprobante": "",
  "fecha_emision": "",
  "emisor": ""
}

REGLAS:
- tipo_comprobante: "CFE", "AGUA", "TELEFONO", "PREDIAL", "GAS", "OTRO"
- Si un campo no es visible, déjalo como string vacío ""
- NO inventes datos
- Responde SOLO con el JSON, sin texto adicional""",

    DocumentType.ESTADO_CUENTA: """\
Eres un sistema de OCR especializado en documentos bancarios mexicanos.
Analiza la imagen de un ESTADO DE CUENTA BANCARIO mexicano y extrae TODOS los datos visibles.

Devuelve ÚNICAMENTE un objeto JSON con esta estructura exacta:
{
  "banco": "",
  "nombre_titular": "",
  "numero_cuenta": "",
  "clabe": "",
  "periodo": "",
  "saldo_promedio": "",
  "tipo_cuenta": ""
}

REGLAS:
- CLABE: 18 dígitos (si es visible)
- Número de cuenta: puede estar parcialmente oculto (ej. ****1234)
- Si un campo no es visible, déjalo como string vacío ""
- NO inventes datos
- Responde SOLO con el JSON, sin texto adicional""",
}


class VisionClient:
    """HTTP client for Granite Vision (OCR) and Gemma4 (validation) on DGX Spark."""

    def __init__(self) -> None:
        self._granite_url = settings.granite_vision_url
        self._gemma4_url = settings.gemma4_url
        self._timeout = settings.vision_timeout_seconds

    async def extract_document(
        self,
        image_base64: str,
        document_type: DocumentType,
    ) -> dict[str, Any]:
        """Extract structured data from a document image using Granite Vision 4.1.

        Returns a dict with extracted fields and per-field confidence.
        """
        prompt = _EXTRACTION_PROMPTS.get(document_type)
        if prompt is None:
            return {
                "error": f"Unsupported document type: {document_type}",
                "fields": {},
                "confidence_scores": {},
                "overall_confidence": 0.0,
            }

        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._granite_url}/chat/completions",
                    json={
                        "model": "granite-vision:4b",
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/jpeg;base64,{image_base64}"
                                        },
                                    },
                                ],
                            }
                        ],
                        "temperature": 0.1,
                        "max_tokens": 2048,
                    },
                )
                response.raise_for_status()

        except TimeoutException:
            elapsed = int((time.time() - start) * 1000)
            return {
                "error": "Vision model timeout",
                "fields": {},
                "confidence_scores": {},
                "overall_confidence": 0.0,
                "processing_time_ms": elapsed,
            }
        except HTTPStatusError as exc:
            elapsed = int((time.time() - start) * 1000)
            return {
                "error": f"Vision model error: HTTP {exc.response.status_code}",
                "fields": {},
                "confidence_scores": {},
                "overall_confidence": 0.0,
                "processing_time_ms": elapsed,
            }

        elapsed = int((time.time() - start) * 1000)

        # Parse the model response
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")

        # Extract JSON from response (handle potential markdown wrapping)
        fields = self._parse_json_response(content)
        overall_confidence = self._estimate_confidence(fields, document_type)

        # Per-field confidence estimates based on field presence
        expected_fields = {
            DocumentType.INE_FRONT: 16,
            DocumentType.INE_BACK: 6,
            DocumentType.CURP: 9,
            DocumentType.PASSPORT: 11,
            DocumentType.RFC: 6,
            DocumentType.COMPROBANTE_DOMICILIO: 8,
            DocumentType.ESTADO_CUENTA: 7,
        }
        total_expected = expected_fields.get(document_type, 8)
        filled = sum(1 for v in fields.values() if v and (isinstance(v, str) and v.strip()))
        confidence_scores: dict[str, float] = {}
        for key, val in fields.items():
            if isinstance(val, str):
                confidence_scores[key] = 1.0 if val.strip() else 0.0
            elif isinstance(val, dict):
                inner_filled = sum(1 for v in val.values() if isinstance(v, str) and v.strip())
                inner_total = max(len(val), 1)
                confidence_scores[key] = inner_filled / inner_total
            else:
                confidence_scores[key] = 0.0

        return {
            "fields": fields,
            "confidence_scores": confidence_scores,
            "overall_confidence": overall_confidence,
            "processing_time_ms": elapsed,
            "fields_filled": filled,
            "fields_total": total_expected,
        }

    async def cross_validate_ine(
        self,
        front_data: dict | None = None,
        back_data: dict | None = None,
        front_image_b64: str | None = None,
        back_image_b64: str | None = None,
        pre_extracted: dict | None = None,
    ) -> dict[str, Any]:
        """Cross-validate INE extracted data using Gemma4 26B for reasoning.

        This checks consistency: does CURP match name? Is clave_elector valid format?
        Are dates logical? Does vigencia make sense for age?
        """
        # Build context for the validation prompt
        data_text = ""
        if pre_extracted:
            data_text = json.dumps(pre_extracted, indent=2, ensure_ascii=False)
        else:
            if front_data:
                data_text += f"FRENTE: {json.dumps(front_data, indent=2, ensure_ascii=False)}\n"
            if back_data:
                data_text += f"REVERSO: {json.dumps(back_data, indent=2, ensure_ascii=False)}\n"

        prompt = f"""\
Eres un validador experto de documentos de identidad mexicanos.
Revisa los siguientes datos extraídos de una INE mexicana e identifica inconsistencias.

DATOS EXTRAÍDOS:
{data_text}

Verifica:
1. Que el CURP coincida con nombre + fecha de nacimiento + sexo (primeros 16 caracteres)
2. Que la clave de elector tenga formato válido (18 caracteres)
3. Que las fechas sean consistentes (fecha_nacimiento < emision < vigencia)
4. Que la vigencia no haya expirado (o esté dentro de un rango razonable)
5. Que el estado/municipio existan en México
6. Que el domicilio tenga estructura válida

Devuelve ÚNICAMENTE un objeto JSON:
{{
  "is_consistent": true/false,
  "overall_confidence": 0.0-1.0,
  "discrepancies": [
    {{"field": "nombre_campo", "extracted_value": "valor", "expected": "valor_esperado", "issue": "descripción", "severity": "high/medium/low"}}
  ],
  "validated_fields": {{}},
  "recommendations": []
}}

Donde validated_fields contiene los campos corregidos (si aplica) y recommendations son sugerencias.
Responde SOLO con el JSON, sin texto adicional."""

        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._gemma4_url}/chat/completions",
                    json={
                        "model": "gemma4:26b",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                        "max_tokens": 2048,
                    },
                )
                response.raise_for_status()

        except (TimeoutException, HTTPStatusError) as exc:
            elapsed = int((time.time() - start) * 1000)
            return {
                "is_consistent": False,
                "overall_confidence": 0.0,
                "discrepancies": [],
                "validated_fields": {},
                "recommendations": [],
                "error": str(exc),
                "processing_time_ms": elapsed,
            }

        elapsed = int((time.time() - start) * 1000)
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        result = self._parse_json_response(content)
        result["processing_time_ms"] = elapsed
        return result

    def _parse_json_response(self, content: str) -> dict:
        """Parse JSON from model response, handling markdown code fences."""
        content = content.strip()

        # Remove markdown code fences if present
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first and last lines (fences)
            if len(lines) >= 3:
                lines = lines[1:-1]
            content = "\n".join(lines)

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            start_idx = content.find("{")
            end_idx = content.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                try:
                    return json.loads(content[start_idx:end_idx + 1])
                except json.JSONDecodeError:
                    pass
            return {"raw_response": content, "parse_error": True}

    @staticmethod
    def _estimate_confidence(fields: dict, doc_type: DocumentType) -> float:
        """Estimate overall extraction confidence based on filled fields."""
        if not fields:
            return 0.0

        def _count_filled(obj: dict, prefix: str = "") -> tuple[int, int]:
            filled = 0
            total = 0
            for key, val in obj.items():
                if isinstance(val, dict):
                    f, t = _count_filled(val, f"{prefix}{key}.")
                    filled += f
                    total += t
                else:
                    total += 1
                    if val and (isinstance(val, str) and val.strip()):
                        filled += 1
            return filled, total

        filled, total = _count_filled(fields)
        if total == 0:
            return 0.0
        return filled / total


# Singleton
vision_client = VisionClient()
