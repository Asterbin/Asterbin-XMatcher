"""High-level API for XRD phase retrieval."""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

import numpy as np

from .database import normalize_database_package
from .matcher import XRDMatcher
from .peak_detector import PeakDetector
from .xrd_reader import XRDReader

logger = logging.getLogger(__name__)


class XRDRetriever:
    """
    High-level interface combining file reading, peak detection and database matching.

    Parameters are intentionally conservative for experimental data. For fast demos,
    reduce ``n_peaks`` and ``max_shift``; for production searches, keep more peaks.
    """

    def __init__(
        self,
        database_path: str,
        position_tolerance: float = 0.2,
        min_peak_height: float = 3.0,
        min_peak_prominence: float = 2.0,
        n_peaks: int = 20,
        scoring_method: str = "hybrid",
        intensity_weight: float = 0.15,
        position_weight: float = 0.85,
        min_matched_peaks: int = 2,
        max_shift: float = 0.5,
        shift_step: float = 0.02,
    ):
        self.database_path = database_path
        self.n_peaks = n_peaks
        self.scoring_method = scoring_method
        self.database = self._load_database(database_path)
        self.reader = XRDReader()
        self.peak_detector = PeakDetector(
            min_peak_height=min_peak_height,
            min_peak_prominence=min_peak_prominence,
        )
        self.matcher = XRDMatcher(
            position_tolerance=position_tolerance,
            intensity_weight=intensity_weight,
            position_weight=position_weight,
            min_matched_peaks=min_matched_peaks,
            scoring_method=scoring_method,
            max_shift=max_shift,
            shift_step=shift_step,
        )

    def retrieve_from_file(
        self,
        xrd_file: Union[str, Path],
        elements: Optional[Sequence[str]] = None,
        top_n: int = 10,
        auto_detect_format: bool = True,
        element_filter_mode: str = "contains",
    ) -> List[Dict]:
        xrd_data = self.reader.read_auto(xrd_file) if auto_detect_format else self.reader.read_csv(xrd_file)
        peaks = self.detect_peaks(xrd_data["two_theta"], xrd_data["intensity"])
        return self.retrieve_from_peak_dicts(
            peaks,
            elements=elements,
            top_n=top_n,
            element_filter_mode=element_filter_mode,
        )

    def detect_peaks(self, two_theta: Sequence[float], intensity: Sequence[float]) -> List[Dict]:
        return self.peak_detector.get_top_peaks(
            np.asarray(two_theta, dtype=float),
            np.asarray(intensity, dtype=float),
            n_peaks=self.n_peaks,
            preprocess=True,
        )

    def retrieve_from_peak_dicts(
        self,
        peaks: List[Dict],
        elements: Optional[Sequence[str]] = None,
        top_n: int = 10,
        element_filter_mode: str = "contains",
    ) -> List[Dict]:
        positions, intensities = self.peak_detector.extract_peak_positions_and_intensities(peaks)
        return self.retrieve_from_peaks(
            positions,
            intensities,
            elements=elements,
            top_n=top_n,
            element_filter_mode=element_filter_mode,
        )

    def retrieve_from_peaks(
        self,
        peak_positions: Sequence[float],
        peak_intensities: Sequence[float],
        elements: Optional[Sequence[str]] = None,
        top_n: int = 10,
        element_filter_mode: str = "contains",
    ) -> List[Dict]:
        return self.matcher.match_pattern(
            peak_positions,
            peak_intensities,
            self.database,
            elements=elements,
            top_n=top_n,
            element_filter_mode=element_filter_mode,
        )

    def get_entry_details(self, entry_id: int) -> Optional[Dict]:
        return self.database["xrd_database"].get(entry_id)

    def search_by_formula(self, formula: str) -> List[Dict]:
        return [
            entry
            for entry in self.database["xrd_database"].values()
            if entry.get("formula") == formula
        ]

    def search_by_elements(
        self,
        elements: Sequence[str],
        element_filter_mode: str = "contains",
    ) -> List[Dict]:
        ids = self.matcher.filter_by_elements(self.database, elements, mode=element_filter_mode)
        return [self.database["xrd_database"][entry_id] for entry_id in ids]

    def get_database_statistics(self) -> Dict:
        xrd_db = self.database["xrd_database"]
        metadata = self.database.get("metadata", {})
        all_elements = set()
        formulas = []
        for entry in xrd_db.values():
            all_elements.update(entry.get("elements", []))
            formulas.append(entry.get("formula"))
        return {
            "total_entries": len(xrd_db),
            "unique_elements": sorted(all_elements),
            "n_unique_elements": len(all_elements),
            "unique_formulas": len(set(formulas)),
            "wavelength": metadata.get("wavelength"),
            "n_peaks_per_entry": metadata.get("n_peaks"),
            "two_theta_range": metadata.get("two_theta_range"),
            "schema_version": metadata.get("schema_version"),
        }

    def print_results(self, results: List[Dict], max_results: int = 10) -> None:
        if not results:
            print("No matches found.")
            return
        print(f"\nTop {min(len(results), max_results)} Matches")
        print("=" * 96)
        for index, result in enumerate(results[:max_results], 1):
            print(
                f"{index:>2}. score={result['score']:.2f} "
                f"weighted={result['weighted_score']:.2f} "
                f"fom={result['fom']:.2f} "
                f"matched={result['n_matched_peaks']} "
                f"shift={result['estimated_shift']:+.3f} "
                f"formula={result['formula']} mpid={result['mpid']}"
            )
        print("=" * 96)

    def _load_database(self, database_path: str) -> Dict:
        path = Path(database_path)
        if not path.exists():
            raise FileNotFoundError(f"XRD database not found: {database_path}")
        with open(path, "rb") as file:
            database = pickle.load(file)
        normalized = normalize_database_package(database)
        logger.info("Loaded XRD database with %d entries", len(normalized["xrd_database"]))
        return normalized
