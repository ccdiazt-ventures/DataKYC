"""Test fixtures and configuration."""

import pytest
from app.config import get_settings


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def sample_ine_front_data():
    return {
        "nombre": "CESAR CARLOS",
        "apellido_paterno": "DIAZ",
        "apellido_materno": "TORREJON",
        "curp": "DITC880211HDFZRS09",
        "clave_elector": "DITCDZ88021109H700",
        "seccion": "1234",
        "vigencia": "2024-2034",
        "domicilio": {
            "calle": "INSURGENTES",
            "numero": "123",
            "colonia": "CENTRO",
            "codigo_postal": "06600",
            "municipio": "CUAUHTEMOC",
            "estado": "CIUDAD DE MEXICO",
        },
        "fecha_nacimiento": "11/02/1988",
        "sexo": "H",
        "emision": "2024",
    }
