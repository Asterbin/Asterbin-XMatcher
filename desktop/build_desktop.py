#!/usr/bin/env python
"""Build the XMatcher desktop app with PyInstaller.

This script keeps platform-specific PyInstaller flags in one place so the
GitHub Actions workflow can stay minimal.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP_DIR = ROOT / "desktop"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build" / "desktop"
APP_NAME = "XMatcher"


def add_data_arg(source: Path, dest: str) -> str:
    separator = ";" if platform.system() == "Windows" else ":"
    return f"{source}{separator}{dest}"


def build(clean: bool) -> None:
    if clean:
        shutil.rmtree(DIST_DIR, ignore_errors=True)
        shutil.rmtree(BUILD_DIR, ignore_errors=True)

    required_files = [
        ROOT / "XMatcher_Local_UI.html",
        ROOT / "MP500_xrd_database.pkl",
    ]
    missing = [str(path) for path in required_files if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required bundle files: " + ", ".join(missing))

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
        "--specpath",
        str(BUILD_DIR),
        "--paths",
        str(ROOT),
        "--add-data",
        add_data_arg(ROOT / "XMatcher_Local_UI.html", "."),
        "--add-data",
        add_data_arg(ROOT / "MP500_xrd_database.pkl", "."),
        "--collect-all",
        "pymatgen",
        "--collect-all",
        "ase",
        "--collect-submodules",
        "scipy",
        "--collect-submodules",
        "pandas",
        str(DESKTOP_DIR / "xmatcher_desktop.py"),
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build XMatcher desktop app.")
    parser.add_argument("--no-clean", action="store_true", help="Keep previous build/dist directories.")
    args = parser.parse_args()
    build(clean=not args.no_clean)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
