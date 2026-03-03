#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Blender Runner CLI - Execute run.py with Blender easily
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')


# Anchor caches to the geojsonto3D project root (parent of src)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_FILE = PROJECT_ROOT / ".blender_cache.json"
CONFIG_FILE = PROJECT_ROOT / ".config_cache.json"

PRESETS = {
    # --- ICO (triangular) presets ---
    'low': {
        'ico_subdiv': 3,
        'extrude_above': 0.03,
        'extrude_below': 0.0,
        'border_width': 0.001,
        'border_height': 0.002,
        'enable_borders': True,
        'enable_closing': False,
        'enable_cities': False,
    },
    'medium': {
        'ico_subdiv': 5,
        'extrude_above': 0.05,
        'extrude_below': 0.0,
        'border_width': 0.0006,
        'border_height': 0.002,
        'enable_borders': True,
        'enable_closing': False,
        'enable_cities': False,
    },
    'high': {
        'ico_subdiv': 7,
        'extrude_above': 0.1,
        'extrude_below': 0.0,
        'border_width': 0.0005,
        'border_height': 0.0015,
        'enable_borders': True,
        'enable_closing': True,
        'enable_cities': True,
    },
    'ultra': {
        'ico_subdiv': 7,
        'extrude_above': 0.1,
        'extrude_below': 0.0,
        'border_width': 0.0005,
        'border_height': 0.0015,
        'enable_borders': True,
        'enable_closing': True,
        'enable_cities': True,
    },
    'custom': {
        'ico_subdiv': 7,
        'extrude_above': 0.1,
        'extrude_below': 0.0,
        'border_width': 0.0005,
        'border_height': 0.0015,
        'enable_borders': True,
        'enable_closing': False,
        'enable_cities': False,
    },
    # --- HEX (Goldberg polyhedron) presets ---
    # bmesh.ops.create_icosphere(subdivisions=N) gives 10*4^(N-1)+2 vertices.
    # ico_subdiv=3 -> 162 cells, ico_subdiv=5 -> 2562, ico_subdiv=6 -> 10242
    # hex_label matches ico_subdiv directly.
    'hex-low': {
        'script': 'hex',
        'mode': 'atlas',
        'ico_subdiv': 3,
        'hex_label': 3,
        'extrude_above': 0.0,
        'extrude_below': 0.5,
        'border_width': 0.0006,
        'border_height': 0.002,
        'enable_borders': True,
    },
    'hex-medium': {
        'script': 'hex',
        'mode': 'atlas',
        'ico_subdiv': 5,
        'hex_label': 5,
        'extrude_above': 0.0,
        'extrude_below': 0.5,
        'border_width': 0.0005,
        'border_height': 0.0015,
        'enable_borders': True,
        'min_pass2_votes': 1,  # Lower threshold to capture narrow countries like Panama
    },
    'hex-high': {
        'script': 'hex',
        'mode': 'atlas',
        'ico_subdiv': 6,
        'hex_label': 6,
        'extrude_above': 0.0,
        'extrude_below': 0.5,
        'border_width': 0.0005,
        'border_height': 0.0015,
        'enable_borders': True,
    },
    'weather-hex-low': {
        'script': 'hex',
        'mode': 'weather',
        'ico_subdiv': 3,
        'hex_label': 3,
        'extrude_above': 0.0,
        'extrude_below': 0.5,
        'border_width': 0.0005,
        'border_height': 0.0015,
        'enable_borders': True,
    },
    'weather-hex-medium': {
        'script': 'hex',
        'mode': 'weather',
        'ico_subdiv': 5,
        'hex_label': 5,
        'extrude_above': 0.0,
        'extrude_below': 0.5,
        'border_width': 0.0005,
        'border_height': 0.0015,
        'enable_borders': True,
        'min_pass2_votes': 1,  # Lower threshold to capture narrow countries like Panama
    },
    'weather-hex-high': {
        'script': 'hex',
        'mode': 'weather',
        'ico_subdiv': 6,
        'hex_label': 6,
        'extrude_above': 0.0,
        'extrude_below': 0.5,
        'border_width': 0.0005,
        'border_height': 0.0015,
        'enable_borders': True,
    },
}

# All valid preset names for CLI
ALL_PRESET_NAMES = list(PRESETS.keys())


def load_cache(cache_file):
    """Load cached data from JSON file, with legacy fallback and migration."""
    cache_path = Path(cache_file)
    candidates = [cache_path]
    # Legacy: files created in current working directory or its parent when run from elsewhere
    try:
        candidates.append(Path.cwd() / cache_path.name)
    except Exception:
        pass
    try:
        candidates.append(Path.cwd().parent / cache_path.name)
    except Exception:
        pass

    for p in candidates:
        if p.exists():
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Migrate to canonical location if loaded from legacy path
                if p.resolve() != cache_path.resolve():
                    save_cache(cache_path, data)
                return data
            except (json.JSONDecodeError, IOError):
                continue
    return {}


def save_cache(cache_file, data):
    """Save data to JSON cache file at canonical location."""
    try:
        cache_path = Path(cache_file)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return True
    except IOError:
        return False


def verify_blender(blender_path):
    """Verify that Blender executable works."""
    if not blender_path or not Path(blender_path).exists():
        return False

    try:
        result = subprocess.run(
            [str(blender_path), '--version'],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def get_blender_path(force_ask=False):
    """Get Blender path from cache or user input."""
    cache = load_cache(CACHE_FILE)

    if not force_ask and 'blender_path' in cache:
        blender_path = cache['blender_path']
        if verify_blender(blender_path):
            print(f"✓ Using cached Blender: {blender_path}")
            return blender_path

    print("\n" + "="*60)
    print("Blender Configuration")
    print("="*60)
    print("Enter the path to blender.exe:")
    print("Example: C:\\Program Files\\Blender Foundation\\Blender 4.4\\blender.exe")
    print("-"*60)

    user_input = input("Blender path: ").strip().strip('"').strip("'")

    if not user_input:
        print("✗ No path provided")
        return None

    if verify_blender(user_input):
        blender_path = str(Path(user_input).resolve())
        cache['blender_path'] = blender_path
        save_cache(CACHE_FILE, cache)
        print(f"✓ Blender configured and cached")
        return blender_path
    else:
        print(f"✗ Invalid Blender path")
        return None


def interactive_config():
    """Interactive configuration for generation parameters."""
    print("\n" + "="*60)
    print("Generation Configuration")
    print("="*60)

    # Load cached config
    cache = load_cache(CONFIG_FILE)

    # Preset selection
    print("\nChoose a quality preset:")
    print("  1. low    - Fast (ICO_SUBDIV=3, ~30s)")
    print("  2. medium - Balanced (ICO_SUBDIV=4, ~1-2min)")
    print("  3. high   - Quality (ICO_SUBDIV=5, ~3-5min)")
    print("  4. ultra  - Ultra (ICO_SUBDIV=6, ~10-20min)")
    print("  5. custom - Custom harmonized (ICO_SUBDIV=7, no extrusion)")

    cached_preset = cache.get('preset', '3')
    choice = input(f"\nChoice [1-5] (default: {cached_preset}): ").strip() or cached_preset

    if choice in ['1', '2', '3', '4', '5']:
        preset_name = ['low', 'medium', 'high', 'ultra', 'custom'][int(choice) - 1]
        config = PRESETS[preset_name].copy()
        config['preset'] = choice
        print(f"✓ Using '{preset_name}' preset")

    elif choice == '5':
        print("\n--- Custom Configuration ---")
        config = {}

        # ICO_SUBDIV
        default_subdiv = cache.get('ico_subdiv', 5)
        subdiv = input(f"ICO_SUBDIV [3-7] (default: {default_subdiv}): ").strip()
        config['ico_subdiv'] = int(subdiv) if subdiv else default_subdiv

        # Extrusion
        default_extrude = cache.get('extrude_above', 0.05)
        extrude = input(f"Extrusion height [0.0-0.1] (default: {default_extrude}): ").strip()
        config['extrude_above'] = float(extrude) if extrude else default_extrude
        config['extrude_below'] = config['extrude_above']

        # Borders
        default_borders = cache.get('enable_borders', True)
        borders_str = "y" if default_borders else "n"
        borders = input(f"Enable borders? [y/n] (default: {borders_str}): ").strip().lower()
        config['enable_borders'] = borders == 'y' if borders else default_borders

        if config['enable_borders']:
            config['border_width'] = cache.get('border_width', 0.0005)
            config['border_height'] = cache.get('border_height', 0.0025)

        # Cities
        default_cities = cache.get('enable_cities', False)
        cities_str = "y" if default_cities else "n"
        cities = input(f"Enable cities? [y/n] (default: {cities_str}): ").strip().lower()
        config['enable_cities'] = cities == 'y' if cities else default_cities

        config['preset'] = '5'

    else:
        print("✗ Invalid choice, using defaults")
        config = PRESETS['high'].copy()
        config['preset'] = '3'

    # Save config
    save_cache(CONFIG_FILE, config)

    return config


def get_config(force_interactive=False, preset=None):
    """Get configuration from cache, preset, or interactive input."""
    if preset and preset in PRESETS:
        config = PRESETS[preset].copy()
        save_cache(CONFIG_FILE, config)
        return config

    if force_interactive:
        return interactive_config()

    # Try to load cached config
    config = load_cache(CONFIG_FILE)
    if config and 'ico_subdiv' in config:
        print(f"✓ Using cached configuration")
        return config

    # No cache, ask interactively
    return interactive_config()


def build_script_args(config):
    """Build command line arguments for run.py or hex_run.py from config."""
    args = []
    is_hex = config.get('script') == 'hex'

    args.extend(['--ico-subdiv', str(config.get('ico_subdiv', 5))])
    args.extend(['--extrude-above', str(config.get('extrude_above', 0.05))])
    args.extend(['--extrude-below', str(config.get('extrude_below', 0.05))])

    if config.get('enable_borders', True):
        args.append('--enable-border')
        args.extend(['--border-width', str(config.get('border_width', 0.0005))])
        args.extend(['--border-height', str(config.get('border_height', 0.0025))])
    else:
        args.append('--disable-border')

    if is_hex:
        # Hex-specific arguments
        if 'hex_label' in config:
            args.extend(['--hex-label', str(config['hex_label'])])
        if 'mode' in config:
            args.extend(['--mode', config['mode']])
        if 'min_pass2_votes' in config:
            args.extend(['--min-pass2-votes', str(config['min_pass2_votes'])])
    else:
        # ICO-specific arguments
        if config.get('enable_closing', False):
            args.append('--enable-closing')
        else:
            args.append('--disable-closing')

        if config.get('enable_cities', False):
            args.append('--enable-cities')
        else:
            args.append('--disable-cities')

    return args


def get_script_path(config, override=None):
    """Determine which Blender script to use based on config."""
    if override:
        return override
    if config.get('script') == 'hex':
        return str(Path(__file__).parent / 'hex_run.py')
    return str(Path(__file__).parent / 'run.py')


def run_blender(blender_path, script_path, args, background=True):
    """Execute Blender with the script."""
    cmd = [blender_path]

    if background:
        cmd.append('--background')

    cmd.extend(['--python', str(script_path)])

    if args:
        cmd.append('--')
        cmd.extend(args)

    print("\n" + "="*60)
    print("Executing Blender")
    print("="*60)
    print(f"Script: {script_path}")
    print(f"Mode:   {'Background' if background else 'GUI'}")
    print("-"*60 + "\n")

    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode == 0
    except KeyboardInterrupt:
        print("\n✗ Interrupted by user")
        return False
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Blender Runner CLI - GeoJSON to 3D Globe Generator',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--blender', '-b',
        type=str,
        help='Path to blender.exe (cached for future use)'
    )

    parser.add_argument(
        '--script', '-s',
        type=str,
        default=str(Path(__file__).parent / 'run.py'),
        help='Python script to execute (default: src/run.py)'
    )

    parser.add_argument(
        '--gui', '-g',
        action='store_true',
        help='Run with Blender GUI (default: background)'
    )

    parser.add_argument(
        '--configure', '-c',
        action='store_true',
        help='Reconfigure all settings'
    )

    parser.add_argument(
        '--preset', '-p',
        type=str,
        choices=ALL_PRESET_NAMES,
        help='Use quality preset (ico: low/medium/high/ultra | hex: hex-low/hex-medium/hex-high | weather: weather-hex-low/weather-hex-medium/weather-hex-high)'
    )

    args = parser.parse_args()

    # Get Blender path
    blender_path = get_blender_path(force_ask=args.configure or bool(args.blender))

    if args.blender:
        # Override with provided path
        if verify_blender(args.blender):
            blender_path = str(Path(args.blender).resolve())
            cache = load_cache(CACHE_FILE)
            cache['blender_path'] = blender_path
            save_cache(CACHE_FILE, cache)
        else:
            print("✗ Provided Blender path is invalid")
            return 1

    if not blender_path:
        print("\n✗ No valid Blender path configured")
        return 1

    # Get configuration
    config = get_config(force_interactive=args.configure, preset=args.preset)

    # Determine script path (hex presets auto-select hex_run.py)
    script_path = get_script_path(config, override=args.script if args.script != str(Path(__file__).parent / 'run.py') else None)

    # Build script arguments
    script_args = build_script_args(config)

    # Run Blender
    success = run_blender(
        blender_path,
        script_path,
        script_args,
        background=not args.gui
    )

    if success:
        print("\n" + "="*60)
        print("✓ Generation completed successfully!")
        print("="*60)
        is_hex = config.get('script') == 'hex'
        subdiv = config.get('ico_subdiv', 5)
        if is_hex:
            label = config.get('hex_label', subdiv + 1)
            mode = config.get('mode', 'atlas')
            if mode == 'weather':
                print(f"\nOutput: weather_hex_globe_subdiv_{label}.glb")
            else:
                print(f"\nOutput: atlas_hex_subdiv_{label}.glb")
        else:
            print(f"\nOutput: atlas_ico_subdiv_{subdiv}.glb")
        return 0
    else:
        print("\n" + "="*60)
        print("✗ Generation failed")
        print("="*60)
        return 1


if __name__ == '__main__':
    sys.exit(main())
