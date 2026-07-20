from XMatcher.matcher import XRDMatcher
from XMatcher.multiphase_matcher import MultiPhaseMatcher


def test_single_phase_matching_retains_valid_pairs_when_other_peaks_are_residuals():
    matcher = XRDMatcher(position_tolerance=0.15, min_matched_peaks=2, max_shift=0)
    metrics = matcher.calculate_match_metrics(
        [20.0, 30.0, 55.0], [100.0, 50.0, 20.0], [20.0, 30.0], [100.0, 50.0]
    )

    assert metrics["n_matched_peaks"] == 2
    assert metrics["score"] > 0


def test_identifies_two_phase_mixture_and_relative_contributions():
    database = {
        "xrd_database": {
            1: {"mpid": "a", "formula": "A", "elements": ["A"], "peaks": {"positions": [20, 30], "intensities": [100, 50]}},
            2: {"mpid": "b", "formula": "B", "elements": ["B"], "peaks": {"positions": [40, 50], "intensities": [100, 40]}},
            3: {"mpid": "c", "formula": "C", "elements": ["C"], "peaks": {"positions": [24, 35], "intensities": [100, 60]}},
        }
    }
    matcher = XRDMatcher(position_tolerance=0.15, min_matched_peaks=1, max_shift=0)
    result = MultiPhaseMatcher(matcher).match_pattern(
        [20, 30, 40, 50], [80, 40, 20, 8], database, max_phases=2, candidate_pool=3
    )

    best = result["results"][0]
    assert {phase["formula"] for phase in best["phases"]} == {"A", "B"}
    contributions = {phase["formula"]: phase["relative_contribution"] for phase in best["phases"]}
    assert contributions["A"] > contributions["B"]
    assert best["peak_attribution"][0]["assigned_formula"] == "A"
    assert best["peak_attribution"][2]["assigned_formula"] == "B"


def test_element_scope_allows_component_phases_with_element_subsets():
    database = {
        "xrd_database": {
            1: {"formula": "TiO2", "elements": ["Ti", "O"], "peaks": {"positions": [20, 30], "intensities": [100, 50]}},
            2: {"formula": "SiO2", "elements": ["Si", "O"], "peaks": {"positions": [40, 50], "intensities": [100, 40]}},
        }
    }
    matcher = XRDMatcher(position_tolerance=0.15, min_matched_peaks=1, max_shift=0)
    result = MultiPhaseMatcher(matcher).match_pattern(
        [20, 30, 40, 50], [80, 40, 20, 8], database,
        elements=["Ti", "O", "Si"], element_filter_mode="exact", max_phases=2,
    )
    assert {phase["formula"] for phase in result["results"][0]["phases"]} == {"TiO2", "SiO2"}


def test_deduplicates_combinations_with_zero_contribution_phases():
    database = {
        "xrd_database": {
            1: {"formula": "A", "elements": ["A"], "peaks": {"positions": [20, 30], "intensities": [100, 50]}},
            # This is deliberately identical to A.  NNLS can give it a zero
            # coefficient in a multi-phase combination, which used to create
            # a duplicate visible result for the same retained phase.
            2: {"formula": "A-alt", "elements": ["A"], "peaks": {"positions": [20, 30], "intensities": [100, 50]}},
        }
    }
    matcher = XRDMatcher(position_tolerance=0.15, min_matched_peaks=1, max_shift=0)
    result = MultiPhaseMatcher(matcher).match_pattern(
        [20, 30], [80, 40], database, max_phases=2, candidate_pool=2, top_n=10
    )

    signatures = [tuple(sorted(str(phase["entry_id"]) for phase in item["phases"])) for item in result["results"]]
    assert len(signatures) == len(set(signatures))


def test_known_entry_activates_constrained_candidate_pool():
    database = {
        "xrd_database": {
            1: {"formula": "A", "elements": ["A"], "peaks": {"positions": [20, 30], "intensities": [100, 50]}},
            2: {"formula": "B", "elements": ["B"], "peaks": {"positions": [40, 50], "intensities": [100, 40]}},
            3: {"formula": "C", "elements": ["C"], "peaks": {"positions": [24, 35], "intensities": [100, 60]}},
        }
    }
    matcher = XRDMatcher(position_tolerance=0.15, min_matched_peaks=1, max_shift=0)
    result = MultiPhaseMatcher(matcher).match_pattern(
        [20, 30, 40, 50], [80, 40, 20, 8], database,
        max_phases=2, candidate_pool=1, known_entry_ids=[2], top_n=10,
    )

    assert result["known_candidate_count"] == 1
    assert result["results"]
    assert all({phase["formula"] for phase in item["phases"]} == {"B"} for item in result["results"])


def test_all_known_phase_constraints_are_required_in_every_result():
    database = {
        "xrd_database": {
            1: {"formula": "NaCl", "elements": ["Na", "Cl"], "peaks": {"positions": [20, 30], "intensities": [100, 50]}},
            2: {"formula": "Mn2O3", "elements": ["Mn", "O"], "peaks": {"positions": [40, 50], "intensities": [100, 40]}},
            3: {"formula": "Other", "elements": ["X"], "peaks": {"positions": [24, 35], "intensities": [100, 60]}},
        }
    }
    matcher = XRDMatcher(position_tolerance=0.15, min_matched_peaks=1, max_shift=0)
    result = MultiPhaseMatcher(matcher).match_pattern(
        [20, 30, 40, 50], [80, 40, 20, 8], database,
        max_phases=2, candidate_pool=1, known_entry_ids=[1, 2],
        required_element_sets=[["Na", "Cl"], ["Mn", "O"]], top_n=10,
    )

    assert result["results"]
    for item in result["results"]:
        element_sets = {tuple(sorted(phase["elements"])) for phase in item["phases"]}
        assert ("Cl", "Na") in element_sets
        assert ("Mn", "O") in element_sets


def test_required_mpid_is_rejected_below_minimum_relative_contribution():
    database = {
        "xrd_database": {
            1: {"formula": "Major", "elements": ["A"], "peaks": {"positions": [20], "intensities": [100]}},
            2: {"formula": "Minor", "elements": ["B"], "peaks": {"positions": [30], "intensities": [100]}},
        }
    }
    matcher = XRDMatcher(position_tolerance=0.15, min_matched_peaks=1, max_shift=0)
    result = MultiPhaseMatcher(matcher).match_pattern(
        [20, 30], [100, 1], database, max_phases=2, candidate_pool=2,
        known_entry_ids=[1, 2], required_entry_ids=[1, 2], top_n=10,
    )

    assert result["results"] == []
    assert result["minimum_required_contribution_percent"] == 3.0
    assert result["constraint_error"] == "required_contribution_below_minimum"
