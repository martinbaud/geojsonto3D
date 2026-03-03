#!/usr/bin/env python
"""
GeoJSON to 3D Globe - Main Launcher
Launch the Blender-based 3D globe generation process
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from blender_runner import main

if __name__ == '__main__':
    main()