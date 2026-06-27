# XMatcher Desktop Packaging

This folder contains the desktop packaging files for XMatcher.

## Files

- `xmatcher_desktop.py`: desktop launcher. It starts the local API and opens `XMatcher_Local_UI.html` in a native window.
- `prepare_database.py`: checks that `MP500_xrd_database.pkl` is available, or downloads it from the workflow input URL.
- `build_desktop.py`: PyInstaller build script used locally and by GitHub Actions.
- `package_artifacts.py`: zips the built app before upload so `.app` bundles keep their required structure.
- `requirements-desktop.txt`: desktop-only build/runtime dependencies.

The GitHub Actions workflow lives in `.github/workflows/build-desktop.yml` because GitHub requires workflow files to be there. It only calls files from this folder and uploads build artifacts. It does not upload anything to Releases.

## Local Build

From the repository root:

```bash
python -m pip install -r requirements.txt -r desktop/requirements-desktop.txt
python desktop/build_desktop.py
```

Outputs:

- Windows: `dist/XMatcher/XMatcher.exe`
- macOS: `dist/XMatcher.app`

For reliable distribution, build each platform on the matching operating system. The GitHub Actions workflow does that automatically.

## Manual GitHub Actions Build

1. Push the repository to GitHub.
2. Open the repository on GitHub.
3. Go to `Actions`.
4. Select `Build Desktop Artifacts`.
5. If `MP500_xrd_database.pkl` is not tracked in Git, paste a direct download URL into `database_url`.
6. Click `Run workflow`.
7. After it finishes, download the artifacts from the workflow run page.

Artifacts are intended for manual download/testing and are not attached to GitHub Releases.
