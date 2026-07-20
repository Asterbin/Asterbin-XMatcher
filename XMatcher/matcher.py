"""Peak-level matching and ranking for XRD phase retrieval."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist

from .database import normalize_database_package

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MatchConfig:
    position_tolerance: float = 0.2
    intensity_weight: float = 0.15
    position_weight: float = 0.85
    min_matched_peaks: int = 2
    max_shift: float = 0.5
    shift_step: float = 0.02
    scoring_method: str = "hybrid"
    shift_candidate_limit: int = 4000


class XRDMatcher:
    """Match experimental peaks to theoretical database peaks."""

    valid_scoring_methods = {"weighted", "fom", "hybrid", "combined"}
    valid_filter_modes = {"contains", "exact"}

    def __init__(
        self,
        position_tolerance: float = 0.2,
        intensity_weight: float = 0.15,
        position_weight: float = 0.85,
        min_matched_peaks: int = 2,
        scoring_method: str = "hybrid",
        max_shift: float = 0.5,
        shift_step: float = 0.02,
    ):
        if scoring_method not in self.valid_scoring_methods:
            raise ValueError(f"scoring_method must be one of {sorted(self.valid_scoring_methods)}")
        if position_tolerance <= 0:
            raise ValueError("position_tolerance must be positive")
        if min_matched_peaks < 1:
            raise ValueError("min_matched_peaks must be at least 1")

        total_weight = intensity_weight + position_weight
        if total_weight <= 0:
            raise ValueError("intensity_weight + position_weight must be positive")

        self.config = MatchConfig(
            position_tolerance=position_tolerance,
            intensity_weight=intensity_weight / total_weight,
            position_weight=position_weight / total_weight,
            min_matched_peaks=min_matched_peaks,
            scoring_method=scoring_method,
            max_shift=max_shift,
            shift_step=shift_step,
        )

    @property
    def position_tolerance(self) -> float:
        return self.config.position_tolerance

    @property
    def scoring_method(self) -> str:
        return self.config.scoring_method

    def filter_by_elements(
        self,
        database: Dict,
        query_elements: Optional[Sequence[str]],
        mode: str = "contains",
    ) -> List[int]:
        database = normalize_database_package(database)
        xrd_db = database["xrd_database"]
        if not query_elements:
            return list(xrd_db.keys())
        if mode not in self.valid_filter_modes:
            raise ValueError(f"element_filter_mode must be one of {sorted(self.valid_filter_modes)}")

        query_set = {_normalize_element_symbol(element) for element in query_elements}
        if mode == "exact":
            ids = database.get("element_index", {}).get(tuple(sorted(query_set)), [])
            return [entry_id for entry_id in ids if entry_id in xrd_db]

        inverted = database.get("element_inverted_index", {})
        if inverted:
            candidate_sets = [set(inverted.get(element, [])) for element in query_set]
            if not candidate_sets:
                return []
            candidate_ids = set.intersection(*candidate_sets)
            return sorted(entry_id for entry_id in candidate_ids if entry_id in xrd_db)

        return [
            entry_id
            for entry_id, entry in xrd_db.items()
            if query_set.issubset(set(entry.get("elements", [])))
        ]

    def match_pattern(
        self,
        exp_positions: Sequence[float],
        exp_intensities: Sequence[float],
        database: Dict,
        elements: Optional[Sequence[str]] = None,
        top_n: int = 10,
        element_filter_mode: str = "contains",
        include_zero_scores: bool = False,
    ) -> List[Dict]:
        database = normalize_database_package(database)
        xrd_db = database["xrd_database"]
        candidate_ids = self.filter_by_elements(database, elements, mode=element_filter_mode)
        exp_positions_arr = np.asarray(exp_positions, dtype=float)
        exp_intensities_arr = np.asarray(exp_intensities, dtype=float)

        results = []
        for entry_id in candidate_ids:
            entry = xrd_db[entry_id]
            metrics = self.match_single_entry(exp_positions_arr, exp_intensities_arr, entry)
            if include_zero_scores or metrics["score"] > 0:
                results.append(
                    {
                        "entry_id": entry_id,
                        "mpid": entry.get("mpid"),
                        "formula": entry.get("formula"),
                        "elements": entry.get("elements", []),
                        "spacegroup": entry.get("spacegroup_number"),
                        "spacegroup_symbol": entry.get("spacegroup_symbol"),
                        **metrics,
                    }
                )

        results.sort(
            key=lambda item: (
                item["score"],
                item["n_matched_peaks"],
                item["fom"],
                item["experimental_coverage"],
                _negative_or_large(item["mean_abs_error"]),
                -abs(item["estimated_shift"]),
            ),
            reverse=True,
        )
        return results[:top_n]

    def match_single_entry(
        self,
        exp_positions: np.ndarray,
        exp_intensities: np.ndarray,
        entry: Dict,
    ) -> Dict:
        db_positions = np.asarray(entry.get("peaks", {}).get("positions", []), dtype=float)
        db_intensities = np.asarray(entry.get("peaks", {}).get("intensities", []), dtype=float)
        return self.calculate_match_metrics(exp_positions, exp_intensities, db_positions, db_intensities)

    def calculate_peak_match_score(
        self,
        exp_positions: np.ndarray,
        exp_intensities: np.ndarray,
        db_positions: np.ndarray,
        db_intensities: np.ndarray,
    ) -> float:
        return self.calculate_match_metrics(exp_positions, exp_intensities, db_positions, db_intensities)["weighted_score"]

    def calculate_fom_score(
        self,
        exp_positions: np.ndarray,
        exp_intensities: np.ndarray,
        db_positions: np.ndarray,
        db_intensities: np.ndarray,
    ) -> Tuple[float, int]:
        metrics = self.calculate_match_metrics(exp_positions, exp_intensities, db_positions, db_intensities)
        return metrics["fom"], metrics["n_matched_peaks"]

    def calculate_match_metrics(
        self,
        exp_positions: np.ndarray,
        exp_intensities: np.ndarray,
        db_positions: np.ndarray,
        db_intensities: np.ndarray,
    ) -> Dict:
        exp_positions, exp_intensities = _prepare_peak_arrays(exp_positions, exp_intensities)
        db_positions, db_intensities = _prepare_peak_arrays(db_positions, db_intensities)

        if exp_positions.size == 0 or db_positions.size == 0:
            return self._empty_metrics()

        best = self._empty_metrics()
        for shift in self._candidate_shifts(exp_positions, db_positions):
            metrics = self._score_at_shift(exp_positions, exp_intensities, db_positions + shift, db_intensities, shift)
            if self._is_better_match(metrics, best):
                best = metrics
        return best

    def calculate_figure_of_merit(
        self,
        exp_positions: np.ndarray,
        exp_intensities: np.ndarray,
        db_positions: np.ndarray,
        db_intensities: np.ndarray,
    ) -> Dict[str, float]:
        metrics = self.calculate_match_metrics(exp_positions, exp_intensities, db_positions, db_intensities)
        return {
            "match_score": metrics["score"],
            "weighted_score": metrics["weighted_score"],
            "fom": metrics["fom"],
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "mean_abs_error": metrics["mean_abs_error"],
            "n_exp_peaks": len(exp_positions),
            "n_db_peaks": len(db_positions),
            "n_matched_peaks": metrics["n_matched_peaks"],
        }

    def _score_at_shift(
        self,
        exp_positions: np.ndarray,
        exp_intensities: np.ndarray,
        shifted_db_positions: np.ndarray,
        db_intensities: np.ndarray,
        shift: float,
    ) -> Dict:
        exp_norm = _normalize_max(exp_intensities)
        db_norm = _normalize_max(db_intensities)
        position_dist = cdist(exp_positions.reshape(-1, 1), shifted_db_positions.reshape(-1, 1))
        intensity_diff = np.abs(exp_norm.reshape(-1, 1) - db_norm.reshape(1, -1)) / 100.0

        cost = (
            self.config.position_weight * (position_dist / self.position_tolerance)
            + self.config.intensity_weight * intensity_diff
        )
        cost[position_dist > self.position_tolerance] = np.inf
        if np.all(np.isinf(cost)):
            return self._empty_metrics(shift=shift)

        # ``linear_sum_assignment`` rejects a matrix as infeasible when even
        # one experimental peak has no theoretical peak inside tolerance. In
        # phase identification that is normal: unmatched experimental peaks
        # are residual evidence, not a reason to discard every valid pair.
        # Restrict the assignment to rows and columns with at least one finite
        # edge, then retain only finite assignments below.
        eligible_rows = np.flatnonzero(np.any(np.isfinite(cost), axis=1))
        eligible_cols = np.flatnonzero(np.any(np.isfinite(cost), axis=0))
        if not eligible_rows.size or not eligible_cols.size:
            return self._empty_metrics(shift=shift)
        feasible_cost = cost[np.ix_(eligible_rows, eligible_cols)]
        try:
            row_sub, col_sub = linear_sum_assignment(feasible_cost)
        except ValueError:
            return self._empty_metrics(shift=shift)

        row_ind = eligible_rows[row_sub]
        col_ind = eligible_cols[col_sub]
        valid = np.isfinite(cost[row_ind, col_ind])
        row_ind = row_ind[valid]
        col_ind = col_ind[valid]
        n_matched = int(len(row_ind))
        if n_matched < self.config.min_matched_peaks:
            return self._empty_metrics(shift=shift, n_matched=n_matched)

        matched_costs = cost[row_ind, col_ind]
        matched_errors = np.abs(exp_positions[row_ind] - shifted_db_positions[col_ind])
        db_total_intensity = float(np.sum(db_norm))
        exp_total_intensity = float(np.sum(exp_norm))
        matched_db_intensity = float(np.sum(db_norm[col_ind]))
        matched_exp_intensity = float(np.sum(exp_norm[row_ind]))

        recall = n_matched / len(shifted_db_positions)
        precision = n_matched / len(exp_positions)
        fom = 100.0 * matched_db_intensity / db_total_intensity if db_total_intensity > 0 else 0.0
        exp_coverage = 100.0 * matched_exp_intensity / exp_total_intensity if exp_total_intensity > 0 else 0.0
        quality = 100.0 * float(np.exp(-np.mean(matched_costs)))
        weighted_score = quality * (0.5 * recall + 0.5 * precision)

        hybrid_score = (
            0.45 * weighted_score
            + 0.30 * fom
            + 0.15 * exp_coverage
            + 0.10 * 100.0 * min(recall, precision)
        )
        score = {
            "weighted": weighted_score,
            "fom": fom,
            "combined": hybrid_score,
            "hybrid": hybrid_score,
        }[self.scoring_method]

        peak_matches = []
        for exp_idx, db_idx, err, pair_cost in zip(row_ind, col_ind, matched_errors, matched_costs):
            peak_matches.append(
                {
                    "exp_index": int(exp_idx),
                    "db_index": int(db_idx),
                    "exp_two_theta": float(exp_positions[exp_idx]),
                    "db_two_theta": float(shifted_db_positions[db_idx]),
                    "db_two_theta_unshifted": float(shifted_db_positions[db_idx] - shift),
                    "delta": float(exp_positions[exp_idx] - shifted_db_positions[db_idx]),
                    "exp_intensity": float(exp_norm[exp_idx]),
                    "db_intensity": float(db_norm[db_idx]),
                    "cost": float(pair_cost),
                }
            )

        return {
            "score": float(score),
            "weighted_score": float(weighted_score),
            "fom": float(fom),
            "experimental_coverage": float(exp_coverage),
            "precision": float(precision),
            "recall": float(recall),
            "n_matched_peaks": n_matched,
            "mean_abs_error": float(np.mean(matched_errors)),
            "max_abs_error": float(np.max(matched_errors)),
            "estimated_shift": float(shift),
            "peak_matches": peak_matches,
        }

    def _candidate_shifts(self, exp_positions: np.ndarray, db_positions: np.ndarray) -> np.ndarray:
        shifts = list(self._shift_grid())
        if self.config.max_shift > 0:
            pair_diffs = exp_positions.reshape(-1, 1) - db_positions.reshape(1, -1)
            pair_diffs = pair_diffs[np.abs(pair_diffs) <= self.config.max_shift]
            if pair_diffs.size <= self.config.shift_candidate_limit:
                shifts.extend(pair_diffs.tolist())
            elif pair_diffs.size:
                sample_indices = np.linspace(0, pair_diffs.size - 1, self.config.shift_candidate_limit, dtype=int)
                shifts.extend(pair_diffs[sample_indices].tolist())
        return np.unique(np.round(np.asarray(shifts, dtype=float), 10))

    def _shift_grid(self) -> np.ndarray:
        if self.config.max_shift <= 0 or self.config.shift_step <= 0:
            return np.array([0.0])
        n_steps = int(round(self.config.max_shift / self.config.shift_step))
        values = np.arange(-n_steps, n_steps + 1, dtype=float) * self.config.shift_step
        if 0.0 not in values:
            values = np.append(values, 0.0)
        return np.unique(np.round(values, 10))

    def _is_better_match(self, candidate: Dict, current: Dict) -> bool:
        if candidate["score"] > current["score"] + 1e-12:
            return True
        if candidate["score"] < current["score"] - 1e-12:
            return False

        candidate_error = _none_to_inf(candidate["mean_abs_error"])
        current_error = _none_to_inf(current["mean_abs_error"])
        if candidate_error < current_error - 1e-12:
            return True
        if candidate_error > current_error + 1e-12:
            return False

        candidate_key = (
            candidate["n_matched_peaks"],
            candidate["fom"],
            candidate["experimental_coverage"],
            -abs(candidate["estimated_shift"]),
        )
        current_key = (
            current["n_matched_peaks"],
            current["fom"],
            current["experimental_coverage"],
            -abs(current["estimated_shift"]),
        )
        return candidate_key > current_key

    def _empty_metrics(self, shift: float = 0.0, n_matched: int = 0) -> Dict:
        return {
            "score": 0.0,
            "weighted_score": 0.0,
            "fom": 0.0,
            "experimental_coverage": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "n_matched_peaks": int(n_matched),
            "mean_abs_error": None,
            "max_abs_error": None,
            "estimated_shift": float(shift),
            "peak_matches": [],
        }


def _normalize_max(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return values
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    values[values < 0] = 0.0
    values = np.sqrt(values)
    max_value = np.max(values)
    return 100.0 * values / max_value if max_value > 0 else values


def _prepare_peak_arrays(positions: Sequence[float], intensities: Sequence[float]) -> Tuple[np.ndarray, np.ndarray]:
    positions = np.asarray(positions, dtype=float)
    intensities = np.asarray(intensities, dtype=float)
    if positions.size != intensities.size:
        raise ValueError("peak positions and intensities must have the same length")
    if positions.size == 0:
        return positions, intensities

    valid = np.isfinite(positions) & np.isfinite(intensities)
    positions = positions[valid]
    intensities = intensities[valid]
    intensities = np.maximum(intensities, 0.0)

    order = np.argsort(positions)
    return positions[order], intensities[order]


def _normalize_element_symbol(element: str) -> str:
    element = str(element).strip()
    if not element:
        return element
    return element[0].upper() + element[1:].lower()


def _none_to_inf(value: Optional[float]) -> float:
    return float("inf") if value is None else float(value)


def _negative_or_large(value: Optional[float]) -> float:
    return -_none_to_inf(value)
