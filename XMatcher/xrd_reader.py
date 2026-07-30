"""Readers and utilities for experimental XRD data."""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class XRDReader:
    """Read experimental XRD data from common two-column text formats."""

    def read_csv(
        self,
        file_path: Union[str, Path],
        two_theta_col: int = 0,
        intensity_col: int = 1,
        delimiter: str = ",",
        skip_rows: int = 0,
        header: Optional[int] = "infer",
    ) -> Dict[str, np.ndarray]:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"XRD file not found: {file_path}")

        try:
            df = pd.read_csv(
                file_path,
                sep=delimiter,
                skiprows=skip_rows,
                header=header,
                engine="python",
                comment="#",
            )
            if df.shape[1] < 2:
                raise ValueError("XRD data must contain at least two columns")
            two_theta = df.iloc[:, two_theta_col].to_numpy(dtype=float)
            intensity = df.iloc[:, intensity_col].to_numpy(dtype=float)
        except Exception as pandas_error:
            logger.debug("pandas failed to read %s: %s", file_path, pandas_error)
            data = np.loadtxt(file_path, delimiter=delimiter, skiprows=skip_rows)
            if data.ndim != 2 or data.shape[1] < 2:
                raise ValueError("XRD data must contain at least two columns") from pandas_error
            two_theta = data[:, two_theta_col].astype(float)
            intensity = data[:, intensity_col].astype(float)

        return self._clean(two_theta, intensity, file_path)

    def read_auto(self, file_path: Union[str, Path]) -> Dict[str, np.ndarray]:
        file_path = Path(file_path)
        suffix = file_path.suffix.lower()
        if suffix == ".json":
            return self._read_json(file_path)
        if suffix in {".xml", ".xrdml"}:
            return self._read_xml(file_path)

        errors = []
        for delimiter in [",", "\t", r"\s+", ";"]:
            # Trying ``header="infer"`` first makes pandas treat a numeric
            # first row as column names, silently dropping that measurement.
            # A genuine textual header fails this no-header attempt and is
            # handled by the following inferred-header attempt.
            for header in [None, "infer"]:
                try:
                    data = self.read_csv(file_path, delimiter=delimiter, header=header)
                    if len(data["two_theta"]) >= 2:
                        return data
                except Exception as exc:
                    errors.append(f"{delimiter!r}/{header!r}: {exc}")
        try:
            return self._read_numeric_text(file_path)
        except Exception as exc:
            errors.append(f"numeric-text fallback: {exc}")
        raise ValueError(f"Could not read XRD file {file_path}. Tried common delimiters. {errors[-1]}")

    def _read_numeric_text(self, file_path: Path) -> Dict[str, np.ndarray]:
        """Read vendor-style ASCII files with metadata before two/three-column data."""
        rows = []
        for line in file_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "//", ";", "_")):
                continue
            values = re.split(r"[,;\t\s]+", stripped)
            if len(values) < 2:
                continue
            try:
                rows.append((float(values[0]), float(values[1])))
            except ValueError:
                continue
        if len(rows) < 2:
            raise ValueError("no two-column numeric rows found")
        return self._clean(
            np.asarray([row[0] for row in rows]), np.asarray([row[1] for row in rows]), file_path
        )

    def _read_json(self, file_path: Path) -> Dict[str, np.ndarray]:
        """Read common two-column JSON layouts used by local instruments and APIs."""
        data = json.loads(file_path.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            positions = data.get("two_theta", data.get("angle", data.get("x")))
            intensities = data.get("intensity", data.get("counts", data.get("y")))
            if positions is not None and intensities is not None:
                return self._clean(np.asarray(positions, dtype=float), np.asarray(intensities, dtype=float), file_path)
        if isinstance(data, list):
            rows = []
            for item in data:
                if isinstance(item, dict):
                    x = item.get("two_theta", item.get("angle", item.get("x")))
                    y = item.get("intensity", item.get("counts", item.get("y")))
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    x, y = item[:2]
                else:
                    continue
                rows.append((float(x), float(y)))
            if rows:
                return self._clean(
                    np.asarray([row[0] for row in rows]), np.asarray([row[1] for row in rows]), file_path
                )
        raise ValueError("JSON must contain two_theta/intensity arrays or two-column rows")

    def _read_xml(self, file_path: Path) -> Dict[str, np.ndarray]:
        """Read simple XML and XRDML scans, including documents with XML namespaces."""
        root = ET.parse(file_path).getroot()

        def local_name(node) -> str:
            return node.tag.rsplit("}", 1)[-1].lower()

        def numbers(text) -> np.ndarray:
            return np.asarray(
                [float(value) for value in re.split(r"[,;\s]+", (text or "").strip()) if value], dtype=float
            )

        nodes = list(root.iter())
        intensity_nodes = [node for node in nodes if local_name(node) in {"intensities", "intensity", "counts"}]
        position_nodes = [node for node in nodes if local_name(node) in {"positions", "position", "twotheta", "2theta"}]
        intensity_values = next((numbers(node.text) for node in intensity_nodes if numbers(node.text).size >= 2), None)
        if intensity_values is None:
            raise ValueError("no intensity values found in XML/XRDML")
        for node in position_nodes:
            position_values = numbers(node.text)
            if position_values.size == intensity_values.size:
                return self._clean(position_values, intensity_values, file_path)

        starts = [numbers(node.text) for node in nodes if local_name(node) in {"startposition", "start"}]
        ends = [numbers(node.text) for node in nodes if local_name(node) in {"endposition", "end"}]
        if starts and ends and starts[0].size and ends[0].size:
            positions = np.linspace(float(starts[0][0]), float(ends[0][0]), intensity_values.size)
            return self._clean(positions, intensity_values, file_path)
        raise ValueError("XML/XRDML needs matching positions or start/end positions")

    def normalize_intensity(self, intensity: np.ndarray, method: str = "max") -> np.ndarray:
        intensity = np.asarray(intensity, dtype=float)
        if intensity.size == 0:
            return intensity
        if method == "max":
            max_val = np.max(intensity)
            return 100.0 * intensity / max_val if max_val > 0 else intensity
        if method == "sum":
            total = np.sum(intensity)
            return intensity / total if total > 0 else intensity
        if method == "minmax":
            min_val = np.min(intensity)
            max_val = np.max(intensity)
            return (intensity - min_val) / (max_val - min_val) if max_val > min_val else intensity
        raise ValueError(f"Unknown normalization method: {method}")

    def smooth_data(
        self,
        two_theta: np.ndarray,
        intensity: np.ndarray,
        window_size: int = 5,
    ) -> Tuple[np.ndarray, np.ndarray]:
        from scipy.ndimage import uniform_filter1d

        return np.asarray(two_theta), uniform_filter1d(np.asarray(intensity), size=window_size, mode="nearest")

    def resample_data(
        self,
        two_theta: np.ndarray,
        intensity: np.ndarray,
        step: float = 0.02,
    ) -> Tuple[np.ndarray, np.ndarray]:
        from scipy.interpolate import interp1d

        two_theta = np.asarray(two_theta, dtype=float)
        intensity = np.asarray(intensity, dtype=float)
        grid = np.arange(two_theta.min(), two_theta.max() + step / 2, step)
        interpolator = interp1d(two_theta, intensity, kind="linear", bounds_error=False, fill_value=0.0)
        return grid, interpolator(grid)

    def _clean(
        self,
        two_theta: np.ndarray,
        intensity: np.ndarray,
        file_path: Path,
    ) -> Dict[str, np.ndarray]:
        two_theta = np.asarray(two_theta, dtype=float)
        intensity = np.asarray(intensity, dtype=float)

        valid = np.isfinite(two_theta) & np.isfinite(intensity)
        two_theta = two_theta[valid]
        intensity = intensity[valid]

        non_negative = intensity >= 0
        two_theta = two_theta[non_negative]
        intensity = intensity[non_negative]

        if two_theta.size < 2:
            raise ValueError(f"XRD file {file_path} does not contain enough valid points")

        order = np.argsort(two_theta)
        two_theta = two_theta[order]
        intensity = intensity[order]

        unique_theta, unique_indices = np.unique(two_theta, return_index=True)
        if unique_theta.size != two_theta.size:
            grouped = pd.DataFrame({"two_theta": two_theta, "intensity": intensity})
            grouped = grouped.groupby("two_theta", as_index=False)["intensity"].mean()
            two_theta = grouped["two_theta"].to_numpy(dtype=float)
            intensity = grouped["intensity"].to_numpy(dtype=float)

        logger.info("Read %d XRD points from %s", len(two_theta), file_path)
        return {"two_theta": two_theta, "intensity": intensity, "file_path": str(file_path)}
