# Contributing to geojsonto3D

Thanks for your interest in contributing!

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/<you>/geojsonto3D.git`
3. Install dev dependencies: `pip install -r requirements-dev.txt`
4. Create a branch: `git checkout -b feat/your-feature`

## Development

```bash
# Run tests
pytest tests/ -v

# Check formatting
black --check --line-length 120 src/ tests/

# Auto-format
black --line-length 120 src/ tests/

# Lint
flake8 src/ tests/ --max-line-length=120 --extend-ignore=E203,W503
```

## Running a Blender generation test

You need Blender installed locally:

```bash
python main.py --preset low
```

This generates `res/atlas_ico_subdiv_3.glb` in about 30 seconds.

## Pull Requests

- One feature per PR
- Include tests for new functionality
- Make sure CI is green before requesting review
- Use clear commit messages: `feat:`, `fix:`, `docs:`, `test:`, `chore:`

## Reporting Bugs

Open an issue with:
- Steps to reproduce
- Expected vs actual behavior
- Python version, OS, Blender version
