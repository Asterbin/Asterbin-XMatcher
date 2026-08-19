# Changelog

## V1.3.0 — 2026-08-19

### Fixed

- Fixes the App data-export bug.

### Expanded crystal-structure database

- Adds 2,007 RRUFF crystal structures to the searchable XRD database.
- Displays local RRUFF `CrystID` values without an external link, while Materials Project IDs remain linked.

## V1.2.0 — 2026-07-30

### Improved identification reliability

- Scores theoretical peaks only within the experimental scan range.
- Penalizes strong unexplained experimental peaks and missing strong theoretical peaks, and returns their diagnostics.
- Adds residual-error-versus-2θ diagnostics for matched peaks.

### Added instrument corrections

- Adds a fixed zero correction applied before peak detection and matching.
- Adds an optional Bragg-Brentano `cos(theta)` geometry correction for values determined from a standard sample.

### Expanded data import

- Preserves the first measurement row in headerless numeric files.
- Supports vendor-style two/three-column ASCII files (XY, XYS, XYE, CHI, ASC, DAT and UXD), simple JSON, and common XRDML/XML scans.



## V1.1.0

- Introduced AutoMix multi-phase identification and relative diffraction contribution reporting.
