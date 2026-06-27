#!/usr/bin/env python
"""Package built desktop artifacts before uploading them from GitHub Actions."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
ARTIFACT_DIR = DIST_DIR / "artifacts"


def package_windows() -> Path:
    source = DIST_DIR / "XMatcher"
    if not source.exists():
        raise FileNotFoundError(f"Windows build output not found: {source}")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    archive_base = ARTIFACT_DIR / "XMatcher-Windows"
    archive = shutil.make_archive(str(archive_base), "zip", root_dir=DIST_DIR, base_dir="XMatcher")
    return Path(archive)


def package_macos() -> Path:
    source = DIST_DIR / "XMatcher.app"
    if not source.exists():
        raise FileNotFoundError(f"macOS build output not found: {source}")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    archive = ARTIFACT_DIR / "XMatcher-macOS.zip"
    subprocess.run(
        ["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(source), str(archive)],
        check=True,
    )
    return archive


def main() -> int:
    system = platform.system()
    if system == "Windows":
        archive = package_windows()
    elif system == "Darwin":
        archive = package_macos()
    else:
        raise RuntimeError(f"Unsupported packaging platform: {system}")
    print(f"Packaged artifact: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
