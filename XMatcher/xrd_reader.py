"""Readers and utilities for experimental XRD data."""

from __future__ import annotations

import logging
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
        errors = []
        for delimiter in [",", "\t", r"\s+", ";"]:
            for header in ["infer", None]:
                try:
                    data = self.read_csv(file_path, delimiter=delimiter, header=header)
                    if len(data["two_theta"]) >= 2:
                        return data
                except Exception as exc:
                    errors.append(f"{delimiter!r}/{header!r}: {exc}")
        raise ValueError(f"Could not read XRD file {file_path}. Tried common delimiters. {errors[-1]}")

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
