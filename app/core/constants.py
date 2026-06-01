"""Core constants for DataKYC."""

from enum import StrEnum


class PlanTier(StrEnum):
    FREE = "FREE"
    BASIC = "BASIC"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"


class OrganizationRole(StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    USER = "USER"


class OrganizationStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class DocumentType(StrEnum):
    INE_FRONT = "INE_FRONT"
    INE_BACK = "INE_BACK"
    CURP = "CURP"
    PASSPORT = "PASSPORT"
    RFC = "RFC"
    COMPROBANTE_DOMICILIO = "COMPROBANTE_DOMICILIO"
    ESTADO_CUENTA = "ESTADO_CUENTA"


class ExtractionStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class FormTemplate(StrEnum):
    CNBV_BASIC = "cnbv_basic"
    CNBV_ADVANCED = "cnbv_advanced"
    SOFOM_STANDARD = "sofom_standard"


# Fields expected per document type (used for validation & prompts)
DOCUMENT_FIELDS: dict[DocumentType, list[str]] = {
    DocumentType.INE_FRONT: [
        "nombre", "apellido_paterno", "apellido_materno", "curp",
        "clave_elector", "seccion", "vigencia",
        "domicilio_calle", "domicilio_numero", "domicilio_colonia",
        "domicilio_cp", "domicilio_municipio", "domicilio_estado",
        "fecha_nacimiento", "sexo", "emision",
    ],
    DocumentType.INE_BACK: [
        "cic", "mrz_linea1", "mrz_linea2", "mrz_linea3",
        "anio_registro", "localidad",
    ],
    DocumentType.CURP: [
        "curp", "nombre", "apellido_paterno", "apellido_materno",
        "fecha_nacimiento", "sexo", "entidad_nacimiento",
        "nacionalidad", "documento_probatorio",
    ],
    DocumentType.PASSPORT: [
        "numero_pasaporte", "nombre", "apellidos", "nacionalidad",
        "fecha_nacimiento", "sexo", "fecha_emision", "fecha_expiracion",
        "autoridad_emisora", "mrz_linea1", "mrz_linea2",
    ],
    DocumentType.RFC: [
        "rfc", "nombre", "apellido_paterno", "apellido_materno",
        "fecha_emision", "regimen_fiscal",
    ],
    DocumentType.COMPROBANTE_DOMICILIO: [
        "nombre", "direccion_completa", "cp", "municipio", "estado",
        "tipo_comprobante", "fecha_emision", "emisor",
    ],
    DocumentType.ESTADO_CUENTA: [
        "banco", "nombre_titular", "numero_cuenta", "clabe",
        "periodo", "saldo_promedio", "tipo_cuenta",
    ],
}
