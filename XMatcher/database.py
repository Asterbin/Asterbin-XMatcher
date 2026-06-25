"""Database processing and offline XRD database construction."""

from __future__ import annotations

import json
import logging
import pickle
from collections import defaultdict
from itertools import islice
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

import numpy as np
from tqdm import tqdm

logger = logging.getLogger(__name__)


class DatabaseProcessor:
    """Read crystal structures from an ASE database."""

    def __init__(self, db_path: str):
        from ase.db import connect

        self.db_path = db_path
        self.db = connect(db_path)

    def get_total_entries(self) -> int:
        return len(self.db)

    def get_atoms(self, entry_id: int):
        try:
            return self.db.get_atoms(id=entry_id)
        except Exception as exc:
            logger.warning("Failed to get atoms for entry %s: %s", entry_id, exc)
            return None

    def get_structure_info(self, entry_id: int) -> Optional[Dict]:
        try:
            row = self.db.get(id=entry_id)
            atoms = row.toatoms()
            symbols = atoms.get_chemical_symbols()
            elements = sorted(set(symbols))
            spacegroup_number, spacegroup_symbol = _get_spacegroup_info(atoms)

            mpid = row.get("mpid", None) or row.get("material_id", None) or row.get("id", None)
            return {
                "entry_id": entry_id,
                "mpid": mpid,
                "formula": atoms.get_chemical_formula(),
                "elements": elements,
                "n_atoms": len(atoms),
                "chemical_symbols": symbols,
                "spacegroup_number": spacegroup_number,
                "spacegroup_symbol": spacegroup_symbol,
                "cell": atoms.get_cell(),
                "scaled_positions": atoms.get_scaled_positions(),
                "cartesian_positions": atoms.get_positions(),
                "atoms": atoms,
            }
        except Exception as exc:
            logger.warning("Failed to extract structure info for entry %s: %s", entry_id, exc)
            return None

    def iterate_all_entries(self) -> Iterable[Tuple[int, Dict]]:
        for row in self.db.select():
            info = self.get_structure_info(row.id)
            if info is not None:
                yield row.id, info

    def close(self) -> None:
        self.db = None


class XRDCalculator:
    """Calculate theoretical powder XRD peaks from crystal structures."""

    def __init__(
        self,
        wavelength: str = "CuKa",
        two_theta_range: Tuple[float, float] = (10.0, 90.0),
        min_d_spacing: float = 0.5,
    ):
        self.wavelength = wavelength
        self.two_theta_range = two_theta_range
        self.min_d_spacing = min_d_spacing
        from pymatgen.analysis.diffraction.xrd import XRDCalculator as PymatgenXRDCalculator
        from pymatgen.io.ase import AseAtomsAdaptor

        self.xrd_calc = PymatgenXRDCalculator(wavelength=wavelength)
        self._adaptor = AseAtomsAdaptor()

    def calculate_pattern(self, atoms) -> Optional[Dict]:
        try:
            structure = self._adaptor.get_structure(atoms)
            pattern = self.xrd_calc.get_pattern(structure, two_theta_range=self.two_theta_range)
            two_theta = np.asarray(pattern.x, dtype=float)
            intensities = np.asarray(pattern.y, dtype=float)
            d_spacings = _extract_d_spacings(pattern)
            valid = d_spacings >= self.min_d_spacing
            return {
                "two_theta": two_theta[valid],
                "intensities": intensities[valid],
                "hkls": [pattern.hkls[i] for i in range(len(pattern.hkls)) if valid[i]],
                "d_spacings": d_spacings[valid],
            }
        except Exception as exc:
            logger.warning("XRD calculation failed: %s", exc)
            return None

    def extract_top_peaks(self, pattern: Dict, n_peaks: int = 30, normalize: bool = True) -> List[Dict]:
        if not pattern or len(pattern["two_theta"]) == 0:
            return []
        intensities = np.asarray(pattern["intensities"], dtype=float)
        if normalize and intensities.size and intensities.max() > 0:
            intensities = 100.0 * intensities / intensities.max()

        peaks = []
        for idx, two_theta in enumerate(pattern["two_theta"]):
            peaks.append(
                {
                    "two_theta": float(two_theta),
                    "intensity": float(intensities[idx]),
                    "hkl": pattern["hkls"][idx],
                    "d_spacing": float(pattern["d_spacings"][idx]),
                }
            )
        peaks.sort(key=lambda peak: peak["intensity"], reverse=True)
        return peaks[:n_peaks]

    def calculate_and_extract_peaks(self, atoms, n_peaks: int = 30, normalize: bool = True) -> List[Dict]:
        pattern = self.calculate_pattern(atoms)
        return self.extract_top_peaks(pattern, n_peaks=n_peaks, normalize=normalize) if pattern else []

    def format_peaks_for_storage(self, peaks: List[Dict]) -> Dict:
        return {
            "positions": [peak["two_theta"] for peak in peaks],
            "intensities": [peak["intensity"] for peak in peaks],
            "hkls": [peak["hkl"] for peak in peaks],
            "d_spacings": [peak["d_spacing"] for peak in peaks],
        }


def _process_entry_worker(args: Tuple[int, Dict, str, int, Tuple[float, float], float, bool]) -> Tuple[int, Optional[Dict]]:
    entry_id, info, wavelength, n_peaks, two_theta_range, min_d_spacing, skip_errors = args
    try:
        calculator = XRDCalculator(
            wavelength=wavelength,
            two_theta_range=two_theta_range,
            min_d_spacing=min_d_spacing,
        )
        peaks = calculator.calculate_and_extract_peaks(info["atoms"], n_peaks=n_peaks, normalize=True)
        if not peaks:
            return entry_id, None
        return entry_id, _make_entry_record(entry_id, info, calculator.format_peaks_for_storage(peaks))
    except Exception as exc:
        if not skip_errors:
            raise
        logger.warning("Worker failed for entry %s: %s", entry_id, exc)
        return entry_id, None


def _make_entry_record(entry_id: int, info: Dict, peak_data: Dict) -> Dict:
    return {
        "entry_id": entry_id,
        "mpid": info["mpid"],
        "formula": info["formula"],
        "elements": info["elements"],
        "n_atoms": info["n_atoms"],
        "spacegroup_number": info["spacegroup_number"],
        "spacegroup_symbol": info["spacegroup_symbol"],
        "peaks": peak_data,
    }


class DatabaseBuilder:
    """Build a searchable XRD peak database from an ASE crystal database."""

    schema_version = 2

    def __init__(
        self,
        db_path: str,
        wavelength: str = "CuKa",
        n_peaks: int = 30,
        two_theta_range: Tuple[float, float] = (10.0, 90.0),
        min_d_spacing: float = 0.5,
    ):
        self.db_path = db_path
        self.wavelength = wavelength
        self.n_peaks = n_peaks
        self.two_theta_range = two_theta_range
        self.min_d_spacing = min_d_spacing
        self.db_processor = DatabaseProcessor(db_path)
        self.xrd_calculator = XRDCalculator(wavelength, two_theta_range, min_d_spacing)
        self.xrd_database: Dict[int, Dict] = {}
        self.element_index: Dict[Tuple[str, ...], List[int]] = {}
        self.element_inverted_index: Dict[str, List[int]] = {}

    def process_single_entry(self, entry_id: int) -> Optional[Dict]:
        info = self.db_processor.get_structure_info(entry_id)
        if info is None:
            return None
        peaks = self.xrd_calculator.calculate_and_extract_peaks(info["atoms"], self.n_peaks, normalize=True)
        if not peaks:
            return None
        return _make_entry_record(entry_id, info, self.xrd_calculator.format_peaks_for_storage(peaks))

    def build_database(
        self,
        output_path: str = "xrd_database.pkl",
        max_entries: Optional[int] = None,
        skip_errors: bool = True,
        save_interval: int = 1000,
        save_json: bool = False,
    ) -> Dict:
        self._load_existing(output_path)
        processed_since_save = 0

        total_entries = self._entry_progress_total(max_entries)

        for entry_id, _ in tqdm(
            self._iter_entries(max_entries),
            desc="Building XRD database",
            unit="entry",
            total=total_entries,
            dynamic_ncols=True,
        ):
            if entry_id in self.xrd_database:
                continue
            try:
                record = self.process_single_entry(entry_id)
                if record is not None:
                    self._store_entry(entry_id, record)
                    processed_since_save += 1
            except Exception:
                if not skip_errors:
                    raise
                logger.exception("Failed to process entry %s", entry_id)

            if save_interval > 0 and processed_since_save >= save_interval:
                self.save_database(output_path, save_json=False)
                processed_since_save = 0

        self.save_database(output_path, save_json=save_json)
        return self.package_database()

    def build_database_parallel(
        self,
        output_path: str = "xrd_database.pkl",
        max_entries: Optional[int] = None,
        skip_errors: bool = True,
        n_workers: Optional[int] = None,
        batch_size: int = 5000,
        save_interval: int = 1000,
        save_json: bool = False,
    ) -> Dict:
        self._load_existing(output_path)
        n_workers = n_workers or cpu_count()
        total_entries = self._entry_progress_total(max_entries)
        processed_since_save = 0

        with tqdm(desc="Building XRD database", unit="entry", total=total_entries, dynamic_ncols=True) as pbar:
            pending_args = _pending_worker_args(
                self._iter_entries(max_entries),
                pbar,
                self.xrd_database,
                self,
                skip_errors,
            )
            for batch in _batched(pending_args, batch_size):
                with Pool(processes=n_workers) as pool:
                    for entry_id, record in pool.map(_process_entry_worker, batch):
                        if record is not None:
                            self._store_entry(entry_id, record)
                            processed_since_save += 1
                        pbar.update(1)
                if save_interval > 0 and processed_since_save >= save_interval:
                    self.save_database(output_path, save_json=False)
                    processed_since_save = 0

        self.save_database(output_path, save_json=save_json)
        return self.package_database()

    def package_database(self) -> Dict:
        self._rebuild_indexes()
        return {
            "xrd_database": self.xrd_database,
            "element_index": self.element_index,
            "element_inverted_index": self.element_inverted_index,
            "metadata": {
                "schema_version": self.schema_version,
                "source_db": self.db_path,
                "wavelength": self.wavelength,
                "n_peaks": self.n_peaks,
                "two_theta_range": self.two_theta_range,
                "min_d_spacing": self.min_d_spacing,
                "total_entries": len(self.xrd_database),
            },
        }

    def save_database(self, output_path: str, save_json: bool = False) -> None:
        package = self.package_database()
        with open(output_path, "wb") as file:
            pickle.dump(package, file, protocol=pickle.HIGHEST_PROTOCOL)
        if save_json:
            json_path = Path(output_path).with_suffix(".json")
            with open(json_path, "w", encoding="utf-8") as file:
                json.dump(_json_ready_database(package), file, indent=2, default=str)

    @staticmethod
    def load_database(database_path: str) -> Dict:
        with open(database_path, "rb") as file:
            database = pickle.load(file)
        return normalize_database_package(database)

    def _collect_entries(self, max_entries: Optional[int]) -> List[Tuple[int, Dict]]:
        return list(self._iter_entries(max_entries))

    def _iter_entries(self, max_entries: Optional[int]) -> Iterator[Tuple[int, Dict]]:
        for index, (entry_id, info) in enumerate(self.db_processor.iterate_all_entries()):
            if max_entries is not None and index >= max_entries:
                break
            yield entry_id, info

    def _entry_progress_total(self, max_entries: Optional[int]) -> int:
        total_entries = self.db_processor.get_total_entries()
        if max_entries is not None:
            return min(max_entries, total_entries)
        return total_entries

    def _load_existing(self, output_path: str) -> None:
        path = Path(output_path)
        if not path.exists():
            return
        database = self.load_database(output_path)
        self.xrd_database = database["xrd_database"]
        self.element_index = database.get("element_index", {})
        self.element_inverted_index = database.get("element_inverted_index", {})

    def _store_entry(self, entry_id: int, record: Dict) -> None:
        self.xrd_database[entry_id] = record
        key = tuple(sorted(_normalize_element_symbol(element) for element in record.get("elements", [])))
        self.element_index.setdefault(key, [])
        if entry_id not in self.element_index[key]:
            self.element_index[key].append(entry_id)
        for element in key:
            self.element_inverted_index.setdefault(element, [])
            if entry_id not in self.element_inverted_index[element]:
                self.element_inverted_index[element].append(entry_id)

    def _rebuild_indexes(self) -> None:
        element_index: Dict[Tuple[str, ...], List[int]] = defaultdict(list)
        inverted: Dict[str, List[int]] = defaultdict(list)
        for entry_id, entry in self.xrd_database.items():
            key = tuple(sorted(_normalize_element_symbol(element) for element in entry.get("elements", [])))
            element_index[key].append(entry_id)
            for element in key:
                inverted[element].append(entry_id)
        self.element_index = {key: sorted(ids) for key, ids in element_index.items()}
        self.element_inverted_index = {element: sorted(ids) for element, ids in inverted.items()}


def normalize_database_package(database: Dict) -> Dict:
    """Normalize old and new database packages into the current in-memory format."""
    if "xrd_database" not in database:
        database = {"xrd_database": database}

    xrd_database = database.get("xrd_database", {})
    normalized = {
        "xrd_database": xrd_database,
        "element_index": database.get("element_index", {}),
        "element_inverted_index": database.get("element_inverted_index", {}),
        "metadata": database.get("metadata", {}),
    }

    if not normalized["element_index"] or not normalized["element_inverted_index"]:
        element_index: Dict[Tuple[str, ...], List[int]] = defaultdict(list)
        inverted: Dict[str, List[int]] = defaultdict(list)
        for entry_id, entry in xrd_database.items():
            key = tuple(sorted(_normalize_element_symbol(element) for element in entry.get("elements", [])))
            element_index[key].append(entry_id)
            for element in key:
                inverted[element].append(entry_id)
        normalized["element_index"] = {key: sorted(ids) for key, ids in element_index.items()}
        normalized["element_inverted_index"] = {element: sorted(ids) for element, ids in inverted.items()}

    normalized["metadata"].setdefault("schema_version", 1)
    normalized["metadata"].setdefault("total_entries", len(xrd_database))
    return normalized


def _json_ready_database(database: Dict) -> Dict:
    package = dict(database)
    package["element_index"] = {
        "|".join(key) if isinstance(key, tuple) else str(key): value
        for key, value in database.get("element_index", {}).items()
    }
    return package


def _extract_d_spacings(pattern) -> np.ndarray:
    raw = getattr(pattern, "d_hkls", None)
    if raw is None:
        raw = [hkl_group[0].get("d_hkl") for hkl_group in pattern.hkls]

    values = []
    for item in raw:
        if isinstance(item, dict):
            values.append(item.get("d_hkl"))
        elif isinstance(item, (list, tuple)) and item and isinstance(item[0], dict):
            values.append(item[0].get("d_hkl"))
        else:
            values.append(item)
    return np.asarray(values, dtype=float)


def _get_spacegroup_info(atoms) -> Tuple[Optional[int], Optional[str]]:
    try:
        import spglib

        dataset = spglib.get_symmetry_dataset(
            (atoms.get_cell(), atoms.get_scaled_positions(), atoms.get_atomic_numbers()),
            symprec=1e-2,
        )
        if dataset is None:
            return None, None
        if isinstance(dataset, dict):
            return dataset.get("number"), dataset.get("international")
        return getattr(dataset, "number", None), getattr(dataset, "international", None)
    except Exception:
        return None, None


def _pending_worker_args(
    entries: Iterable[Tuple[int, Dict]],
    progress,
    existing_entries: Dict[int, Dict],
    builder: DatabaseBuilder,
    skip_errors: bool,
) -> Iterator[Tuple]:
    for entry_id, info in entries:
        if entry_id in existing_entries:
            progress.update(1)
            continue
        yield (
            entry_id,
            info,
            builder.wavelength,
            builder.n_peaks,
            builder.two_theta_range,
            builder.min_d_spacing,
            skip_errors,
        )


def _batched(iterable: Iterable, batch_size: int) -> Iterator[List]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    iterator = iter(iterable)
    while True:
        batch = list(islice(iterator, batch_size))
        if not batch:
            break
        yield batch


def _normalize_element_symbol(element: str) -> str:
    element = str(element).strip()
    if not element:
        return element
    return element[0].upper() + element[1:].lower()
