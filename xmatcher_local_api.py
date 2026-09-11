#!/usr/bin/env python
"""Local HTTP API used by XMatcher_Local_UI.html.

Run:
    python xmatcher_local_api.py --database MP500_xrd_database.pkl --host 127.0.0.1 --port 8765
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import math
import re
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from XMatcher.calibration import calibrate_two_theta
from XMatcher.database import DatabaseBuilder, normalize_database_package
from XMatcher.formula import formula_ratio_key
from XMatcher.matcher import XRDMatcher
from XMatcher.multiphase_matcher import MultiPhaseMatcher
from XMatcher.peak_detector import PeakDetector

logger = logging.getLogger("xmatcher_local_api")

DATABASE: Optional[Dict] = None
DATABASE_PATH: Optional[Path] = None


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Dict) -> None:
    body = json.dumps(_json_ready(payload), ensure_ascii=False, allow_nan=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


def _xlsx_response(handler: BaseHTTPRequestHandler, filename: str, workbook: bytes) -> None:
    """Return an XLSX attachment without adding an Excel dependency."""
    handler.send_response(200)
    handler.send_header(
        "Content-Type",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    handler.send_header("Content-Length", str(len(workbook)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(workbook)


def _json_ready(value):
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, np.ndarray):
        return _json_ready(value.tolist())
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _read_json(handler: BaseHTTPRequestHandler) -> Dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


def _as_float_array(values: Sequence) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    return arr


def _prepare_arrays(two_theta: Sequence, intensity: Sequence) -> Tuple[np.ndarray, np.ndarray]:
    x = np.asarray(two_theta, dtype=float)
    y = np.asarray(intensity, dtype=float)
    if x.size != y.size:
        raise ValueError("two_theta and intensity must have the same length")
    valid = np.isfinite(x) & np.isfinite(y)
    x = x[valid]
    y = y[valid]
    y[y < 0] = 0
    if x.size < 3:
        raise ValueError("At least 3 valid XRD points are required")
    order = np.argsort(x)
    return x[order], y[order]


def _calibration_adjustment(raw_score: float, estimated_shift: float, max_shift: float,
                            warning_fraction: float = 0.60,
                            max_penalty_fraction: float = 0.20) -> Dict:
    """Return a continuous, bounded calibration penalty for ranking candidates."""
    limit = abs(float(max_shift))
    fraction = abs(float(estimated_shift)) / limit if limit else 0.0
    excess = max(0.0, fraction - warning_fraction)
    span = max(1e-12, 1.0 - warning_fraction)
    severity = min(1.0, excess / span)
    penalty = max(0.0, float(raw_score)) * max(0.0, float(max_penalty_fraction)) * severity
    return {
        "shift_fraction_of_limit": fraction,
        "shift_calibration_warning": fraction >= warning_fraction,
        "calibration_penalty": penalty,
        "calibration_adjusted_score": float(raw_score) - penalty,
    }


def _get_database() -> Dict:
    if DATABASE is None:
        raise RuntimeError("Database is not loaded")
    return DATABASE


def _canonical_elements(values: Sequence) -> Tuple[str, ...]:
    """Return a stable element-set key used by the local database indexes."""
    cleaned = {str(item).strip().capitalize() for item in values if str(item).strip()}
    return tuple(sorted(cleaned))


def _parse_known_element_sets(value) -> List[Tuple[str, ...]]:
    """Parse one exact phase element set per line or semicolon-separated group."""
    if value is None or value == "":
        return []
    groups = value if isinstance(value, list) else str(value).replace("\r", "").replace(";", "\n").split("\n")
    parsed = []
    for group in groups:
        items = group if isinstance(group, (list, tuple)) else str(group).replace("，", ",").split(",")
        key = _canonical_elements(items)
        if key and key not in parsed:
            parsed.append(key)
    return parsed


def _parse_known_mpids(value) -> List[str]:
    if value is None or value == "":
        return []
    raw = value if isinstance(value, list) else str(value).replace("\r", "").replace("\n", ",").replace(";", ",").split(",")
    result = []
    for item in raw:
        token = _canonical_mpid(item)
        if token and token not in result:
            result.append(token)
    return result


def _parse_known_formulas(value) -> List[str]:
    """Read one chemical formula per line (or semicolon-separated)."""
    if value is None or value == "":
        return []
    raw = value if isinstance(value, list) else str(value).replace("\r", "").replace(";", "\n").split("\n")
    formulas = []
    for item in raw:
        formula = str(item).strip()
        if formula:
            # Validate at input time so a typo never silently becomes a full search.
            formula_ratio_key(formula)
            formulas.append(formula)
    return formulas


def _resolve_formula_entries(database: Dict, formulas: Sequence[str]) -> Tuple[List[int], Dict]:
    """Resolve formulas by reduced element ratio, not display-string equality."""
    keys = {formula: formula_ratio_key(formula) for formula in formulas}
    entry_ids: List[int] = []
    counts = {formula: 0 for formula in formulas}
    for entry_id, entry in normalize_database_package(database)["xrd_database"].items():
        try:
            entry_key = formula_ratio_key(entry.get("formula", ""))
        except ValueError:
            continue
        for formula, target_key in keys.items():
            if entry_key == target_key:
                entry_ids.append(int(entry_id))
                counts[formula] += 1
    missing = [formula for formula, count in counts.items() if count == 0]
    if missing:
        raise ValueError(f"No local database entries match the element ratio of: {', '.join(missing)}")
    return list(dict.fromkeys(entry_ids)), {
        "formulas": list(formulas),
        "formula_ratio_match_counts": counts,
        "resolved_entry_count": len(set(entry_ids)),
    }


def _canonical_mpid(value) -> str:
    """Normalize an MPID independently of the database's legacy ``.cif`` suffix."""
    return str(value).strip().lower().removesuffix(".cif")


def _resolve_known_phase_entries(database: Dict, element_sets: List[Tuple[str, ...]], mpids: List[str]) -> Tuple[List[int], Dict]:
    """Resolve exact element sets and MPIDs to trusted local database entries."""
    database = normalize_database_package(database)
    entries = database["xrd_database"]
    element_index = database.get("element_index", {})
    entry_ids: List[int] = []
    exact_counts = {}
    for element_set in element_sets:
        ids = [int(entry_id) for entry_id in element_index.get(element_set, [])]
        exact_counts[",".join(element_set)] = len(ids)
        entry_ids.extend(ids)
    mpid_entry_ids = []
    if mpids:
        # Older databases retain source filenames (e.g. ``mp-22862.cif``),
        # while the UI asks users for the Material Project ID (``mp-22862``).
        # Compare their canonical IDs so both representations resolve.
        mpid_to_entry = {
            _canonical_mpid(entry.get("mpid")): int(entry_id)
            for entry_id, entry in entries.items()
            if entry.get("mpid") is not None
        }
        missing_mpids = [mpid for mpid in mpids if mpid not in mpid_to_entry]
        if missing_mpids:
            raise ValueError(f"Known MPID not found in the local database: {', '.join(missing_mpids)}")
        mpid_entry_ids = [mpid_to_entry[mpid] for mpid in mpids]
        entry_ids.extend(mpid_entry_ids)
    deduplicated = list(dict.fromkeys(entry_ids))
    return deduplicated, {
        "exact_element_sets": [list(item) for item in element_sets],
        "exact_element_match_counts": exact_counts,
        "mpids": mpids,
        "mpid_entry_ids": mpid_entry_ids,
        "resolved_entry_count": len(deduplicated),
    }


def _database_stats() -> Dict:
    database = _get_database()
    xrd_db = database["xrd_database"]
    metadata = database.get("metadata", {})
    elements = set()
    formulas = set()
    for entry in xrd_db.values():
        elements.update(entry.get("elements", []))
        formulas.add(entry.get("formula"))
    return {
        "database_path": str(DATABASE_PATH) if DATABASE_PATH else None,
        "total_entries": len(xrd_db),
        "unique_elements": sorted(elements),
        "n_unique_elements": len(elements),
        "unique_formulas": len(formulas),
        "metadata": metadata,
    }


def _match(payload: Dict) -> Dict:
    database = _get_database()
    params = payload.get("params", {})
    two_theta, intensity = _prepare_arrays(payload.get("two_theta", []), payload.get("intensity", []))
    zero_shift = float(params.get("fixed_zero_shift", 0.0))
    specimen_displacement = float(params.get("specimen_displacement", 0.0))
    calibrated_two_theta = calibrate_two_theta(two_theta, zero_shift, specimen_displacement)

    detector = PeakDetector(
        min_peak_height=float(params.get("min_peak_height", 3.0)),
        min_peak_prominence=float(params.get("min_peak_prominence", 2.0)),
        min_peak_distance=float(params.get("min_peak_distance", 0.1)),
        smooth_window=int(params.get("smooth_window", 7)),
        baseline_window_fraction=float(params.get("baseline_window_fraction", 0.05)),
    )
    n_peaks = int(params.get("n_peaks", 4))
    # Keep the full detector count separate from the selected matching peaks.
    # ``len(detected_peaks)`` is otherwise capped by n_peaks and cannot be used
    # to decide whether a pattern is peak-rich.
    all_detected_peaks = detector.detect_peaks(calibrated_two_theta, intensity, preprocess=True)
    peaks = [dict(peak) for peak in all_detected_peaks[:n_peaks]]
    if peaks:
        selected_max_intensity = max(peak["intensity"] for peak in peaks)
        if selected_max_intensity > 0:
            for peak in peaks:
                peak["intensity"] = 100.0 * peak["intensity"] / selected_max_intensity
    exp_positions, exp_intensities = detector.extract_peak_positions_and_intensities(peaks)

    matcher = XRDMatcher(
        position_tolerance=float(params.get("position_tolerance", 0.2)),
        intensity_weight=float(params.get("intensity_weight", 0.15)),
        position_weight=float(params.get("position_weight", 0.85)),
        min_matched_peaks=int(params.get("min_matched_peaks", 2)),
        scoring_method=str(params.get("scoring_method", "hybrid")),
        max_shift=float(params.get("max_shift", 0.5)),
        shift_step=float(params.get("shift_step", 0.02)),
    )

    elements = payload.get("elements")
    if isinstance(elements, str):
        elements = [item.strip() for item in elements.split(",") if item.strip()]
    if not elements:
        elements = None
    element_filter_mode = str(payload.get("element_filter_mode", "contains"))
    top_n = int(payload.get("top_n", 10))
    formula = str(payload.get("formula") or "").strip()
    formula_entry_ids, formula_constraint = _resolve_formula_entries(database, [formula]) if formula else (None, None)

    candidate_ids = formula_entry_ids if formula_entry_ids is not None else matcher.filter_by_elements(database, elements, mode=element_filter_mode)
    results = matcher.match_pattern(
        exp_positions,
        exp_intensities,
        database,
        elements=elements,
        top_n=top_n,
        element_filter_mode=element_filter_mode,
        two_theta_range=(float(calibrated_two_theta[0]), float(calibrated_two_theta[-1])),
        candidate_ids=formula_entry_ids,
    )

    warning_fraction = float(params.get("shift_warning_fraction", 0.60))
    max_penalty_fraction = float(params.get("shift_penalty_max_fraction", 0.20))
    enriched = []
    for result in results:
        entry = database["xrd_database"].get(result["entry_id"], {})
        peaks_data = entry.get("peaks", {})
        estimated_shift = float(result.get("estimated_shift", 0.0))
        adjustment = _calibration_adjustment(
            float(result.get("score", 0.0)), estimated_shift,
            float(params.get("max_shift", 0.5)), warning_fraction, max_penalty_fraction,
        )
        enriched.append(
            {
                **result,
                **adjustment,
                "theoretical_peaks": {
                    "positions": peaks_data.get("positions", []),
                    "intensities": peaks_data.get("intensities", []),
                    "d_spacings": peaks_data.get("d_spacings", []),
                    "hkls": peaks_data.get("hkls", []),
                },
            }
        )
    enriched.sort(key=lambda candidate: candidate["calibration_adjusted_score"], reverse=True)

    processed_x, processed_y = detector.preprocess_spectrum(calibrated_two_theta, intensity)
    return {
        "status": "ok",
        "input_points": int(two_theta.size),
        "candidate_count": len(candidate_ids),
        "detected_peak_count": len(all_detected_peaks),
        "detected_peaks": peaks,
        "processed_spectrum": {
            "two_theta": processed_x.tolist(),
            "intensity": processed_y.tolist(),
        },
        "results": enriched,
        "params": params,
        "ranking": {
            "primary": "calibration_adjusted_score",
            "raw_score_field": "score",
            "shift_warning_fraction": warning_fraction,
            "max_penalty_fraction": max_penalty_fraction,
        },
        "elements": elements,
        "formula_constraint": formula_constraint,
        "element_filter_mode": element_filter_mode,
        "calibration": {"fixed_zero_shift": zero_shift, "specimen_displacement": specimen_displacement},
    }


def _detect_peaks(payload: Dict) -> Dict:
    """Detect all experimental peaks before any matching-peak cap is applied."""
    params = payload.get("params", {})
    two_theta, intensity = _prepare_arrays(payload.get("two_theta", []), payload.get("intensity", []))
    zero_shift = float(params.get("fixed_zero_shift", 0.0))
    specimen_displacement = float(params.get("specimen_displacement", 0.0))
    calibrated_two_theta = calibrate_two_theta(two_theta, zero_shift, specimen_displacement)
    detector = PeakDetector(
        min_peak_height=float(params.get("min_peak_height", 3.0)),
        min_peak_prominence=float(params.get("min_peak_prominence", 2.0)),
        min_peak_distance=float(params.get("min_peak_distance", 0.1)),
        smooth_window=int(params.get("smooth_window", 7)),
        baseline_window_fraction=float(params.get("baseline_window_fraction", 0.05)),
    )
    peaks = detector.detect_peaks(calibrated_two_theta, intensity, preprocess=True)
    processed_x, processed_y = detector.preprocess_spectrum(calibrated_two_theta, intensity)
    step = float(np.median(np.diff(processed_x))) if len(processed_x) > 1 else 0.0
    differences = np.diff(processed_y)
    noise_sigma = float(1.4826 * np.median(np.abs(differences - np.median(differences))) / math.sqrt(2)) if differences.size else 0.0
    max_peak_intensity = max((float(peak["intensity"]) for peak in peaks), default=0.0)
    min_width = max(2.0 * step, 0.0)
    min_prominence = max(float(params.get("min_peak_prominence", 2.0)), 5.0 * noise_sigma)
    reliable_peaks = []
    for peak in peaks:
        annotated = dict(peak)
        annotated["relative_intensity_percent"] = 100.0 * float(peak["intensity"]) / max_peak_intensity if max_peak_intensity else 0.0
        annotated["reliable"] = bool(
            float(peak["prominence"]) >= min_prominence
            and float(peak["width"]) >= min_width
            and annotated["relative_intensity_percent"] >= 1.0
        )
        reliable_peaks.append(annotated)
    reliable = [peak for peak in reliable_peaks if peak["reliable"]]
    return {
        "status": "ok",
        "input_points": int(two_theta.size),
        "detected_peak_count": len(peaks),
        "detected_peaks": reliable_peaks,
        "reliable_detected_peak_count": len(reliable),
        "reliable_detected_peaks": reliable,
        "reliability_criteria": {
            "minimum_prominence": min_prominence,
            "minimum_width_deg": min_width,
            "minimum_relative_intensity_percent": 1.0,
            "estimated_noise_sigma": noise_sigma,
        },
        "processed_spectrum": {
            "two_theta": processed_x.tolist(),
            "intensity": processed_y.tolist(),
        },
        "params": params,
        "calibration": {"fixed_zero_shift": zero_shift, "specimen_displacement": specimen_displacement},
    }


def _multiphase_match(payload: Dict) -> Dict:
    """Identify a small mixture from the same detected peaks used for matching."""
    database = _get_database()
    params = payload.get("params", {})
    two_theta, intensity = _prepare_arrays(payload.get("two_theta", []), payload.get("intensity", []))
    zero_shift = float(params.get("fixed_zero_shift", 0.0))
    specimen_displacement = float(params.get("specimen_displacement", 0.0))
    calibrated_two_theta = calibrate_two_theta(two_theta, zero_shift, specimen_displacement)
    detector = PeakDetector(
        min_peak_height=float(params.get("min_peak_height", 3.0)),
        min_peak_prominence=float(params.get("min_peak_prominence", 2.0)),
        min_peak_distance=float(params.get("min_peak_distance", 0.1)),
        smooth_window=int(params.get("smooth_window", 7)),
        baseline_window_fraction=float(params.get("baseline_window_fraction", 0.05)),
    )
    # Quantifying a mixture from only the few strongest peaks can entirely
    # miss a genuine minor phase.  Retain the single-phase setting as a lower
    # bound, but fit AutoMix with at least twelve detected peaks.
    n_peaks = int(params.get("multiphase_n_peaks", max(12, int(params.get("n_peaks", 4)))))
    n_peaks = max(1, min(n_peaks, 80))
    peaks = detector.get_top_peaks(calibrated_two_theta, intensity, n_peaks=n_peaks, preprocess=True)
    exp_positions, exp_intensities = detector.extract_peak_positions_and_intensities(peaks)
    matcher = XRDMatcher(
        position_tolerance=float(params.get("position_tolerance", 0.2)),
        intensity_weight=float(params.get("intensity_weight", 0.15)),
        position_weight=float(params.get("position_weight", 0.85)),
        min_matched_peaks=int(params.get("min_matched_peaks", 2)),
        scoring_method=str(params.get("scoring_method", "hybrid")),
        max_shift=float(params.get("max_shift", 0.5)),
        shift_step=float(params.get("shift_step", 0.02)),
    )
    elements = payload.get("elements")
    if isinstance(elements, str):
        elements = [item.strip() for item in elements.split(",") if item.strip()]
    element_filter_mode = str(payload.get("element_filter_mode", "contains"))
    known_element_sets = _parse_known_element_sets(payload.get("known_phase_elements"))
    known_formulas = _parse_known_formulas(payload.get("known_phase_formulas"))
    known_mpids = _parse_known_mpids(payload.get("known_phase_mpids"))
    known_entry_ids, known_phase_constraints = _resolve_known_phase_entries(database, known_element_sets, known_mpids)
    formula_entry_ids, formula_constraints = _resolve_formula_entries(database, known_formulas) if known_formulas else ([], {"formulas": [], "formula_ratio_match_counts": {}, "resolved_entry_count": 0})
    known_entry_ids = list(dict.fromkeys(known_entry_ids + formula_entry_ids))
    known_phase_constraints["formulas"] = formula_constraints["formulas"]
    known_phase_constraints["formula_ratio_match_counts"] = formula_constraints["formula_ratio_match_counts"]
    known_phase_constraints["resolved_entry_count"] = len(known_entry_ids)
    unmatched_sets = [name for name, count in known_phase_constraints["exact_element_match_counts"].items() if count == 0]
    if unmatched_sets:
        raise ValueError(f"No local database entries match the exact known phase element set(s): {', '.join(unmatched_sets)}")
    result = MultiPhaseMatcher(matcher).match_pattern(
        exp_positions, exp_intensities, database, elements=elements or None,
        element_filter_mode=element_filter_mode,
        max_phases=int(payload.get("max_phases", 3)),
        candidate_pool=int(payload.get("candidate_pool", 8)),
        top_n=int(payload.get("top_n", 10)),
        known_entry_ids=known_entry_ids,
        required_entry_ids=known_phase_constraints["mpid_entry_ids"],
        required_element_sets=known_element_sets,
        minimum_required_contribution_percent=3.0,
        two_theta_range=(float(calibrated_two_theta[0]), float(calibrated_two_theta[-1])),
        prefer_multiphase=bool(payload.get("prefer_multiphase", True)),
        required_formula_keys=[formula_ratio_key(formula) for formula in known_formulas],
    )
    single_results = []
    # MultiPhaseMatcher already evaluates its one-phase baseline. Only perform
    # this legacy fallback when no combination was usable and no known-phase
    # constraint must be preserved.
    if not result.get("results") and not known_entry_ids:
        single_results = matcher.match_pattern(
            exp_positions, exp_intensities, database, elements=elements or None,
            element_filter_mode=element_filter_mode, top_n=1,
            two_theta_range=(float(calibrated_two_theta[0]), float(calibrated_two_theta[-1])),
        )
    if not result.get("results") and single_results:
        candidate = single_results[0]
        attribution = [
            {
                "two_theta": float(match["exp_two_theta"]),
                "intensity": float(match["exp_intensity"]),
                "fitted_intensity": float(match["exp_intensity"]),
                "residual_intensity": 0.0,
                "assigned_formula": candidate.get("formula"),
                "overlap": False,
            }
            for match in candidate.get("peak_matches", [])
        ]
        result["results"] = [{
            "score": float(candidate.get("score", 0.0)),
            "residual_sum_squares": None,
            "explained_intensity_percent": float(candidate.get("experimental_coverage", 0.0)),
            "n_phases": 1,
            "phases": [{
                "entry_id": candidate["entry_id"], "mpid": candidate.get("mpid"), "cryst_id": candidate.get("cryst_id"),
                "formula": candidate.get("formula"), "elements": candidate.get("elements", []),
                "spacegroup": candidate.get("spacegroup"), "spacegroup_symbol": candidate.get("spacegroup_symbol"),
                "estimated_shift": candidate.get("estimated_shift", 0.0),
                "single_phase_score": candidate.get("score", 0.0), "relative_contribution": 100.0,
            }],
            "peak_attribution": attribution,
            "fallback": "single_phase",
        }]
        result["fallback_used"] = True
    # AutoMix needs the complete database peak list for each selected phase,
    # not only the detected-peak fit.  This lets the UI provide the same
    # full-theoretical-peak verification users get in the PDF comparison.
    for combination in result.get("results", []):
        for phase in combination.get("phases", []):
            entry = database["xrd_database"].get(phase.get("entry_id"), {})
            peaks_data = entry.get("peaks", {})
            phase["theoretical_peaks"] = {
                "positions": peaks_data.get("positions", []),
                "intensities": peaks_data.get("intensities", []),
                "d_spacings": peaks_data.get("d_spacings", []),
                "hkls": peaks_data.get("hkls", []),
            }
    result["single_phase_fallback_available"] = bool(single_results)
    result["known_phase_constraints"] = known_phase_constraints
    processed_x, processed_y = detector.preprocess_spectrum(calibrated_two_theta, intensity)
    return {
        "status": "ok", "detected_peaks": peaks,
        "processed_spectrum": {"two_theta": processed_x.tolist(), "intensity": processed_y.tolist()},
        "calibration": {"fixed_zero_shift": zero_shift, "specimen_displacement": specimen_displacement},
        **result,
    }


def _calculate_cif_xrd(payload: Dict) -> Dict:
    try:
        from pymatgen.analysis.diffraction.xrd import XRDCalculator as PymatgenXRDCalculator
        from pymatgen.io.cif import CifParser
    except Exception as exc:
        raise RuntimeError(f"pymatgen is required for CIF XRD calculation: {exc}") from exc

    cifs = payload.get("cifs") or []
    if not isinstance(cifs, list) or not cifs:
        raise ValueError("At least one CIF is required")
    if len(cifs) > 5:
        raise ValueError("At most 5 CIF files are supported")

    two_theta_range = payload.get("two_theta_range") or [5.0, 90.0]
    if len(two_theta_range) != 2:
        raise ValueError("two_theta_range must contain [min, max]")
    t_min = float(two_theta_range[0])
    t_max = float(two_theta_range[1])
    if not math.isfinite(t_min) or not math.isfinite(t_max) or t_max <= t_min:
        raise ValueError("Invalid two_theta_range")

    wavelength = str(payload.get("wavelength") or "CuKa")
    min_intensity = max(0.0, float(payload.get("min_intensity", 0.0)))
    fwhm = max(0.01, float(payload.get("fwhm", 0.12)))
    step = max(0.005, float(payload.get("step", 0.02)))
    normalize = bool(payload.get("normalize", True))

    calculator = PymatgenXRDCalculator(wavelength=wavelength)
    phases = []
    weights = []
    grid = np.arange(t_min, t_max + step / 2, step, dtype=float)
    mixture = np.zeros_like(grid)
    sigma = fwhm / 2.354820045

    for index, item in enumerate(cifs):
        name = str(item.get("name") or f"phase_{index + 1}.cif")
        content = str(item.get("content") or "")
        weight = float(item.get("weight", 1.0))
        if not content.strip():
            raise ValueError(f"CIF content is empty for {name}")
        if not math.isfinite(weight) or weight < 0:
            raise ValueError(f"Invalid weight for {name}")
        weights.append(weight)

        parser = CifParser(io.StringIO(content.lstrip("\ufeff")))
        structures = parser.get_structures(primitive=False)
        if not structures:
            raise ValueError(f"No structure found in {name}")
        structure = structures[0]
        pattern = calculator.get_pattern(structure, two_theta_range=(t_min, t_max))
        positions = np.asarray(pattern.x, dtype=float)
        intensities = np.asarray(pattern.y, dtype=float)
        if intensities.size and normalize and intensities.max() > 0:
            intensities = 100.0 * intensities / intensities.max()
        keep = intensities >= min_intensity
        positions = positions[keep]
        intensities = intensities[keep]
        hkls = [pattern.hkls[i] for i in range(len(pattern.hkls)) if keep[i]]
        d_spacings = np.asarray(getattr(pattern, "d_hkls", []), dtype=float)
        if d_spacings.size == len(keep):
            d_spacings = d_spacings[keep]
        else:
            d_spacings = np.asarray([], dtype=float)

        broadened = np.zeros_like(grid)
        for pos, intensity_value in zip(positions, intensities):
            broadened += float(intensity_value) * np.exp(-0.5 * ((grid - pos) / sigma) ** 2)
        mixture += weight * broadened

        phases.append(
            {
                "name": name,
                "weight": weight,
                "formula": structure.composition.reduced_formula,
                "spacegroup": None,
                "peaks": {
                    "positions": positions.tolist(),
                    "intensities": intensities.tolist(),
                    "hkls": hkls,
                    "d_spacings": d_spacings.tolist(),
                },
                "profile": {
                    "two_theta": grid.tolist(),
                    "intensity": broadened.tolist(),
                },
            }
        )

    total_weight = sum(weights) or 1.0
    mixture = mixture / total_weight
    if mixture.size and normalize and mixture.max() > 0:
        mixture = 100.0 * mixture / mixture.max()

    return {
        "status": "ok",
        "phases": phases,
        "mixture": {
            "two_theta": grid.tolist(),
            "intensity": mixture.tolist(),
        },
        "settings": {
            "two_theta_range": [t_min, t_max],
            "wavelength": wavelength,
            "min_intensity": min_intensity,
            "fwhm": fwhm,
            "step": step,
            "normalize": normalize,
        },
    }


def _xlsx_escape(value) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _excel_sheet_name(value: object, index: int, used_names: set) -> str:
    name = re.sub(r"[\\[\\]:*?/\\\\]", "_", str(value or f"Phase {index}"))
    name = name.rsplit(".", 1)[0].strip() or f"Phase {index}"
    name = name[:31]
    candidate = name
    suffix = 2
    while candidate.lower() in used_names:
        marker = f"_{suffix}"
        candidate = f"{name[:31 - len(marker)]}{marker}"
        suffix += 1
    used_names.add(candidate.lower())
    return candidate


def _hkl_text(value: object) -> str:
    """Convert pymatgen's HKL/multiplicity records into a readable cell value."""
    if not isinstance(value, list):
        return str(value or "")
    labels = []
    for item in value:
        if isinstance(item, dict):
            hkl = item.get("hkl", "")
            multiplicity = item.get("multiplicity")
            if isinstance(hkl, (list, tuple)):
                hkl = " ".join(str(part) for part in hkl)
            label = f"({hkl})" if hkl else ""
            if multiplicity is not None:
                label = f"{label} ×{multiplicity}".strip()
            labels.append(label)
        else:
            labels.append(str(item))
    return "; ".join(label for label in labels if label)


def _pdf_peaks_xlsx(payload: Dict) -> bytes:
    """Build a compact XLSX workbook with one peak table per calculated phase."""
    phases = payload.get("phases") or []
    if not isinstance(phases, list) or not phases:
        raise ValueError("No PDF phase peaks available for Excel export")

    sheets = []
    used_names = set()
    for index, phase in enumerate(phases, start=1):
        if not isinstance(phase, dict):
            continue
        peaks = phase.get("peaks") or {}
        positions = peaks.get("positions") or []
        intensities = peaks.get("intensities") or []
        hkls = peaks.get("hkls") or []
        d_spacings = peaks.get("d_spacings") or []
        sheet_name = _excel_sheet_name(phase.get("name"), index, used_names)
        rows = [
            ["Phase", phase.get("name", "")],
            ["Formula", phase.get("formula", "")],
            ["Weight (%)", phase.get("weight", "")],
            [],
            ["HKL", "2theta (degree)", "d spacing (angstrom)", "Relative intensity (%)"],
        ]
        for peak_index, position in enumerate(positions):
            rows.append([
                _hkl_text(hkls[peak_index]) if peak_index < len(hkls) else "",
                position,
                d_spacings[peak_index] if peak_index < len(d_spacings) else "",
                intensities[peak_index] if peak_index < len(intensities) else "",
            ])
        sheets.append((sheet_name, rows))

    if not sheets:
        raise ValueError("No valid PDF phase peaks available for Excel export")

    def cell_xml(row_index: int, column_index: int, value: object) -> str:
        column = ""
        number = column_index
        while number:
            number, remainder = divmod(number - 1, 26)
            column = chr(65 + remainder) + column
        ref = f"{column}{row_index}"
        if isinstance(value, bool):
            value = int(value)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return f'<c r="{ref}"><v>{value}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{_xlsx_escape(value)}</t></is></c>'

    workbook = io.BytesIO()
    with zipfile.ZipFile(workbook, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, len(sheets) + 1))
            + "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(f'<sheet name="{_xlsx_escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i, (name, _) in enumerate(sheets, start=1))
            + "</sheets></workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1))
            + "</Relationships>",
        )
        for sheet_index, (_, rows) in enumerate(sheets, start=1):
            sheet_rows = "".join(
                f'<row r="{row_index}">' + "".join(cell_xml(row_index, column_index, value) for column_index, value in enumerate(row, start=1)) + "</row>"
                for row_index, row in enumerate(rows, start=1)
            )
            archive.writestr(
                f"xl/worksheets/sheet{sheet_index}.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                + sheet_rows
                + "</sheetData></worksheet>",
            )
    return workbook.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = "XMatcherLocalAPI/1.3.0"

    def do_OPTIONS(self) -> None:
        _json_response(self, 200, {"status": "ok"})

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/api/status":
            _json_response(self, 200, {"status": "ok", "database": _database_stats()})
            return
        _json_response(self, 404, {"status": "error", "error": "Unknown endpoint"})

    def do_POST(self) -> None:
        try:
            if self.path.rstrip("/") == "/api/detect-peaks":
                payload = _read_json(self)
                _json_response(self, 200, _detect_peaks(payload))
                return
            if self.path.rstrip("/") == "/api/match":
                payload = _read_json(self)
                _json_response(self, 200, _match(payload))
                return
            if self.path.rstrip("/") == "/api/multiphase-match":
                payload = _read_json(self)
                _json_response(self, 200, _multiphase_match(payload))
                return
            if self.path.rstrip("/") == "/api/cif-xrd":
                payload = _read_json(self)
                _json_response(self, 200, _calculate_cif_xrd(payload))
                return
            if self.path.rstrip("/") == "/api/pdf-peaks-xlsx":
                payload = _read_json(self)
                _xlsx_response(self, "xmatcher_pdf_peak_tables.xlsx", _pdf_peaks_xlsx(payload))
                return
            _json_response(self, 404, {"status": "error", "error": "Unknown endpoint"})
        except Exception as exc:
            logger.exception("Request failed")
            _json_response(self, 500, {"status": "error", "error": str(exc)})

    def log_message(self, fmt: str, *args) -> None:
        logger.info("%s - %s", self.address_string(), fmt % args)


def main() -> int:
    global DATABASE, DATABASE_PATH

    parser = argparse.ArgumentParser(description="Local XMatcher API for XMatcher_Local_UI.html")
    parser.add_argument("--database", default="MP500_xrd_database.pkl", help="Path to the built XMatcher .pkl database")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", default=8765, type=int, help="Bind port")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    DATABASE_PATH = Path(args.database)
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DATABASE_PATH}")

    logger.info("Loading database: %s", DATABASE_PATH)
    DATABASE = DatabaseBuilder.load_database(str(DATABASE_PATH))
    DATABASE = normalize_database_package(DATABASE)
    logger.info("Loaded %d entries", len(DATABASE["xrd_database"]))

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    logger.info("Serving XMatcher local API at http://%s:%d", args.host, args.port)
    logger.info("Open XMatcher_Local_UI.html in your browser.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
