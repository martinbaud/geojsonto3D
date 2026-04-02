"""
Geometric unit tests for geo_utils.

Tests the core mathematical functions used to project
GeoJSON coordinates onto a 3D sphere.
"""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from geo_utils import xyz_to_latlon, point_in_poly


class TestXyzToLatlon(unittest.TestCase):
    """Test Cartesian to lat/lon conversion."""

    def test_north_pole(self):
        lat, lon = xyz_to_latlon(0, 0, 1)
        self.assertAlmostEqual(lat, 90.0, places=5)

    def test_south_pole(self):
        lat, lon = xyz_to_latlon(0, 0, -1)
        self.assertAlmostEqual(lat, -90.0, places=5)

    def test_equator_prime_meridian(self):
        lat, lon = xyz_to_latlon(1, 0, 0)
        self.assertAlmostEqual(lat, 0.0, places=5)
        self.assertAlmostEqual(lon, 0.0, places=5)

    def test_equator_90e(self):
        lat, lon = xyz_to_latlon(0, 1, 0)
        self.assertAlmostEqual(lat, 0.0, places=5)
        self.assertAlmostEqual(lon, 90.0, places=5)

    def test_equator_180(self):
        lat, lon = xyz_to_latlon(-1, 0, 0)
        self.assertAlmostEqual(lat, 0.0, places=5)
        self.assertAlmostEqual(abs(lon), 180.0, places=5)

    def test_equator_90w(self):
        lat, lon = xyz_to_latlon(0, -1, 0)
        self.assertAlmostEqual(lat, 0.0, places=5)
        self.assertAlmostEqual(lon, -90.0, places=5)

    def test_arbitrary_point(self):
        """Paris is roughly at lat 48.86, lon 2.35."""
        lat_rad = math.radians(48.86)
        lon_rad = math.radians(2.35)
        x = math.cos(lat_rad) * math.cos(lon_rad)
        y = math.cos(lat_rad) * math.sin(lon_rad)
        z = math.sin(lat_rad)
        lat, lon = xyz_to_latlon(x, y, z)
        self.assertAlmostEqual(lat, 48.86, places=2)
        self.assertAlmostEqual(lon, 2.35, places=2)

    def test_zero_vector(self):
        lat, lon = xyz_to_latlon(0, 0, 0)
        self.assertEqual(lat, 0.0)
        self.assertEqual(lon, 0.0)

    def test_scaled_vector(self):
        """Result should be the same regardless of radius."""
        lat1, lon1 = xyz_to_latlon(1, 1, 1)
        lat2, lon2 = xyz_to_latlon(100, 100, 100)
        self.assertAlmostEqual(lat1, lat2, places=5)
        self.assertAlmostEqual(lon1, lon2, places=5)

    def test_roundtrip(self):
        """Convert lat/lon -> xyz -> lat/lon should be identity."""
        for lat_in, lon_in in [(0, 0), (45, 90), (-30, -60), (89, 170)]:
            lat_r = math.radians(lat_in)
            lon_r = math.radians(lon_in)
            x = math.cos(lat_r) * math.cos(lon_r)
            y = math.cos(lat_r) * math.sin(lon_r)
            z = math.sin(lat_r)
            lat_out, lon_out = xyz_to_latlon(x, y, z)
            self.assertAlmostEqual(lat_out, lat_in, places=4)
            self.assertAlmostEqual(lon_out, lon_in, places=4)


class TestPointInPoly(unittest.TestCase):
    """Test ray-casting point-in-polygon."""

    def setUp(self):
        """Simple unit square polygon."""
        self.square = [(0, 0), (10, 0), (10, 10), (0, 10)]

    def test_inside(self):
        self.assertTrue(point_in_poly(5, 5, self.square))

    def test_outside(self):
        self.assertFalse(point_in_poly(15, 5, self.square))

    def test_outside_negative(self):
        self.assertFalse(point_in_poly(-1, -1, self.square))

    def test_near_edge(self):
        """Point clearly inside, close to edge."""
        self.assertTrue(point_in_poly(0.1, 0.1, self.square))

    def test_triangle(self):
        triangle = [(0, 0), (10, 0), (5, 10)]
        self.assertTrue(point_in_poly(5, 3, triangle))
        self.assertFalse(point_in_poly(9, 9, triangle))

    def test_concave_polygon(self):
        """L-shaped polygon."""
        l_shape = [(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)]
        self.assertTrue(point_in_poly(2, 2, l_shape))  # inside bottom
        self.assertTrue(point_in_poly(2, 8, l_shape))  # inside top-left
        self.assertFalse(point_in_poly(8, 8, l_shape))  # outside top-right notch

    def test_empty_polygon(self):
        self.assertFalse(point_in_poly(0, 0, []))

    def test_france_rough(self):
        """France is roughly inside a bounding polygon."""
        france_rough = [(-5, 42), (9, 42), (9, 51), (-5, 51)]
        self.assertTrue(point_in_poly(2.35, 48.86, france_rough))  # Paris
        self.assertFalse(point_in_poly(-10, 40, france_rough))  # Atlantic


if __name__ == "__main__":
    unittest.main()
