import pytest

from xmatcher_local_api import _calculate_cif_xrd


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
