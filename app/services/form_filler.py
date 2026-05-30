"""Form filler — maps extracted document data to KYC form templates."""

from __future__ import annotations

from app.core.constants import FormTemplate

# ---------------------------------------------------------------------------
# Field mappings: form_template -> { form_field_name: (label, [extraction_source_keys]) }
# ---------------------------------------------------------------------------

_SOFOM_STANDARD_MAPPING: dict[str, tuple[str, list[str]]] = {
    "primer_nombre": ("Primer Nombre", ["nombre"]),
    "segundo_nombre": ("Segundo Nombre", []),
    "apellido_paterno": ("Apellido Paterno", ["apellido_paterno"]),
    "apellido_materno": ("Apellido Materno", ["apellido_materno"]),
    "nombre_completo": ("Nombre Completo", ["nombre", "apellido_paterno", "apellido_materno"]),
    "curp": ("CURP", ["curp"]),
    "rfc": ("RFC", ["rfc"]),
    "fecha_nacimiento": ("Fecha de Nacimiento", ["fecha_nacimiento"]),
    "sexo": ("Sexo", ["sexo"]),
    "nacionalidad": ("Nacionalidad", ["nacionalidad"]),
    "estado_civil": ("Estado Civil", []),
    "clave_elector": ("Clave de Elector", ["clave_elector"]),
    "numero_ine": ("Número INE", ["cic"]),
    "vigencia_ine": ("Vigencia INE", ["vigencia"]),
    "calle": ("Calle", ["domicilio.calle", "calle"]),
    "numero_exterior": ("Número Exterior", ["domicilio.numero", "numero"]),
    "numero_interior": ("Número Interior", []),
    "colonia": ("Colonia", ["domicilio.colonia", "colonia"]),
    "codigo_postal": ("Código Postal", ["domicilio.codigo_postal", "codigo_postal", "cp"]),
    "municipio": ("Municipio/Delegación", ["domicilio.municipio", "municipio"]),
    "estado": ("Estado", ["domicilio.estado", "estado", "entidad_nacimiento"]),
    "pais": ("País", ["nacionalidad"]),
    "telefono": ("Teléfono", []),
    "email": ("Correo Electrónico", []),
    "ocupacion": ("Ocupación/Profesión", []),
    "tipo_identificacion": ("Tipo de Identificación", []),
    "numero_pasaporte": ("Número de Pasaporte", ["numero_pasaporte"]),
    "fecha_emision_pasaporte": ("Fecha Emisión Pasaporte", ["fecha_emision"]),
    "fecha_expiracion_pasaporte": ("Fecha Expiración Pasaporte", ["fecha_expiracion"]),
    "banco": ("Banco", ["banco"]),
    "numero_cuenta": ("Número de Cuenta", ["numero_cuenta"]),
    "clabe": ("CLABE", ["clabe"]),
}

_CNBV_BASIC_MAPPING: dict[str, tuple[str, list[str]]] = {
    "nombre_solicitante": ("Nombre del Solicitante", ["nombre", "apellido_paterno", "apellido_materno"]),
    "curp": ("CURP", ["curp"]),
    "rfc": ("RFC", ["rfc"]),
    "fecha_nacimiento": ("Fecha de Nacimiento", ["fecha_nacimiento"]),
    "sexo": ("Sexo", ["sexo"]),
    "nacionalidad": ("Nacionalidad", ["nacionalidad"]),
    "tipo_identificacion": ("Tipo de Identificación", []),
    "numero_identificacion": ("Número de Identificación", ["clave_elector", "cic", "numero_pasaporte"]),
    "domicilio_completo": ("Domicilio Completo", ["direccion_completa"]),
    "codigo_postal": ("Código Postal", ["domicilio.codigo_postal", "codigo_postal", "cp"]),
    "pais_residencia": ("País de Residencia", []),
    "telefono": ("Teléfono", []),
    "email": ("Correo Electrónico", []),
    "actividad_economica": ("Actividad Económica", []),
    "ingreso_mensual": ("Ingreso Mensual", []),
}

_CNBV_ADVANCED_MAPPING: dict[str, tuple[str, list[str]]] = {
    **_CNBV_BASIC_MAPPING,
    "apellido_paterno": ("Apellido Paterno", ["apellido_paterno"]),
    "apellido_materno": ("Apellido Materno", ["apellido_materno"]),
    "calle": ("Calle", ["domicilio.calle", "calle"]),
    "numero_exterior": ("Número Exterior", ["domicilio.numero", "numero"]),
    "colonia": ("Colonia", ["domicilio.colonia", "colonia"]),
    "municipio": ("Municipio/Delegación", ["domicilio.municipio", "municipio"]),
    "estado": ("Estado", ["domicilio.estado", "estado"]),
    "empleador": ("Empleador/Negocio", []),
    "antiguedad_laboral": ("Antigüedad Laboral", []),
    "referencia_personal": ("Referencia Personal", []),
}

FORM_MAPPINGS: dict[FormTemplate, dict] = {
    FormTemplate.SOFOM_STANDARD: _SOFOM_STANDARD_MAPPING,
    FormTemplate.CNBV_BASIC: _CNBV_BASIC_MAPPING,
    FormTemplate.CNBV_ADVANCED: _CNBV_ADVANCED_MAPPING,
}


def _get_nested_value(data: dict, key_path: str) -> str | None:
    """Get a value using dot-notation path (e.g., 'domicilio.calle')."""
    parts = key_path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return str(current) if current else None


def fill_form(
    extracted_data: dict,
    form_template: FormTemplate,
) -> dict:
    """Fill a KYC form template with extracted document data.

    Returns filled fields, missing fields, and warnings.
    """
    mapping = FORM_MAPPINGS.get(form_template, _SOFOM_STANDARD_MAPPING)

    filled_fields = []
    missing_fields = []
    warnings = []

    for field_name, (label, source_keys) in mapping.items():
        value = None
        matched_source = None

        for key in source_keys:
            value = _get_nested_value(extracted_data, key)
            if value:
                matched_source = key
                break

        if value:
            # Check if this field is auto-composed (multiple sources)
            confidence = 0.9 if "." not in (matched_source or "") else 0.85
            filled_fields.append({
                "field_name": field_name,
                "field_label": label,
                "value": value,
                "source": matched_source or "extracted",
                "confidence": confidence,
            })
        elif source_keys:
            missing_fields.append(f"{label} ({field_name})")
        else:
            missing_fields.append(f"{label} ({field_name}) — requiere entrada manual")

    if len(missing_fields) > 10:
        warnings.append(
            f"El {len(missing_fields)}/{len(mapping)} campos requieren datos adicionales. "
            "Considere extraer documentos complementarios (comprobante de domicilio, RFC, estado de cuenta)."
        )

    return {
        "form_template": form_template.value,
        "filled_fields": filled_fields,
        "missing_fields": missing_fields,
        "warnings": warnings,
    }
