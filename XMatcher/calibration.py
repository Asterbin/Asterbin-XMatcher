"""Instrument peak-position corrections for experimental XRD scans."""

from __future__ import annotations

from typing import Sequence

import numpy as np


def calibrate_two_theta(
    two_theta: Sequence[float], zero_shift: float = 0.0, specimen_displacement: float = 0.0
) -> np.ndarray:
    """Apply a fixed zero correction and a Bragg-Brentano displacement term.

    Both values are in degrees and are *added* to measured 2theta. The
    displacement parameter is the correction amplitude at 2theta = 0; its
    angular dependence follows ``cos(theta)``. It should be obtained from a
    standard sample, not fitted freely to an unknown phase.
    """
    positions = np.asarray(two_theta, dtype=float)
    zero_shift = float(zero_shift)
    specimen_displacement = float(specimen_displacement)
    if not np.isfinite(zero_shift) or not np.isfinite(specimen_displacement):
        raise ValueError("calibration corrections must be finite")
    theta_radians = np.deg2rad(positions / 2.0)
    return positions + zero_shift + specimen_displacement * np.cos(theta_radians)
