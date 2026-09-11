import io
import zipfile

import numpy as np
import pytest

from xmatcher_local_api import _calibration_adjustment, _calculate_cif_xrd, _detect_peaks, _parse_known_element_sets, _parse_known_formulas, _parse_known_mpids, _pdf_peaks_xlsx, _resolve_formula_entries, _resolve_known_phase_entries
from XMatcher.formula import formula_ratio_key


NACL_CIF = """data_NaCl
_symmetry_space_group_name_H-M   'F m -3 m'
_symmetry_Int_Tables_number      225
_cell_length_a                   5.6402
_cell_length_b                   5.6402
_cell_length_c                   5.6402
_cell_angle_alpha                90
_cell_angle_beta                 90
_cell_angle_gamma                90
_chemical_formula_sum            'Na1 Cl1'
loop_
  _atom_site_label
  _atom_site_type_symbol
  _atom_site_fract_x
  _atom_site_fract_y
  _atom_site_fract_z
  _atom_site_occupancy
  Na1 Na 0.00000 0.00000 0.00000 1
  Cl1 Cl 0.50000 0.50000 0.50000 1
"""


def test_detect_peaks_returns_uncapped_peak_count():
    two_theta = np.linspace(10.0, 40.0, 601)
    intensity = (
        2.0
        + 100.0 * np.exp(-0.5 * ((two_theta - 15.0) / 0.12) ** 2)
        + 80.0 * np.exp(-0.5 * ((two_theta - 25.0) / 0.12) ** 2)
        + 60.0 * np.exp(-0.5 * ((two_theta - 35.0) / 0.12) ** 2)
    )
    result = _detect_peaks({
        "two_theta": two_theta.tolist(),
        "intensity": intensity.tolist(),
        "params": {"min_peak_height": 3, "min_peak_prominence": 2, "smooth_window": 7},
    })

    assert result["status"] == "ok"
    assert result["detected_peak_count"] == 3
    assert len(result["detected_peaks"]) == 3
    assert result["reliable_detected_peak_count"] == 3
    assert len(result["reliable_detected_peaks"]) == 3


def test_calibration_penalty_scales_with_shift_excess():
    no_penalty = _calibration_adjustment(50, 0.30, 0.50)
    severe_penalty = _calibration_adjustment(50, 0.50, 0.50)

    assert no_penalty["calibration_penalty"] == 0
    assert no_penalty["calibration_adjusted_score"] == 50
    assert severe_penalty["calibration_penalty"] == 10
    assert severe_penalty["calibration_adjusted_score"] == 40


def test_calculate_cif_xrd_parses_cif_from_string():
    pytest.importorskip("pymatgen")

    result = _calculate_cif_xrd(
        {
            "cifs": [{"name": "nacl.cif", "content": NACL_CIF, "weight": 100}],
            "two_theta_range": [10, 80],
            "min_intensity": 0.1,
            "fwhm": 0.12,
            "wavelength": "CuKa",
            "normalize": True,
        }
    )

    assert result["phases"][0]["name"] == "nacl.cif"
    assert result["phases"][0]["peaks"]["positions"]
    assert result["mixture"]["two_theta"]
    assert result["mixture"]["intensity"]


def test_pdf_peak_excel_contains_a_sheet_and_peak_columns_for_each_phase():
    workbook = _pdf_peaks_xlsx(
        {
            "phases": [
                {
                    "name": "NaCl.cif",
                    "formula": "NaCl",
                    "weight": 100,
                    "peaks": {
                        "positions": [31.7],
                        "intensities": [100.0],
                        "hkls": [[{"hkl": [1, 1, 1], "multiplicity": 8}]],
                        "d_spacings": [2.82],
                    },
                }
            ]
        }
    )

    with zipfile.ZipFile(io.BytesIO(workbook)) as archive:
        assert "xl/worksheets/sheet1.xml" in archive.namelist()
        sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")

    assert 'name="NaCl"' in workbook_xml
    assert "2theta (degree)" in sheet
    assert "Relative intensity (%)" in sheet
    assert "(1 1 1) ×8" in sheet


def test_known_phase_constraints_resolve_exact_elements_and_mpid():
    database = {
        "xrd_database": {
            1: {"mpid": "mp-NaCl", "elements": ["Na", "Cl"], "peaks": {"positions": [], "intensities": []}},
            2: {"mpid": "mp-NaClO", "elements": ["Na", "Cl", "O"], "peaks": {"positions": [], "intensities": []}},
        }
    }
    element_sets = _parse_known_element_sets("Na, Cl\nO, Na, Cl")
    mpids = _parse_known_mpids("MP-NACL")
    entry_ids, status = _resolve_known_phase_entries(database, element_sets, mpids)

    assert element_sets == [("Cl", "Na"), ("Cl", "Na", "O")]
    assert mpids == ["mp-nacl"]
    assert entry_ids == [1, 2]
    assert status["exact_element_match_counts"] == {"Cl,Na": 1, "Cl,Na,O": 1}


def test_formula_ratio_constraint_resolves_only_matching_stoichiometry():
    database = {
        "xrd_database": {
            1: {"formula": "Fe2O3", "peaks": {"positions": [], "intensities": []}},
            2: {"formula": "Fe4O6", "peaks": {"positions": [], "intensities": []}},
            3: {"formula": "FeO", "peaks": {"positions": [], "intensities": []}},
        }
    }
    ids, status = _resolve_formula_entries(database, ["O3Fe2"])

    assert formula_ratio_key("Ca(OH)2") == (("Ca", 1), ("H", 2), ("O", 2))
    assert ids == [1, 2]
    assert status["formula_ratio_match_counts"] == {"O3Fe2": 2}


def test_empty_formula_values_create_no_formula_constraint():
    assert _parse_known_formulas(None) == []


def test_known_phase_constraints_resolve_mpid_when_database_stores_cif_suffix():
    database = {
        "xrd_database": {
            1: {"mpid": "mp-22862.cif", "elements": ["Na", "Cl"], "peaks": {"positions": [], "intensities": []}},
        }
    }

    entry_ids, status = _resolve_known_phase_entries(database, [], _parse_known_mpids("mp-22862"))

    assert entry_ids == [1]
    assert status["mpid_entry_ids"] == [1]
