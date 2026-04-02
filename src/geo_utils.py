"""
Shared geometric utilities for GeoJSON to 3D globe generation.

These functions are used by both run.py (ICO) and hex_run.py (Goldberg hex)
and contain no Blender (bpy) dependencies.
"""

from __future__ import annotations

import math
from typing import Sequence


def xyz_to_latlon(x: float, y: float, z: float) -> tuple[float, float]:
    """Convert 3D Cartesian coordinates to (latitude, longitude) in degrees."""
    r = math.sqrt(x * x + y * y + z * z)
    if r < 1e-10:
        return 0.0, 0.0
    return (
        math.degrees(math.asin(max(-1.0, min(1.0, z / r)))),
        math.degrees(math.atan2(y, x)),
    )


def point_in_poly(lon: float, lat: float, poly: Sequence[tuple[float, float]]) -> bool:
    """Ray-casting algorithm to test if a point is inside a polygon."""
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if ((y1 > lat) != (y2 > lat)) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside
