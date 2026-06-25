import math

import pytest

from XMatcher.matcher import XRDMatcher


def _database():
    return {
        "xrd_database": {
            1: {
                "mpid": "mp-1",
                "formula": "BTc",
                "elements": ["B", "Tc"],
                "peaks": {
                    "positions": [20.0, 30.0, 45.0],
                    "intensities": [100.0, 60.0, 30.0],
                },
            },
            2: {
                "mpid": "mp-2",
                "formula": "TiO2",
                "elements": ["Ti", "O"],
                "peaks": {
                    "positions": [25.0, 38.0, 48.0],
                    "intensities": [100.0, 40.0, 20.0],
                },
            },
            3: {
                "mpid": "mp-3",
                "formula": "BTcO",
                "elements": ["B", "Tc", "O"],
                "peaks": {
                    "positions": [20.1, 30.1, 45.1],
                    "intensities": [100.0, 55.0, 35.0],
                },
            },
        }
    }


def test_element_filter_is_case_tolerant():
    matcher = XRDMatcher()
    database = _database()

    assert matcher.filter_by_elements(database, ["b", "tc"], mode="exact") == [1]
    assert matcher.filter_by_elements(database, ["b", "tc"], mode="contains") == [1, 3]


def test_shift_estimate_prefers_low_error_candidate():
    matcher = XRDMatcher(position_tolerance=0.2, max_shift=0.5, shift_step=0.05, min_matched_peaks=2)

    metrics = matcher.calculate_match_metrics(
        exp_positions=[20.13, 30.13, 45.13],
        exp_intensities=[100.0, 55.0, 35.0],
        db_positions=[20.0, 30.0, 45.0],
        db_intensities=[100.0, 60.0, 30.0],
    )

    assert metrics["n_matched_peaks"] == 3
    assert math.isclose(metrics["estimated_shift"], 0.13, abs_tol=1e-9)
    assert metrics["mean_abs_error"] == pytest.approx(0.0, abs=1e-9)


def test_intensity_mismatch_does_not_overwhelm_position_match():
    matcher = XRDMatcher(position_tolerance=0.2, min_matched_peaks=2)

    metrics = matcher.calculate_match_metrics(
        exp_positions=[20.0, 30.0, 45.0],
        exp_intensities=[5.0, 100.0, 10.0],
        db_positions=[20.0, 30.0, 45.0],
        db_intensities=[100.0, 60.0, 30.0],
    )

    assert metrics["n_matched_peaks"] == 3
    assert metrics["score"] > 50.0


def test_retrieve_ranks_true_candidate_first_with_extra_experimental_peak():
    matcher = XRDMatcher(position_tolerance=0.25, max_shift=0.3, min_matched_peaks=2)

    results = matcher.match_pattern(
        exp_positions=[20.05, 30.05, 45.05, 72.0],
        exp_intensities=[100.0, 55.0, 30.0, 20.0],
        database=_database(),
        elements=["B", "Tc"],
        element_filter_mode="exact",
        top_n=2,
    )

    assert results[0]["formula"] == "BTc"
    assert results[0]["n_matched_peaks"] == 3
