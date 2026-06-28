#!/usr/bin/env python
"""Local HTTP API used by XMatcher_Local_UI.html.

Run:
    python xmatcher_local_api.py --database MP500_xrd_database.pkl --host 127.0.0.1 --port 8765
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from XMatcher.database import DatabaseBuilder, normalize_database_package
from XMatcher.matcher import XRDMatcher
from XMatcher.peak_detector import PeakDetector

logger = logging.getLogger("xmatcher_local_api")

DATABASE: Optional[Dict] = None
DATABASE_PATH: Optional[Path] = None


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Dict) -> None:
    body = json.dumps(_json_ready(payload), ensure_ascii=False, allow_nan=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


def _json_ready(value):
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, np.ndarray):
        return _json_ready(value.tolist())
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _read_json(handler: BaseHTTPRequestHandler) -> Dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


def _as_float_array(values: Sequence) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    return arr


def _prepare_arrays(two_theta: Sequence, intensity: Sequence) -> Tuple[np.ndarray, np.ndarray]:
    x = np.asarray(two_theta, dtype=float)
    y = np.asarray(intensity, dtype=float)
    if x.size != y.size:
        raise ValueError("two_theta and intensity must have the same length")
    valid = np.isfinite(x) & np.isfinite(y)
    x = x[valid]
    y = y[valid]
    y[y < 0] = 0
    if x.size < 3:
        raise ValueError("At least 3 valid XRD points are required")
    order = np.argsort(x)
    return x[order], y[order]


def _get_database() -> Dict:
    if DATABASE is None:
        raise RuntimeError("Database is not loaded")
    return DATABASE


def _database_stats() -> Dict:
    database = _get_database()
    xrd_db = database["xrd_database"]
    metadata = database.get("metadata", {})
    elements = set()
    formulas = set()
    for entry in xrd_db.values():
        elements.update(entry.get("elements", []))
        formulas.add(entry.get("formula"))
    return {
        "database_path": str(DATABASE_PATH) if DATABASE_PATH else None,
        "total_entries": len(xrd_db),
        "unique_elements": sorted(elements),
        "n_unique_elements": len(elements),
        "unique_formulas": len(formulas),
        "metadata": metadata,
    }


def _match(payload: Dict) -> Dict:
    database = _get_database()
    params = payload.get("params", {})
    two_theta, intensity = _prepare_arrays(payload.get("two_theta", []), payload.get("intensity", []))

    detector = PeakDetector(
        min_peak_height=float(params.get("min_peak_height", 3.0)),
        min_peak_prominence=float(params.get("min_peak_prominence", 2.0)),
        min_peak_distance=float(params.get("min_peak_distance", 0.1)),
        smooth_window=int(params.get("smooth_window", 7)),
        baseline_window_fraction=float(params.get("baseline_window_fraction", 0.05)),
    )
    n_peaks = int(params.get("n_peaks", 4))
    peaks = detector.get_top_peaks(two_theta, intensity, n_peaks=n_peaks, preprocess=True)
    exp_positions, exp_intensities = detector.extract_peak_positions_and_intensities(peaks)

    matcher = XRDMatcher(
        position_tolerance=float(params.get("position_tolerance", 0.2)),
        intensity_weight=float(params.get("intensity_weight", 0.15)),
        position_weight=float(params.get("position_weight", 0.85)),
        min_matched_peaks=int(params.get("min_matched_peaks", 2)),
        scoring_method=str(params.get("scoring_method", "hybrid")),
        max_shift=float(params.get("max_shift", 0.5)),
        shift_step=float(params.get("shift_step", 0.02)),
    )

    elements = payload.get("elements")
    if isinstance(elements, str):
        elements = [item.strip() for item in elements.split(",") if item.strip()]
    if not elements:
        elements = None
    element_filter_mode = str(payload.get("element_filter_mode", "contains"))
    top_n = int(payload.get("top_n", 10))

    candidate_ids = matcher.filter_by_elements(database, elements, mode=element_filter_mode)
    results = matcher.match_pattern(
        exp_positions,
        exp_intensities,
        database,
        elements=elements,
        top_n=top_n,
        element_filter_mode=element_filter_mode,
    )

    enriched = []
    for result in results:
        entry = database["xrd_database"].get(result["entry_id"], {})
        peaks_data = entry.get("peaks", {})
        enriched.append(
            {
                **result,
                "theoretical_peaks": {
                    "positions": peaks_data.get("positions", []),
                    "intensities": peaks_data.get("intensities", []),
                    "d_spacings": peaks_data.get("d_spacings", []),
                    "hkls": peaks_data.get("hkls", []),
                },
            }
        )

    processed_x, processed_y = detector.preprocess_spectrum(two_theta, intensity)
    return {
        "status": "ok",
        "input_points": int(two_theta.size),
        "candidate_count": len(candidate_ids),
        "detected_peaks": peaks,
        "processed_spectrum": {
            "two_theta": processed_x.tolist(),
            "intensity": processed_y.tolist(),
        },
        "results": enriched,
        "params": params,
        "elements": elements,
        "element_filter_mode": element_filter_mode,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "XMatcherLocalAPI/1.0"

    def do_OPTIONS(self) -> None:
        _json_response(self, 200, {"status": "ok"})

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/api/status":
            _json_response(self, 200, {"status": "ok", "database": _database_stats()})
            return
        _json_response(self, 404, {"status": "error", "error": "Unknown endpoint"})

    def do_POST(self) -> None:
        try:
            if self.path.rstrip("/") == "/api/match":
                payload = _read_json(self)
                _json_response(self, 200, _match(payload))
                return
            _json_response(self, 404, {"status": "error", "error": "Unknown endpoint"})
        except Exception as exc:
            logger.exception("Request failed")
            _json_response(self, 500, {"status": "error", "error": str(exc)})

    def log_message(self, fmt: str, *args) -> None:
        logger.info("%s - %s", self.address_string(), fmt % args)


def main() -> int:
    global DATABASE, DATABASE_PATH

    parser = argparse.ArgumentParser(description="Local XMatcher API for XMatcher_Local_UI.html")
    parser.add_argument("--database", default="MP500_xrd_database.pkl", help="Path to the built XMatcher .pkl database")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", default=8765, type=int, help="Bind port")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    DATABASE_PATH = Path(args.database)
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DATABASE_PATH}")

    logger.info("Loading database: %s", DATABASE_PATH)
    DATABASE = DatabaseBuilder.load_database(str(DATABASE_PATH))
    DATABASE = normalize_database_package(DATABASE)
    logger.info("Loaded %d entries", len(DATABASE["xrd_database"]))

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    logger.info("Serving XMatcher local API at http://%s:%d", args.host, args.port)
    logger.info("Open XMatcher_Local_UI.html in your browser.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
