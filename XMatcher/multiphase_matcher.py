"""Automatic multi-phase XRD identification built on single-phase retrieval.

The fitted values are relative diffraction contributions, not weight fractions.
"""

from __future__ import annotations

from itertools import combinations
from typing import Dict, List, Optional, Sequence

import numpy as np
from scipy.optimize import nnls

from .database import normalize_database_package
from .matcher import XRDMatcher


class MultiPhaseMatcher:
    """Rank small combinations of database phases using non-negative fitting."""

    def __init__(self, matcher: XRDMatcher):
        self.matcher = matcher

    def match_pattern(
        self,
        exp_positions: Sequence[float],
        exp_intensities: Sequence[float],
        database: Dict,
        elements: Optional[Sequence[str]] = None,
        element_filter_mode: str = "contains",
        max_phases: int = 3,
        candidate_pool: int = 8,
        top_n: int = 10,
        known_entry_ids: Optional[Sequence[int]] = None,
        required_entry_ids: Optional[Sequence[int]] = None,
        required_element_sets: Optional[Sequence[Sequence[str]]] = None,
        minimum_required_contribution_percent: float = 3.0,
    ) -> Dict:
        """Return ranked phase combinations and peak-level attribution.

        Single-phase retrieval provides a chemically and positionally plausible
        candidate pool. Every combination in that small pool is then fitted with
        NNLS against the detected experimental peaks.
        """
        max_phases = max(1, min(int(max_phases), 3))
        candidate_pool = max(2, min(int(candidate_pool), 30))
        top_n = max(1, int(top_n))
        minimum_required_contribution_percent = max(0.0, float(minimum_required_contribution_percent))
        x = np.asarray(exp_positions, dtype=float)
        y = np.maximum(np.asarray(exp_intensities, dtype=float), 0.0)
        if x.ndim != 1 or y.ndim != 1 or x.size != y.size:
            raise ValueError("peak positions and intensities must be one-dimensional arrays of equal length")
        valid = np.isfinite(x) & np.isfinite(y)
        x, y = x[valid], y[valid]
        order = np.argsort(x)
        x, y = x[order], y[order]
        if not x.size or float(y.sum()) <= 0:
            return {"candidate_count": 0, "combinations_tested": 0, "results": []}

        # Known-phase mode is intentionally constrained: the user supplied
        # the components to accelerate AutoMix and requires every result to
        # contain them. Searching the unconstrained ~100k-entry library again
        # would both defeat that purpose and introduce irrelevant phases.
        candidates = [] if known_entry_ids else self._single_phase_candidates(
            x, y, database, elements, element_filter_mode, candidate_pool
        )
        known_candidates = self._known_entry_candidates(
            x, y, database, known_entry_ids, candidate_pool, required_element_sets, required_entry_ids
        )
        # Known-phase candidates are prepended so an explicitly supplied MPID
        # or exact-element constraint cannot be displaced by the unconstrained
        # retrieval ranking. De-duplicate by database entry while retaining the
        # known candidate's priority.
        candidate_by_id = {}
        for item in known_candidates + candidates:
            candidate_by_id.setdefault(item["entry_id"], item)
        candidates = list(candidate_by_id.values())
        known_ids = {int(item) for item in known_entry_ids or []}
        candidates = [item for item in candidates if item.get("n_matched_peaks", 0) > 0 or item["entry_id"] in known_ids]
        if not candidates:
            return {"candidate_count": 0, "combinations_tested": 0, "results": []}

        required_ids = {int(item) for item in required_entry_ids or []}
        required_sets = {tuple(sorted(str(element).strip().capitalize() for element in item if str(element).strip())) for item in required_element_sets or []}
        if len(required_ids) > max_phases:
            return {"candidate_count": len(candidates), "combinations_tested": 0, "results": [], "constraint_error": "More required MPIDs than the maximum number of phases."}

        columns = [self._response_column(candidate, len(x)) for candidate in candidates]
        results: List[Dict] = []
        tested = 0
        contribution_threshold_rejections = 0
        for size in range(1, min(max_phases, len(candidates)) + 1):
            for indices in combinations(range(len(candidates)), size):
                selected_candidates = [candidates[index] for index in indices]
                selected_ids = {candidate["entry_id"] for candidate in selected_candidates}
                selected_sets = {tuple(sorted(str(element).strip().capitalize() for element in candidate.get("elements", []) if str(element).strip())) for candidate in selected_candidates}
                if not required_ids.issubset(selected_ids) or not required_sets.issubset(selected_sets):
                    continue
                matrix = np.column_stack([columns[index] for index in indices])
                if not np.any(matrix):
                    continue
                coefficients, _ = nnls(matrix, y)
                predicted = matrix @ coefficients
                sse = float(np.sum((y - predicted) ** 2))
                # Penalize redundant phases very lightly so a real minor phase
                # can still be selected, while duplicates do not win by noise.
                score = 100.0 * max(0.0, 1.0 - sse / float(np.sum(y ** 2))) - 0.75 * (size - 1)
                force_keep = selected_ids.intersection(required_ids) | {
                    candidate["entry_id"] for candidate in selected_candidates
                    if tuple(sorted(str(element).strip().capitalize() for element in candidate.get("elements", []) if str(element).strip())) in required_sets
                }
                phases, contributions = self._phase_payload(selected_candidates, matrix, coefficients, predicted, force_keep)
                if not phases:
                    continue
                # A user-specified MPID is a required phase, not merely a
                # label carried by an NNLS-zero/minor component.  Reject the
                # combination unless every required MPID contributes at least
                # the configured relative diffraction threshold.
                required_phase_contributions = {
                    int(phase["entry_id"]): float(phase["relative_contribution"])
                    for phase in phases
                    if int(phase["entry_id"]) in required_ids
                }
                if any(
                    required_phase_contributions.get(entry_id, 0.0) < minimum_required_contribution_percent
                    for entry_id in required_ids
                ):
                    contribution_threshold_rejections += 1
                    continue
                results.append({
                    "score": float(score),
                    "residual_sum_squares": sse,
                    "explained_intensity_percent": float(100.0 * predicted.sum() / y.sum()),
                    "n_phases": len(phases),
                    "phases": phases,
                    "peak_attribution": self._peak_attribution(x, y, predicted, contributions, phases),
                })
                tested += 1

        # A valid single-phase candidate must never disappear merely because a
        # combination fit was numerically rejected. This is both a useful
        # fallback and a clear baseline for interpreting multi-phase gains.
        if not results and not required_ids and not required_sets:
            for candidate, column in zip(candidates, columns):
                matrix = column.reshape(-1, 1)
                coefficients, _ = nnls(matrix, y)
                predicted = matrix @ coefficients
                phases, contributions = self._phase_payload([candidate], matrix, coefficients, predicted, required_ids)
                if not phases:
                    continue
                sse = float(np.sum((y - predicted) ** 2))
                results.append({
                    "score": float(100.0 * max(0.0, 1.0 - sse / float(np.sum(y ** 2)))),
                    "residual_sum_squares": sse,
                    "explained_intensity_percent": float(100.0 * predicted.sum() / y.sum()),
                    "n_phases": 1, "phases": phases,
                    "peak_attribution": self._peak_attribution(x, y, predicted, contributions, phases),
                })

        results.sort(key=lambda item: (item["score"], item["explained_intensity_percent"], -item["n_phases"]), reverse=True)
        # A tested combination can contain one or more NNLS-zero phases.  They
        # are omitted from ``phases`` for display, which otherwise makes e.g.
        # A, A+B(0%), and A+C(0%) appear as repeated AutoMix results.  Keep
        # only the highest-ranked instance of each effective database-entry
        # combination.
        unique_results = []
        seen_combinations = set()
        for item in results:
            key = tuple(sorted(str(phase.get("entry_id")) for phase in item["phases"]))
            if not key or key in seen_combinations:
                continue
            seen_combinations.add(key)
            unique_results.append(item)
        response = {
            "candidate_count": len(candidates),
            "known_candidate_count": len(known_candidates),
            "combinations_tested": tested,
            "results": unique_results[:top_n],
            "minimum_required_contribution_percent": minimum_required_contribution_percent if required_ids else None,
            "disclaimer": "Contributions are relative diffraction contributions, not quantitative weight fractions.",
        }
        if not response["results"] and contribution_threshold_rejections:
            response["constraint_error"] = "required_contribution_below_minimum"
        return response

    def _known_entry_candidates(
        self,
        x: np.ndarray,
        y: np.ndarray,
        database: Dict,
        known_entry_ids: Optional[Sequence[int]],
        candidate_pool: int,
        required_element_sets: Optional[Sequence[Sequence[str]]] = None,
        required_entry_ids: Optional[Sequence[int]] = None,
    ) -> List[Dict]:
        """Score user-constrained entries and preserve them in the pool.

        Exact-element constraints may resolve to several polymorphs; these are
        scored normally and capped to the same practical pool size as ordinary
        retrieval candidates. An MPID therefore identifies a database entry,
        whereas an element-set constraint identifies a chemically exact family.
        """
        if not known_entry_ids:
            return []
        database = normalize_database_package(database)
        entries = database["xrd_database"]
        candidates = []
        seen = set()
        for raw_id in known_entry_ids:
            try:
                entry_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if entry_id in seen or entry_id not in entries:
                continue
            seen.add(entry_id)
            entry = entries[entry_id]
            metrics = self.matcher.match_single_entry(x, y, entry)
            candidates.append({
                "entry_id": entry_id, "mpid": entry.get("mpid"),
                "formula": entry.get("formula"), "elements": entry.get("elements", []),
                "spacegroup": entry.get("spacegroup_number"),
                "spacegroup_symbol": entry.get("spacegroup_symbol"),
                "known_constraint": True, **metrics,
            })
        candidates.sort(
            key=lambda item: (item["score"], item["n_matched_peaks"], item["fom"], item["experimental_coverage"]),
            reverse=True,
        )
        required_sets = {
            tuple(sorted(str(element).strip().capitalize() for element in item if str(element).strip()))
            for item in required_element_sets or []
        }
        # Retain the best entry from every required exact-element family before
        # filling the rest of the practical candidate pool. This guarantees
        # that multiple user-entered known phases are all available to the
        # combination generator, even when one family has a weaker score.
        selected = []
        selected_ids = set()
        for entry_id in {int(item) for item in required_entry_ids or []}:
            match = next((item for item in candidates if item["entry_id"] == entry_id), None)
            if match is not None:
                selected.append(match)
                selected_ids.add(match["entry_id"])
        for element_set in required_sets:
            match = next(
                (item for item in candidates if tuple(sorted(str(element).strip().capitalize() for element in item.get("elements", []) if str(element).strip())) == element_set),
                None,
            )
            if match is not None:
                selected.append(match)
                selected_ids.add(match["entry_id"])
        for item in candidates:
            if len(selected) >= candidate_pool and item["entry_id"] not in selected_ids:
                break
            if item["entry_id"] not in selected_ids:
                selected.append(item)
                selected_ids.add(item["entry_id"])
        return selected

    def _single_phase_candidates(
        self, x: np.ndarray, y: np.ndarray, database: Dict,
        elements: Optional[Sequence[str]], element_filter_mode: str, candidate_pool: int,
    ) -> List[Dict]:
        """Retrieve candidates with a multi-phase-aware element scope.

        A single-phase query for ``Ti,O,Si`` normally requires every candidate
        to contain all three elements.  For a mixture, however, TiO2 and SiO2
        are both valid component phases, so each component must be a *subset*
        of the supplied element scope instead.
        """
        if not elements:
            return self.matcher.match_pattern(x, y, database, top_n=candidate_pool)
        database = normalize_database_package(database)
        allowed = {str(element).strip().capitalize() for element in elements if str(element).strip()}
        entries = database["xrd_database"]
        results = []
        for entry_id, entry in entries.items():
            phase_elements = set(entry.get("elements", []))
            if not phase_elements or not phase_elements.issubset(allowed):
                continue
            metrics = self.matcher.match_single_entry(x, y, entry)
            if metrics["score"] <= 0:
                continue
            results.append({
                "entry_id": entry_id, "mpid": entry.get("mpid"),
                "formula": entry.get("formula"), "elements": entry.get("elements", []),
                "spacegroup": entry.get("spacegroup_number"),
                "spacegroup_symbol": entry.get("spacegroup_symbol"), **metrics,
            })
        results.sort(
            key=lambda item: (item["score"], item["n_matched_peaks"], item["fom"], item["experimental_coverage"]),
            reverse=True,
        )
        return results[:candidate_pool]

    @staticmethod
    def _response_column(candidate: Dict, n_peaks: int) -> np.ndarray:
        column = np.zeros(n_peaks, dtype=float)
        for match in candidate.get("peak_matches", []):
            index = int(match["exp_index"])
            if 0 <= index < n_peaks:
                column[index] = max(column[index], float(match.get("db_intensity", 0.0)))
        maximum = float(column.max())
        return column / maximum if maximum > 0 else column

    @staticmethod
    def _phase_payload(
        candidates: List[Dict], matrix: np.ndarray, coefficients: np.ndarray, predicted: np.ndarray,
        force_keep_entry_ids: Optional[Sequence[int]] = None,
    ):
        contributions = matrix * coefficients.reshape(1, -1)
        totals = contributions.sum(axis=0)
        total = float(predicted.sum())
        phases = []
        kept = []
        force_keep = {int(item) for item in force_keep_entry_ids or []}
        for index, (candidate, coefficient, contribution) in enumerate(zip(candidates, coefficients, totals)):
            if (coefficient <= 1e-10 or contribution <= 1e-10) and candidate["entry_id"] not in force_keep:
                continue
            phases.append({
                "entry_id": candidate["entry_id"], "mpid": candidate.get("mpid"),
                "formula": candidate.get("formula"), "elements": candidate.get("elements", []),
                "spacegroup": candidate.get("spacegroup"),
                "spacegroup_symbol": candidate.get("spacegroup_symbol"),
                "estimated_shift": candidate.get("estimated_shift", 0.0),
                "single_phase_score": candidate.get("score", 0.0),
                "relative_contribution": float(100.0 * contribution / total) if total > 0 else 0.0,
                "known_constraint": candidate["entry_id"] in force_keep,
            })
            kept.append(index)
        return phases, contributions[:, kept] if kept else np.empty((len(predicted), 0))

    @staticmethod
    def _peak_attribution(x, y, predicted, contributions, phases):
        rows = []
        for index, (position, intensity, fitted) in enumerate(zip(x, y, predicted)):
            values = contributions[index] if contributions.size else np.array([])
            if values.size and fitted > 0:
                winner = int(np.argmax(values))
                label = phases[winner]["formula"]
                overlap = int(np.count_nonzero(values >= 0.2 * values.max())) > 1
            else:
                label, overlap = None, False
            rows.append({
                "two_theta": float(position), "intensity": float(intensity), "fitted_intensity": float(fitted),
                "residual_intensity": float(max(0.0, intensity - fitted)),
                "assigned_formula": label, "overlap": overlap,
            })
        return rows
