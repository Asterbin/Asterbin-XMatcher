import io
import zipfile

import pytest

from xmatcher_local_api import _calculate_cif_xrd, _parse_known_element_sets, _parse_known_mpids, _pdf_peaks_xlsx, _resolve_known_phase_entries


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


def test_known_phase_constraints_resolve_mpid_when_database_stores_cif_suffix():
    database = {
        "xrd_database": {
            1: {"mpid": "mp-22862.cif", "elements": ["Na", "Cl"], "peaks": {"positions": [], "intensities": []}},
        }
    }

    entry_ids, status = _resolve_known_phase_entries(database, [], _parse_known_mpids("mp-22862"))

    assert entry_ids == [1]
    assert status["mpid_entry_ids"] == [1]
