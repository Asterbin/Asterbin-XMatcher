#!/usr/bin/env python
"""Desktop launcher for the XMatcher local UI.

The launcher starts the local HTTP API in-process and opens the existing
HTML interface in a native desktop window via pywebview.
"""

from __future__ import annotations

import logging
import socket
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import webview

import xmatcher_local_api as api
from XMatcher.database import DatabaseBuilder, normalize_database_package


APP_NAME = "XMatcher"
DEFAULT_PORT = 8765


def resource_path(name: str) -> Path:
    """Return a path that works in source checkout and PyInstaller bundles."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / name
    return Path(__file__).resolve().parents[1] / name


def find_available_port(preferred: int = DEFAULT_PORT) -> int:
    for port in [preferred, *range(8766, 8796)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No available local port found in range 8765-8795.")


def start_api_server(database_path: Path, port: int) -> ThreadingHTTPServer:
    if not database_path.exists():
        raise FileNotFoundError(f"Database not found: {database_path}")

    logging.info("Loading database: %s", database_path)
    api.DATABASE_PATH = database_path
    api.DATABASE = DatabaseBuilder.load_database(str(database_path))
    api.DATABASE = normalize_database_package(api.DATABASE)

    server = ThreadingHTTPServer(("127.0.0.1", port), api.Handler)
    thread = threading.Thread(target=server.serve_forever, name="xmatcher-api", daemon=True)
    thread.start()
    logging.info("Local API running at http://127.0.0.1:%s", port)
    return server


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    html_path = resource_path("XMatcher_Local_UI.html")
    database_path = resource_path("MP500_xrd_database.pkl")
    if not html_path.exists():
        raise FileNotFoundError(f"UI file not found: {html_path}")

    port = find_available_port()
    server = start_api_server(database_path, port)
    api_url = f"http://127.0.0.1:{port}"

    window = webview.create_window(
        APP_NAME,
        html_path.as_uri(),
        width=1480,
        height=940,
        min_size=(1100, 720),
        text_select=True,
    )

    def configure_ui() -> None:
        escaped_api_url = api_url.replace("\\", "\\\\").replace("'", "\\'")
        window.evaluate_js(
            "(() => {"
            "const input = document.getElementById('apiUrl');"
            f"if (input) input.value = '{escaped_api_url}';"
            "if (typeof checkServer === 'function') checkServer();"
            "})()"
        )

    window.events.loaded += configure_ui

    try:
        webview.start(debug=False)
    finally:
        logging.info("Shutting down local API")
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
