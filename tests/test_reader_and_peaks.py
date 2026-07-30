from pathlib import Path

import numpy as np

from XMatcher import PeakDetector, XRDReader


def test_reader_auto_detects_example_csv():
    data = XRDReader().read_auto(Path("exp_data/BTc.csv"))

    assert len(data["two_theta"]) == len(data["intensity"])
    assert len(data["two_theta"]) > 100
    assert np.all(np.diff(data["two_theta"]) > 0)


def test_reader_auto_keeps_first_row_of_headerless_numeric_data(tmp_path):
    path = tmp_path / "headerless.csv"
    path.write_text("10,1\n20,2\n30,3\n", encoding="utf-8")

    data = XRDReader().read_auto(path)

    assert data["two_theta"].tolist() == [10.0, 20.0, 30.0]
    assert data["intensity"].tolist() == [1.0, 2.0, 3.0]


def test_reader_auto_reads_vendor_ascii_with_metadata_and_third_column(tmp_path):
    path = tmp_path / "scan.xye"
    path.write_text("_INSTRUMENT=example\n# 2theta intensity uncertainty\n10 1 0.1\n20 2 0.1\n30 3 0.1\n")

    data = XRDReader().read_auto(path)

    assert data["two_theta"].tolist() == [10.0, 20.0, 30.0]
    assert data["intensity"].tolist() == [1.0, 2.0, 3.0]


def test_reader_auto_reads_json_arrays(tmp_path):
    path = tmp_path / "scan.json"
    path.write_text('{"two_theta": [10, 20, 30], "counts": [1, 2, 3]}', encoding="utf-8")

    data = XRDReader().read_auto(path)

    assert data["two_theta"].tolist() == [10.0, 20.0, 30.0]
    assert data["intensity"].tolist() == [1.0, 2.0, 3.0]


def test_reader_auto_reads_namespaced_xrdml_start_end_positions(tmp_path):
    path = tmp_path / "scan.xrdml"
    path.write_text(
        """<xrdMeasurements xmlns=\"urn:xrdml\"><scan><dataPoints>
        <positions axis=\"2Theta\"><startPosition>10</startPosition><endPosition>30</endPosition></positions>
        <intensities>1 2 3</intensities>
        </dataPoints></scan></xrdMeasurements>""",
        encoding="utf-8",
    )

    data = XRDReader().read_auto(path)

    assert data["two_theta"].tolist() == [10.0, 20.0, 30.0]
    assert data["intensity"].tolist() == [1.0, 2.0, 3.0]


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
