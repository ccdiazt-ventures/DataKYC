"""Tests for the extraction API."""

import pytest
from app.services.form_filler import fill_form
from app.core.constants import FormTemplate


def test_fill_sofom_standard(sample_ine_front_data):
    result = fill_form(sample_ine_front_data, FormTemplate.SOFOM_STANDARD)
    assert result["form_template"] == "sofom_standard"
    assert len(result["filled_fields"]) > 0
    # Should have filled nombre, apellido_paterno, curp at minimum
    filled_names = {f["field_name"] for f in result["filled_fields"]}
    assert "curp" in filled_names
    assert "nombre_completo" in filled_names
    assert len(result["missing_fields"]) > 0  # Some fields need manual input


def test_fill_cnbv_basic(sample_ine_front_data):
    result = fill_form(sample_ine_front_data, FormTemplate.CNBV_BASIC)
    assert result["form_template"] == "cnbv_basic"
    filled_names = {f["field_name"] for f in result["filled_fields"]}
    assert "curp" in filled_names
    assert "nombre_solicitante" in filled_names
