# GeoJSON to 3D Globe

![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)
![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)
![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)

Convert GeoJSON geographic data into interactive 3D globe models using Blender.

## Table of Contents

- [Usage](#usage)
- [Features](#features)
- [Installation](#installation)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Output](#output)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

## Usage

### Quick Start

```bash
# Run the application
python main.py
```

On first launch:
1. Enter Blender path when prompted (e.g., `C:\Program Files\Blender Foundation\Blender 4.4\blender.exe`)
2. Choose a quality preset (1-4)
3. Wait for generation to complete
4. Find your 3D globe in `res/atlas_ico_subdiv_X.glb`

### Quality Presets

```bash
# Fast test (quick check)
python main.py --preset low

# Balanced quality
python main.py --preset medium

# High quality (portfolio-ready)
python main.py --preset high

# Maximum quality
python main.py --preset ultra
```

### Advanced Options

```bash
# Run with Blender GUI visible
python main.py --gui

# Reconfigure all settings
python main.py --configure

# Specify custom Blender path
python main.py --blender "C:\Program Files\Blender Foundation\Blender 4.4\blender.exe"

# Show help
python main.py --help
```

### Preset Details

| Preset | ICO_SUBDIV | Use Case |
|--------|------------|----------|
| low    | 3          | Quick testing |
| medium | 5          | Development |
| high   | 7          | Production (portfolio) |
| ultra  | 7          | Production (heavier borders) |

### Custom Configuration

When choosing "custom" during interactive setup, you can configure:

- **ICO_SUBDIV** (3-7): Globe subdivision level
- **Extrusion** (0.0-0.1): Country height above surface (default 0.1 above, 0.0 below)
- **Borders**: Enable/disable 3D country borders
- **Cities**: Enable/disable city markers (significantly slower)

## Features

- 🌍 Spherical projection of GeoJSON polygons onto 3D globe
- 📊 Radial extrusion aligned to base sphere (above by default)
- 🎨 Automatic 3D border generation with anti-z-fighting
- 🎯 Support for complex MultiPolygon geometries
- 📦 GLB export for web/game engines
- ⚙️ Interactive CLI with quality presets
- 💾 Automatic caching of Blender path and configuration

## Installation

1. **Install Blender** (version 2.80+)
   - Download from [blender.org](https://www.blender.org/download/)

2. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/geojsonto3D.git
   cd geojsonto3D
   ```

   ℹ️ **GeoJSON data is included** - Natural Earth data files are already in `data/` directory (public domain).

3. **Run the application**
   ```bash
   python main.py
   ```

## Project Structure

```
geojsonto3D/
├── main.py                             # Main launcher (run this)
├── blender_script.py                   # Blender script (legacy, updated version in src/)
├── README.md                           # This file
│
├── src/                                # Source code
│   ├── blender_runner.py              # CLI with interactive configuration
│   └── run.py                         # Blender script (globe generation)
│
├── data/                               # Input GeoJSON data
│   ├── ne_50m_admin_0_countries.geojson
│   └── ne_50m_populated_places.json
│
└── res/                                # Generated 3D models (output)
  └── atlas_ico_subdiv_*.glb         # Auto-created
```

## Configuration

### Cache Files

The tool uses two cache files in the project root:
- `.blender_cache.json` - Stores Blender executable path
- `.config_cache.json` - Stores generation parameters

Delete these files to reset configuration.

### Technical Parameters

- `ICO_SUBDIV`: Icosphere subdivision level (affects quality and performance)
- `EXTRUDE_ABOVE_COUNTRY`: Outward extrusion depth for countries
- `EXTRUDE_BELOW_COUNTRY`: Inward extrusion depth for countries
- `EXTRUDE_ABOVE_CITY`: Outward extrusion depth for cities
- `EXTRUDE_BELOW_CITY`: Inward extrusion depth for cities
- `BORDER_WIDTH`: Border ribbon width
- `BORDER_HEIGHT`: Border ribbon height
- `ENABLE_COUNTRIES`: Toggle country rendering
- `ENABLE_CITIES`: Toggle city markers
- `ENABLE_COUNTRY_BORDERS`: Toggle country borders
- `ENABLE_CITY_BORDERS`: Toggle city borders
- `INVERT_POLES`: Invert globe orientation (Antarctica at bottom)

### Configuration File Output

The generator now creates a configuration file alongside the GLB model:

```json
{
  "generated_at": "2025-10-12T09:10:25",
  "ico_subdiv": 7,
  "radius": 1.0,
  "invert_poles": true,
  "extrusions": {
    "country": {
      "above": 0.0,
      "below": 0.0
    },
    "city": {
      "above": 0.0,
      "below": 0.0
    }
  },
  "border": {
    "width": 0.0006,
    "height": 0.0025,
    "zfight_eps": 8e-05
  },
  "counts": {
    "countries": 374,
    "cities": 1106
  }
}
```

This configuration can be used by applications consuming the 3D globe to understand the model parameters and adjust rendering accordingly.

## Output

Generated GLB files are saved to `res/` directory:
- `atlas_ico_subdiv_3.glb` - Low
- `atlas_ico_subdiv_5.glb` - Medium
- `atlas_ico_subdiv_7.glb` - High/Ultra

### Mesh naming convention

Exported object names follow a simple, stable pattern to make it easy for consuming apps to identify elements:

- Globe base: `GlobeFill`
- Countries: `country_{name}`
- Borders: `border_{name}` (generated from the corresponding country name)
- Cities: `city_{cityName}_{index}` (if enabled; triangular prism markers)
- Closings: `closing_{cityName}_{index}` (per-city triangular ribbon above each city marker’s top face)

Notes:
- Previous versions produced borders named like `border_country_{name}`. This has been simplified to `border_{name}`.
- There are no separate wall objects emitted; if you need walls, create them from country meshes in your pipeline.
- Mobile builds typically hide cities/closings; web/desktop can toggle them at runtime (see below).

Terminology:
- “Border” refers to country borders (ribbons along country top edges): `border_{countryName}`.
- “Closing” refers to the thin ribbon around a city’s top face. We keep a distinct name (`closing_…`) to differentiate it from country borders in runtime code and styling.

### Feature flags

Generation flags (CLI):
- `--enable-border` / `--disable-border`
- `--enable-closing` / `--disable-closing`
- `--enable-cities` / `--disable-cities`

Presets default to: low/medium (cities off, closings off), high/ultra (cities on, closings on).
Note: Closings are generated per city. If cities are disabled, the closing flag has no effect.

### Viewing Results

**Online viewers:**
- [glTF Viewer](https://gltf-viewer.donmccurdy.com/)
- [Babylon.js Sandbox](https://sandbox.babylonjs.com/)
- [Three.js Editor](https://threejs.org/editor/)

**Desktop software:**
- Blender: File → Import → glTF 2.0 (.glb)
- Windows 3D Viewer (Windows 10/11)
- Any 3D software supporting GLB/glTF

**Web frameworks:**
- Three.js, Babylon.js, A-Frame, React Three Fiber

**Game engines:**
- Unity, Unreal Engine, Godot

## Troubleshooting

### Blender not found
```bash
python run.py --configure
```
Then enter the correct path to `blender.exe`

### Script failed
Run in GUI mode to see detailed errors:
```bash
python run.py --gui
```

### Check cache
View current configuration:
```bash
cat .blender_cache.json
cat .config_cache.json
```

### Reset everything
```bash
rm .blender_cache.json .config_cache.json
python run.py --configure
```

### Out of memory
Use a lower quality preset:
```bash
python run.py --preset low
```

## How It Works

1. **Load GeoJSON** - Parse country boundaries from Natural Earth data
2. **Create Icosphere** - Generate base globe with configurable subdivision
3. **Project Countries** - Map GeoJSON polygons onto sphere surface using point-in-polygon
4. **Extrude** - Create 3D relief by bidirectional radial extrusion
5. **Generate Borders** - Create 3D border ribbons along country boundaries
6. **Export GLB** - Save final model in glTF binary format

## Testing

The project includes comprehensive unit and integration tests.

### Run Tests

```bash
# Run all tests
python run_tests.py

# Run specific test file
python -m unittest tests.test_blender_runner
python -m unittest tests.test_integration

# Run with pytest (if installed)
pytest tests/ -v
```

### Test Coverage

The test suite covers:
- ✅ Cache operations (load/save)
- ✅ Blender path verification
- ✅ Configuration presets
- ✅ Script argument building
- ✅ Project structure validation
- ✅ README documentation checks
- ✅ Integration workflows

**35 tests** covering critical functionality with **100% pass rate**.

### Continuous Integration

GitHub Actions automatically runs tests on:
- Multiple OS: Ubuntu, Windows, macOS
- Multiple Python versions: 3.8, 3.9, 3.10, 3.11
- Every push to `master` branch
- Every pull request

## Credits

- **Geographic data**: [Natural Earth](https://www.naturalearthdata.com/)
  - Admin 0 - Countries (1:50m)
  - Populated Places (1:50m)
  - License: Public Domain
- **3D engine**: [Blender](https://www.blender.org/)
- **Export format**: [glTF 2.0](https://www.khronos.org/gltf/)

## Data Attribution

This project includes geographic data from [Natural Earth](https://www.naturalearthdata.com/), a public domain map dataset available at 1:10m, 1:50m, and 1:110m scales.

Natural Earth is made available under **Public Domain** terms. No permission is needed to use Natural Earth. Crediting the authors is unnecessary.

## License

**Code**: This project code is provided as-is for educational and creative use.

**Data**: Geographic data from Natural Earth is in the **Public Domain**.
