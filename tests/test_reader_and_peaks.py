from pathlib import Path

import numpy as np

from XMatcher import PeakDetector, XRDReader


def test_reader_auto_detects_example_csv():
    data = XRDReader().read_auto(Path("exp_data/BTc.csv"))

    assert len(data["two_theta"]) == len(data["intensity"])
    assert len(data["two_theta"]) > 100
    assert np.all(np.diff(data["two_theta"]) > 0)


def test_peak_detector_finds_synthetic_peaks():
    two_theta = np.linspace(10.0, 50.0, 2000)
    intensity = (
        100.0 * np.exp(-0.5 * ((two_theta - 20.0) / 0.08) ** 2)
        + 60.0 * np.exp(-0.5 * ((two_theta - 35.0) / 0.12) ** 2)
    )

    peaks = PeakDetector(min_peak_height=5.0, min_peak_prominence=3.0).get_top_peaks(
        two_theta,
        intensity,
        n_peaks=2,
    )

    assert len(peaks) == 2
    assert abs(peaks[0]["two_theta"] - 20.0) < 0.05
    assert abs(peaks[1]["two_theta"] - 35.0) < 0.05
