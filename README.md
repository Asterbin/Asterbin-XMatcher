# XMatcher

XMatcher is a Python toolkit for experimental X-ray diffraction (XRD) phase
matching against precomputed crystal-structure databases. It is designed around
a production workflow: build a searchable theoretical peak database once, then
perform fast and explainable retrieval for experimental patterns.

## What It Does

- Reads common two-column XRD text formats, including CSV, tab-separated and whitespace-separated files.
- Detects experimental peaks with baseline correction, smoothing, prominence filtering and sub-point peak refinement.
- Searches a precomputed theoretical XRD database by element constraints before peak-level ranking.
- Matches peaks with an optimal assignment algorithm instead of greedy nearest-neighbor pairing.
- Estimates a global 2θ shift from both a regular scan grid and peak-pair shift candidates.
- Returns explainable results, including matched peak pairs, position errors, FOM, precision, recall and estimated shift.

## Project Files

Start here if you are using the project locally:

| File | Purpose |
| --- | --- |
| [`XMatcher_Guide.html`](XMatcher_Guide.html) | Bilingual quick guide for installation, database download/build, first search, Jupyter API, and local UI usage. Open directly in a browser. |
| [`XMatcher_Local_UI.html`](XMatcher_Local_UI.html) | Advanced local browser interface for uploading XRD files, tuning parameters, running identification, plotting experimental/theoretical peaks, and downloading results. |
| [`xmatcher_local_api.py`](xmatcher_local_api.py) | Local Python API used by `XMatcher_Local_UI.html` to call XMatcher and the `.pkl` database. Start it before using the UI. |
| [`XMatcher_Jupyter_API_Guide_CN_EN.ipynb`](XMatcher_Jupyter_API_Guide_CN_EN.ipynb) | Detailed bilingual Jupyter notebook showing XRD import, parameter tuning, full-database retrieval, and result interpretation. |
| [`build_database_parallel.py`](build_database_parallel.py) | Multiprocessing builder that converts raw `MP500.db` or another ASE database into a searchable XMatcher peak database. |
| [`MP500_xrd_database.pkl`](MP500_xrd_database.pkl) | Prebuilt searchable XRD peak database. This can also be downloaded from GitHub Releases. |
| [`MP500.db`](MP500.db) | Raw ASE crystal-structure database used only when rebuilding the peak database yourself. This can also be downloaded from GitHub Releases. |
| [`exp_data/`](exp_data/) | Example experimental XRD files for quick tests and demos. |
| [`XMatcher/`](XMatcher/) | Python package source code. Main API: `XRDRetriever`, `XRDReader`, `PeakDetector`, `XRDMatcher`, `DatabaseBuilder`. |

For the browser UI:

```bash
python xmatcher_local_api.py --database MP500_xrd_database.pkl
```

Then open [`XMatcher_Local_UI.html`](XMatcher_Local_UI.html) locally.

## Installation

```bash
pip install -r requirements.txt
pip install -e .
```

For plotting in notebooks:

```bash
pip install -e ".[viz]"
```

For development and tests:

```bash
pip install -r requirements-dev.txt
pytest
```

## Quick Start

```python
from XMatcher import XRDRetriever

retriever = XRDRetriever(
    database_path="xrd_database.pkl",
    n_peaks=20,
    position_tolerance=0.2,
    scoring_method="hybrid",
)

results = retriever.retrieve_from_file(
    "exp_data/BTc.csv",
    elements=["B", "Tc"],
    element_filter_mode="exact",
    top_n=10,
)

retriever.print_results(results)

best = results[0]
print(best["formula"], best["score"], best["estimated_shift"])
print(best["peak_matches"][:3])
```

Use `element_filter_mode="contains"` when extra elements, impurities or dopants
are possible. Use `element_filter_mode="exact"` when the phase chemistry is
known and candidates should contain exactly the requested element set.

## Get An XRD Database

XMatcher expects a trusted local pickle database with theoretical peaks. The
fastest path is to download the prebuilt `MP500_xrd_database.pkl` from GitHub
Releases and place it in the project root.

If you want to change build parameters or rebuild from raw structures, download
`MP500.db` from Releases and build the peak database yourself:

```bash
python build_database_parallel.py \
  --db-path MP500.db \
  --output MP500_xrd_database.pkl \
  --workers 8 \
  --n-peaks 30 \
  --two-theta-min 10 \
  --two-theta-max 90
```

The database package contains:

- `xrd_database`: entry metadata and theoretical peaks
- `element_index`: exact element-set index
- `element_inverted_index`: fast contains-mode element index
- `metadata`: wavelength, 2θ range, number of peaks and schema version

Existing version-1 databases remain loadable; indexes are rebuilt in memory if
they are missing.

Do not load pickle files from untrusted sources. Pickle is used here for fast
local scientific workflows, but it can execute code during deserialization.

For a detailed Jupyter API walkthrough, open
`XMatcher_Jupyter_API_Guide_CN_EN.ipynb` in the project root.

For an interactive local browser UI, run the local API and open
`XMatcher_Local_UI.html`:

```bash
python xmatcher_local_api.py --database MP500_xrd_database.pkl
```

## Matching Model

The retrieval pipeline is:

1. Read and clean experimental XRD data.
2. Normalize, remove baseline, smooth and detect peaks.
3. Select the strongest experimental peaks.
4. Filter database entries by element constraints.
5. For each candidate, scan a small global 2θ shift window and likely peak-pair shifts.
6. At each shift, solve an optimal peak assignment with the Hungarian algorithm.
7. Rank candidates with the selected score and deterministic tie-breakers.

The default `hybrid` score combines:

- position and intensity assignment quality, with intensity differences scaled to avoid overwhelming position agreement
- theoretical peak intensity coverage, reported as `fom`
- experimental peak coverage
- peak-match precision and recall

For less reliable intensities, keep `intensity_weight` low. The default is 0.15.

## Result Fields

Each result contains:

- `score`: ranking score for the selected scoring method
- `weighted_score`: assignment-quality score
- `fom`: matched theoretical intensity fraction
- `experimental_coverage`: matched experimental intensity fraction
- `precision`: matched experimental peaks / experimental peaks
- `recall`: matched database peaks / database peaks
- `estimated_shift`: best global shift applied to database peaks
- `peak_matches`: matched peak-pair diagnostics
- `mpid`, `formula`, `elements`, `spacegroup`, `spacegroup_symbol`

## Python API

```python
from XMatcher import PeakDetector, XRDMatcher, XRDReader, XRDRetriever
from XMatcher.database import DatabaseBuilder
```

Use the `XMatcher` package directly for all new code.

## Data Format

Experimental data should contain two numeric columns:

```csv
two_theta,intensity
10.00,5.2
10.02,5.5
10.04,5.1
```

The reader auto-detects comma, tab, whitespace and semicolon delimiters.

## Tutorials

- [`XMatcher_Guide.html`](XMatcher_Guide.html): bilingual setup and usage guide.
- [`XMatcher_Jupyter_API_Guide_CN_EN.ipynb`](XMatcher_Jupyter_API_Guide_CN_EN.ipynb): detailed bilingual Jupyter API walkthrough.
- [`XMatcher_Local_UI.html`](XMatcher_Local_UI.html): local browser UI for interactive XRD identification.

## Project Layout

- `XMatcher/`: package source
- `tests/`: regression tests for matching, reading and peak detection
- `exp_data/`: small example experimental patterns
- `build_database_parallel.py`: CLI for building theoretical databases
- `xmatcher_local_api.py`: local API used by the browser UI
- `requirements.txt`: runtime dependencies
- `requirements-dev.txt`: runtime plus notebook/test/lint tooling



## License

This project is licensed under the MIT License. See `LICENSE`.
