from io import BytesIO

import pandas as pd
import pytest

from utils import (
    MAX_UPLOAD_BYTES,
    DataValidationError,
    calc_hresid,
    calc_ifm,
    get_mechanism_group,
    read_excel_file,
    validate_excel_upload,
    validate_normalized_columns,
)


def test_calc_ifm_from_components():
    ifm, pi_r, pi_c = calc_ifm(1000, 0.5, 2000, 0.5)
    assert (ifm, pi_r, pi_c) == (0.5, 500.0, 1000.0)


def test_calc_ifm_rejects_non_positive_design_capacity():
    with pytest.raises(ValueError):
        calc_ifm(100, 0)


def test_calc_hresid_rejects_invalid_spectrum():
    with pytest.raises(ValueError):
        calc_hresid(1, 100, 10, 0)


def test_mechanism_group_uses_matrix_and_rejects_unknown_classes():
    assert get_mechanism_group("T6 (test)", "L2 (test)") == "M6"
    with pytest.raises(ValueError):
        get_mechanism_group("T99", "L2")


def test_upload_validation_rejects_wrong_extension_empty_and_oversized_files():
    with pytest.raises(DataValidationError):
        validate_excel_upload("fleet.csv", b"data")
    with pytest.raises(DataValidationError):
        validate_excel_upload("fleet.xlsx", b"")
    with pytest.raises(DataValidationError):
        validate_excel_upload("fleet.xlsx", b"x" * (MAX_UPLOAD_BYTES + 1))


def test_upload_validation_rejects_fake_xlsx():
    with pytest.raises(DataValidationError):
        validate_excel_upload("fleet.xlsx", b"not a zip archive")


def test_read_excel_uses_ponts_sheet_and_expected_header_row():
    buffer = BytesIO()
    data = pd.DataFrame(
        {
            "PAYS": ["FRANCE"],
            "Site": ["DEMO"],
            "Pont": ["Pont 1"],
            "Age": [10],
            "Evaluation Spéciale O/N": ["N"],
        }
    )
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        data.to_excel(writer, sheet_name="Ponts", index=False, startrow=9)

    file_bytes = buffer.getvalue()
    validate_excel_upload("fleet.xlsx", file_bytes)
    parsed = read_excel_file(BytesIO(file_bytes))

    assert list(parsed.columns) == list(data.columns)
    assert parsed.iloc[0]["Pont"] == "Pont 1"


def test_normalized_schema_reports_missing_columns():
    with pytest.raises(DataValidationError, match="age, evs_statut"):
        validate_normalized_columns(
            pd.DataFrame(columns=["pays", "site", "pont"])
        )
