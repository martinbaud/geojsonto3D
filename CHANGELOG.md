# Changelog

## [1.2.0] - 2026-04-03

### Added
- `hex-medium-lite` and `hex-high-lite` presets (lighter extrusion, thinner borders for mobile)
- GPU optimization: remove inner closing faces hidden by GlobeFill
- Shared geometric utilities (`geo_utils.py`)
- Geometric unit tests (`test_geo_utils.py`) — 20 new tests
- Type hints on all public functions
- `pyproject.toml` with project metadata
- `.pre-commit-config.yaml`
- `CONTRIBUTING.md`, `CHANGELOG.md`
- Globe screenshot in README (Blender viewport)
- CI: Python 3.10-3.13, strict lint, coverage upload

### Changed
- CI upgraded to actions/checkout@v4, setup-python@v5
- Dropped EOL Python 3.8/3.9
- Lint is now strict (no `|| true`)
- Normals recalculated after face removal for Three.js FrontSide rendering

### Removed
- Redundant `run_tests.py`
- Deprecated `datetime.utcnow()` calls
- Fragile README/structure tests

## [1.1.0] - 2026-03-06

### Fixed
- Cities aligned with globe surface, extrude inward like countries
- Country name normalization for API compatibility

## [1.0.0] - 2025-10-12

### Added
- Initial release
- GeoJSON to 3D globe conversion
- ICO sphere subdivision with configurable quality
- Country extrusion (bidirectional radial)
- 3D border generation with anti-z-fighting
- City markers (triangular prisms)
- GLB export
- Interactive CLI with quality presets
- GitHub Actions CI
- 35 unit and integration tests
