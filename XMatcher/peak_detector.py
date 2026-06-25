"""Peak detection for experimental XRD spectra."""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

import numpy as np
from scipy.ndimage import gaussian_filter1d, minimum_filter1d
from scipy.signal import find_peaks, peak_widths, savgol_filter

logger = logging.getLogger(__name__)


class PeakDetector:
    """Detect robust peak positions and relative intensities from XRD spectra."""

    def __init__(
        self,
        min_peak_height: float = 3.0,
        min_peak_prominence: float = 2.0,
        min_peak_distance: float = 0.1,
        smooth_window: int = 7,
        baseline_window_fraction: float = 0.05,
    ):
        self.min_peak_height = min_peak_height
        self.min_peak_prominence = min_peak_prominence
        self.min_peak_distance = min_peak_distance
        self.smooth_window = smooth_window if smooth_window % 2 == 1 else smooth_window + 1
        self.baseline_window_fraction = baseline_window_fraction

    def preprocess_spectrum(
        self,
        two_theta: np.ndarray,
        intensity: np.ndarray,
        normalize: bool = True,
        remove_baseline: bool = True,
        smooth: bool = True,
    ) -> Tuple[np.ndarray, np.ndarray]:
        two_theta = np.asarray(two_theta, dtype=float)
        processed = np.asarray(intensity, dtype=float).copy()

        if processed.size == 0:
            return two_theta, processed

        processed[processed < 0] = 0
        if normalize:
            max_val = np.max(processed)
            if max_val > 0:
                processed = 100.0 * processed / max_val

        if remove_baseline and processed.size > 3:
            processed = self._remove_baseline(processed)

        if smooth and processed.size > self.smooth_window:
            try:
                processed = savgol_filter(processed, self.smooth_window, polyorder=2, mode="nearest")
            except Exception as exc:
                logger.debug("Savitzky-Golay smoothing failed: %s", exc)
                processed = gaussian_filter1d(processed, sigma=1.0)

        processed[processed < 0] = 0
        return two_theta, processed

    def detect_peaks(
        self,
        two_theta: np.ndarray,
        intensity: np.ndarray,
        preprocess: bool = True,
        refine_positions: bool = True,
    ) -> List[Dict]:
        two_theta = np.asarray(two_theta, dtype=float)
        intensity = np.asarray(intensity, dtype=float)
        if two_theta.size != intensity.size:
            raise ValueError("two_theta and intensity must have the same length")
        if two_theta.size < 3:
            return []

        if preprocess:
            two_theta, intensity = self.preprocess_spectrum(two_theta, intensity)

        avg_step = float(np.median(np.diff(two_theta)))
        if avg_step <= 0:
            raise ValueError("two_theta values must be strictly increasing")

        distance_indices = max(1, int(round(self.min_peak_distance / avg_step)))
        max_intensity = float(np.max(intensity)) if intensity.size else 0.0
        if max_intensity <= 0:
            return []

        peak_indices, properties = find_peaks(
            intensity,
            height=self.min_peak_height * max_intensity / 100.0,
            prominence=self.min_peak_prominence * max_intensity / 100.0,
            distance=distance_indices,
        )
        if peak_indices.size == 0:
            return []

        try:
            widths, _, _, _ = peak_widths(intensity, peak_indices, rel_height=0.5)
        except Exception:
            widths = np.ones(peak_indices.size)

        peaks = []
        for i, idx in enumerate(peak_indices):
            position = float(two_theta[idx])
            if refine_positions:
                position = self.refine_peak_position(two_theta, intensity, int(idx))
            peaks.append(
                {
                    "index": int(idx),
                    "two_theta": position,
                    "intensity": float(intensity[idx]),
                    "height": float(properties["peak_heights"][i]),
                    "prominence": float(properties["prominences"][i]),
                    "width": float(widths[i] * avg_step),
                }
            )

        peaks.sort(key=lambda peak: peak["intensity"], reverse=True)
        return peaks

    def get_top_peaks(
        self,
        two_theta: np.ndarray,
        intensity: np.ndarray,
        n_peaks: int = 20,
        preprocess: bool = True,
        normalize: bool = True,
    ) -> List[Dict]:
        peaks = self.detect_peaks(two_theta, intensity, preprocess=preprocess)
        top_peaks = peaks[:n_peaks]
        if normalize and top_peaks:
            max_intensity = max(peak["intensity"] for peak in top_peaks)
            if max_intensity > 0:
                for peak in top_peaks:
                    peak["intensity"] = 100.0 * peak["intensity"] / max_intensity
        return top_peaks

    def extract_peak_positions_and_intensities(self, peaks: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
        if not peaks:
            return np.array([], dtype=float), np.array([], dtype=float)
        return (
            np.array([peak["two_theta"] for peak in peaks], dtype=float),
            np.array([peak["intensity"] for peak in peaks], dtype=float),
        )

    def refine_peak_position(
        self,
        two_theta: np.ndarray,
        intensity: np.ndarray,
        peak_index: int,
        window: int = 3,
    ) -> float:
        start = max(0, peak_index - window)
        end = min(len(intensity), peak_index + window + 1)
        if end - start < 3:
            return float(two_theta[peak_index])

        x = two_theta[start:end]
        y = intensity[start:end]
        local_max = int(np.argmax(y))
        if local_max == 0 or local_max == len(y) - 1:
            return float(two_theta[peak_index])

        x3 = x[local_max - 1 : local_max + 2]
        y3 = y[local_max - 1 : local_max + 2]
        try:
            a, b, _ = np.polyfit(x3, y3, deg=2)
        except Exception:
            return float(two_theta[peak_index])
        if abs(a) < 1e-12:
            return float(two_theta[peak_index])

        refined = -b / (2.0 * a)
        if x3[0] <= refined <= x3[-1]:
            return float(refined)
        return float(two_theta[peak_index])

    def _remove_baseline(self, intensity: np.ndarray) -> np.ndarray:
        window_size = max(int(len(intensity) * self.baseline_window_fraction), 10)
        baseline = minimum_filter1d(intensity, size=window_size, mode="nearest")
        corrected = intensity - baseline
        corrected[corrected < 0] = 0
        return corrected
