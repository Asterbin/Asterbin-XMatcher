#!/usr/bin/env python
"""Ensure the bundled XMatcher database exists before desktop packaging."""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "MP500_xrd_database.pkl"


def main() -> int:
    if DATABASE.exists():
        print(f"Database found: {DATABASE}")
        return 0

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        print(
            "MP500_xrd_database.pkl is missing. This file is ignored by Git, so "
            "GitHub Actions cannot see your local copy. Re-run the workflow with "
            "the database_url input, or track the database with Git LFS.",
            file=sys.stderr,
        )
        return 1

    print(f"Downloading database from {database_url}")
    try:
        request = urllib.request.Request(database_url, headers={"User-Agent": "XMatcher-GitHub-Actions"})
        with urllib.request.urlopen(request) as response:
            DATABASE.write_bytes(response.read())
    except urllib.error.HTTPError as exc:
        print(
            f"Failed to download database: HTTP {exc.code} {exc.reason}. "
            "Check that the release tag, asset name, and repository visibility are correct. "
            "For private repositories, this direct release URL is not enough; use actions/download-artifact, "
            "gh release download with GITHUB_TOKEN, or make the asset publicly accessible.",
            file=sys.stderr,
        )
        return 1
    except urllib.error.URLError as exc:
        print(f"Failed to download database: {exc.reason}", file=sys.stderr)
        return 1
    print(f"Database downloaded: {DATABASE} ({DATABASE.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
