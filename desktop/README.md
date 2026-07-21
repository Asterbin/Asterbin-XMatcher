# XMatcher Desktop Packaging

[![Paper](https://img.shields.io/badge/arXiv-2607.17162-b31b1b.svg)](https://arxiv.org/abs/2607.17162)

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

## Citation

When using XMatcher, please cite both the XMatcher paper and the related XQueryer paper:

Cao B. *XMatcher: An Open-Source Framework for X-Ray Diffraction Phase Identification.* arXiv:2607.17162 (2026). https://arxiv.org/abs/2607.17162

```bibtex
@misc{cao2026xmatcheropensourceframeworkxray,
      title={XMatcher: An Open-Source Framework for X-Ray Diffraction Phase Identification},
      author={Bin Cao},
      year={2026},
      eprint={2607.17162},
      archivePrefix={arXiv},
      primaryClass={cond-mat.mtrl-sci},
      url={https://arxiv.org/abs/2607.17162},
}
```

Related paper: Cao B., Zheng Z., Liu Y., Zhang L., Wong L. W. Y., Weng L.-T., Li J., Li H., and Zhang T.-Y. *XQueryer: an intelligent crystal structure identifier for powder X-ray diffraction.* *National Science Review* 12(12), nwaf421 (2025).

```bibtex
@article{cao2025xqueryer,
  title={XQueryer: an intelligent crystal structure identifier for powder X-ray diffraction},
  author={Cao, Bin and Zheng, Zinan and Liu, Yang and Zhang, Longhan and Wong, Lawrence WY and Weng, Lu-Tao and Li, Jia and Li, Haoxiang and Zhang, Tong-Yi},
  journal={National Science Review},
  volume={12},
  number={12},
  pages={nwaf421},
  year={2025},
  publisher={Oxford University Press}
}
```
