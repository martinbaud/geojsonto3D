# Changelog

## [1.1.0] - 2026-04-03

### Added
- Country name normalization for API compatibility
- City alignment with surface, inward extrusion
- Hex grid generation mode (`hex_run.py`)
- Shared geometric utilities (`geo_utils.py`)
- Type hints on all public functions
- `pyproject.toml` with project metadata
- `.pre-commit-config.yaml`
- `CONTRIBUTING.md`
- Geometric unit tests (`test_geo_utils.py`)
- Globe screenshot in README
- CI: Python 3.10-3.13, strict lint, coverage upload

### Changed
- Email templates switched to orange theme
- CI upgraded to actions/checkout@v4, setup-python@v5
- Dropped EOL Python 3.8/3.9
- Lint is now strict (no `|| true`)

### Removed
- Redundant `run_tests.py`
- Deprecated `datetime.utcnow()` calls
- Fragile README/structure tests

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
