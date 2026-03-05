#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Goldberg Polyhedron Hex Globe Generator

Generates hex/pent globe meshes by computing the dual of a Blender icosphere.
Each icosphere vertex becomes a hexagonal (or pentagonal) cell.

Supports two modes:
  - atlas:   Countries grouped by name, with borders and extrusion
  - weather: Individual cells with mapping JSON for weather data overlay

Output naming conventions:
  - Atlas:   atlas_hex_subdiv_{label}.glb
  - Weather: weather_hex_globe_subdiv_{label}.glb + .mapping.json
"""

import bpy
import json
import math
import bmesh
import sys
from mathutils import Vector
from datetime import datetime
from pathlib import Path

# --- CONFIGURATION (overridable via CLI) ------------------------------------
PROJECT_ROOT = (
    Path(bpy.path.abspath("//")).parent
    if "//" in bpy.path.abspath("//")
    else Path(__file__).parent.parent
)
DATA_DIR = PROJECT_ROOT / "data"
RES_DIR = PROJECT_ROOT / "res"
RES_DIR.mkdir(exist_ok=True)

GEOJSON_COUNTRIES = str(DATA_DIR / "ne_50m_admin_0_countries.geojson")
GEOJSON_PLACES = str(DATA_DIR / "ne_50m_populated_places.json")

RADIUS = 1.0
ICO_SUBDIV = 4          # Blender icosphere subdivision (dual -> hex cells)
HEX_LABEL = None         # Output filename label (default: ICO_SUBDIV + 1)
MODE = "atlas"            # "atlas" or "weather"

EXTRUDE_ABOVE = 0.02
EXTRUDE_BELOW = 0.0
BORDER_WIDTH = 0.0005
BORDER_HEIGHT = 0.0015
EMBED_EPS = 0.0002

ENABLE_BORDER = True
ENABLE_EXTRUSION = True
ENABLE_CITIES = False

# City configuration
CITY_MAX = 200              # Max cities to generate
CITY_MARKER_RADIUS = 0.006  # Radius of city marker base
CITY_MARKER_SIDES = 6       # Hexagonal prism (matches hex globe)
CITY_MARKER_HEIGHT = 0.03  # Height above cell surface (doubled for visibility)
CITY_BORDER_WIDTH = 0.0004  # Width of city border ring
CITY_BORDER_HEIGHT = 0.001  # Height of city border ring
EXTRUDE_ABOVE_CITY = CITY_MARKER_HEIGHT

# Minimum vertex votes required for pass-2 rescue of narrow countries.
# Use 2 for high subdivision (ico_subdiv >= 6, small cells).
# Use 3 for medium subdivision (ico_subdiv=5) to avoid false assignments
# across narrow water bodies like the Mediterranean (~200km wide vs ~477km cells).
MIN_PASS2_VOTES = 2

BATCH_LOG = 50            # Progress log interval

# --- CLI PARSING ------------------------------------------------------------
if "--" in sys.argv:
    _args = sys.argv[sys.argv.index("--") + 1:]
    _i = 0
    while _i < len(_args):
        _a = _args[_i]
        if _a == "--ico-subdiv" and _i + 1 < len(_args):
            ICO_SUBDIV = int(_args[_i + 1]); _i += 2
        elif _a == "--hex-label" and _i + 1 < len(_args):
            HEX_LABEL = int(_args[_i + 1]); _i += 2
        elif _a == "--mode" and _i + 1 < len(_args):
            MODE = _args[_i + 1]; _i += 2
        elif _a == "--extrude-above" and _i + 1 < len(_args):
            EXTRUDE_ABOVE = float(_args[_i + 1]); _i += 2
        elif _a == "--extrude-below" and _i + 1 < len(_args):
            EXTRUDE_BELOW = float(_args[_i + 1]); _i += 2
        elif _a == "--border-width" and _i + 1 < len(_args):
            BORDER_WIDTH = float(_args[_i + 1]); _i += 2
        elif _a == "--border-height" and _i + 1 < len(_args):
            BORDER_HEIGHT = float(_args[_i + 1]); _i += 2
        elif _a in ("--enable-border", "--enable-borders"):
            ENABLE_BORDER = True; _i += 1
        elif _a in ("--disable-border", "--disable-borders"):
            ENABLE_BORDER = False; _i += 1
        elif _a == "--enable-extrusion":
            ENABLE_EXTRUSION = True; _i += 1
        elif _a == "--disable-extrusion":
            ENABLE_EXTRUSION = False; _i += 1
        elif _a == "--min-pass2-votes" and _i + 1 < len(_args):
            MIN_PASS2_VOTES = int(_args[_i + 1]); _i += 2
        elif _a in ("--enable-cities",):
            ENABLE_CITIES = True; _i += 1
        elif _a in ("--disable-cities",):
            ENABLE_CITIES = False; _i += 1
        elif _a == "--city-max" and _i + 1 < len(_args):
            CITY_MAX = int(_args[_i + 1]); _i += 2
        else:
            _i += 1

if HEX_LABEL is None:
    HEX_LABEL = ICO_SUBDIV

# Output paths
if MODE == "weather":
    PARENT_NAME = "WeatherGlobe"
    OUT_GLB = str(RES_DIR / f"weather_hex_globe_subdiv_{HEX_LABEL}.glb")
    OUT_MAPPING = str(RES_DIR / f"weather_hex_globe_subdiv_{HEX_LABEL}.mapping.json")
    GLOBE_FILL_NAME = "WeatherGlobeFill"
else:
    PARENT_NAME = "Atlas"
    OUT_GLB = str(RES_DIR / f"atlas_hex_subdiv_{HEX_LABEL}.glb")
    OUT_MAPPING = None
    GLOBE_FILL_NAME = "GlobeFill"

OUT_CFG = OUT_GLB.replace(".glb", ".config.json")


# --- UTILITY FUNCTIONS ------------------------------------------------------
def xyz_to_latlon(v):
    """Convert 3D Cartesian to (latitude, longitude) in degrees."""
    r = v.length
    if r < 1e-10:
        return 0.0, 0.0
    return (
        math.degrees(math.asin(max(-1.0, min(1.0, v.z / r)))),
        math.degrees(math.atan2(v.y, v.x)),
    )


def point_in_poly(lon, lat, poly):
    """Ray-casting point-in-polygon test."""
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if ((y1 > lat) != (y2 > lat)) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def select_hierarchy(obj):
    """Recursively select object and all children."""
    obj.select_set(True)
    for c in obj.children:
        select_hierarchy(c)


def new_mesh_object(name, verts, faces, parent=None, smooth=True):
    """Create a Blender mesh object from vertices and face index lists."""
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    if smooth:
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.shade_smooth()
    if parent:
        obj.parent = parent
    return obj


# --- GOLDBERG DUAL MESH -----------------------------------------------------
def compute_goldberg_cells(ico_subdiv, radius):
    """
    Compute Goldberg polyhedron cells as the dual of a Blender icosphere.

    Algorithm:
      1. Create icosphere with bmesh
      2. For each vertex, walk adjacent faces in winding order via BMesh loops
      3. Collect face centroids -> these form the hex/pent cell polygon
      4. Project cell vertices to the sphere surface

    Returns: list of dicts with keys 'verts' (list[Vector]), 'centroid' (Vector), 'sides' (int)
    """
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=ico_subdiv, radius=radius)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    total = len(bm.verts)
    cells = []

    for vi, vert in enumerate(bm.verts):
        if vi % BATCH_LOG == 0:
            print(f"  Computing dual cells: {vi}/{total} ({vi * 100 / total:.0f}%)")

        if not vert.link_loops:
            continue

        # Walk faces around vertex in winding order using BMesh loop navigation.
        # For each face, take the centroid and project it to the sphere surface.
        first_loop = vert.link_loops[0]
        loop = first_loop
        face_centroids = []
        safety = 0

        while safety < 8:
            centroid = loop.face.calc_center_median()
            face_centroids.append(centroid.normalized() * radius)

            # Navigate to the next face around the vertex:
            #   link_loop_prev -> the loop ending at our vertex (shares the "previous" edge)
            #   link_loop_radial_next -> cross that edge to the adjacent face
            # The result is a loop at our vertex in the next face (consistent winding).
            loop = loop.link_loop_prev.link_loop_radial_next
            safety += 1
            if loop == first_loop:
                break

        if len(face_centroids) >= 3:
            cells.append({
                'verts': face_centroids,
                'centroid': vert.co.normalized() * radius,
                'sides': len(face_centroids),
            })

    bm.free()
    return cells


# --- COUNTRY ASSIGNMENT -----------------------------------------------------
def load_geojson_features(path):
    """Load and parse GeoJSON country polygons."""
    with open(path, encoding='utf-8') as f:
        gj = json.load(f)

    features = []
    for feat in gj.get("features", []):
        name = feat["properties"]["ADMIN"]
        geom = feat.get("geometry", {})
        if not geom:
            continue
        polys = (
            geom["coordinates"]
            if geom["type"] == "MultiPolygon"
            else [geom["coordinates"]]
        )
        for idx, poly in enumerate(polys):
            rings = []
            for ring in poly:
                pts = [(lon, lat) for lon, lat in ring if isinstance(lon, (int, float))]
                if len(pts) >= 3:
                    rings.append(pts)
            if not rings:
                continue
            outer = rings[0]
            bbox = (
                min(x for x, y in outer), max(x for x, y in outer),
                min(y for x, y in outer), max(y for x, y in outer),
            )
            features.append({"name": f"{name}_{idx}", "admin": name, "rings": rings, "bbox": bbox})

    return features


def assign_cells_to_countries(cells, features):
    """
    Two-pass country assignment:

    Pass 1 (centroid): Fast and precise — preserves ocean gaps like the
    Mediterranean and Caribbean by only assigning cells whose centroid
    lands inside a country polygon.

    Pass 2 (vertex vote): For cells still unassigned after pass 1, test
    all cell vertices. A country wins only if >= 2 vertices fall inside it.
    This rescues narrow countries (Panama, El Salvador, ...) whose centroid
    falls in the ocean but whose shape overlaps 2+ cell vertices, while
    rejecting coastal ocean cells where only 1 vertex grazes land.
    """
    assignments = [None] * len(cells)
    total = len(cells)
    pass2_rescued = 0

    for idx, cell in enumerate(cells):
        if idx % BATCH_LOG == 0:
            print(f"  Assigning cells: {idx}/{total} ({idx * 100 / total:.0f}%)")

        lat, lon = xyz_to_latlon(cell['centroid'])
        cell['lat'] = lat
        cell['lon'] = lon

        # --- Pass 1: centroid ---
        for feat in features:
            minx, maxx, miny, maxy = feat["bbox"]
            if not (minx <= lon <= maxx and miny <= lat <= maxy):
                continue
            if point_in_poly(lon, lat, feat["rings"][0]):
                assignments[idx] = feat["name"]
                cell['admin'] = feat["admin"]
                break

        if assignments[idx] is not None:
            continue

        # --- Pass 2: vertex vote (requires >= 2 vertex hits for same country) ---
        votes = {}
        for v in cell['verts']:
            vlat, vlon = xyz_to_latlon(v)
            for feat in features:
                minx, maxx, miny, maxy = feat["bbox"]
                if not (minx <= vlon <= maxx and miny <= vlat <= maxy):
                    continue
                if point_in_poly(vlon, vlat, feat["rings"][0]):
                    key = feat["name"]
                    votes[key] = votes.get(key, 0) + 1
                    break  # one country per vertex

        if votes:
            best_name, best_count = max(votes.items(), key=lambda x: x[1])
            if best_count >= MIN_PASS2_VOTES:
                for feat in features:
                    if feat["name"] == best_name:
                        assignments[idx] = feat["name"]
                        cell['admin'] = feat["admin"]
                        pass2_rescued += 1
                        break

    print(f"  Pass 2 rescued {pass2_rescued} narrow-country cells")
    return assignments


# --- MESH CREATION -----------------------------------------------------------
def create_cell_mesh(name, cell_verts_list, parent=None, merge_verts=True):
    """
    Create a Blender mesh from a list of cell vertex lists.

    When merge_verts=True, vertices at the same position are shared.
    This is critical for atlas mode so that interior edges between
    same-country cells are not treated as boundary edges.
    """
    if merge_verts:
        vert_map = {}
        all_verts = []
        all_faces = []

        for cell_verts in cell_verts_list:
            face = []
            for v in cell_verts:
                key = (round(v.x, 6), round(v.y, 6), round(v.z, 6))
                if key not in vert_map:
                    vert_map[key] = len(all_verts)
                    all_verts.append(v)
                face.append(vert_map[key])
            all_faces.append(face)
    else:
        all_verts = []
        all_faces = []
        offset = 0
        for cell_verts in cell_verts_list:
            n = len(cell_verts)
            all_verts.extend(cell_verts)
            all_faces.append(list(range(offset, offset + n)))
            offset += n

    obj = new_mesh_object(name, all_verts, all_faces, parent=parent, smooth=True)

    # Ensure outward-facing normals
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()

    return obj


# --- RADIAL EXTRUSION -------------------------------------------------------
def extrude_mesh_radially_bi(obj, depth_above, depth_below):
    """Bidirectional radial extrusion aligned to the base sphere."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()

    # Normalize all verts to the base sphere
    for v in bm.verts:
        v.co = v.co.normalized() * RADIUS

    if depth_above > 0:
        res_up = bmesh.ops.extrude_face_region(bm, geom=bm.faces)
        verts_up = [v for v in res_up["geom"] if isinstance(v, bmesh.types.BMVert)]
        for v in verts_up:
            v.co = v.co.normalized() * (RADIUS + depth_above)

    if depth_below > 0:
        res_down = bmesh.ops.extrude_face_region(bm, geom=bm.faces)
        verts_down = [v for v in res_down["geom"] if isinstance(v, bmesh.types.BMVert)]
        for v in verts_down:
            v.co = v.co.normalized() * (RADIUS - depth_below)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()


# --- BORDER RIBBONS ----------------------------------------------------------
def create_border_ribbons(source_obj, above, name_prefix, parent,
                          width=BORDER_WIDTH, height=BORDER_HEIGHT):
    """
    Generate 3D border ribbons on boundary edges of a mesh.

    Boundary edges (shared by only 1 face) represent country outlines.
    Ribbons are projected to the top surface (RADIUS + above).
    """
    bm = bmesh.new()
    bm.from_mesh(source_obj.data)
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    boundary_edges = [e for e in bm.edges if len(e.link_faces) == 1]
    if not boundary_edges:
        bm.free()
        return None

    bm_out = bmesh.new()

    for e in boundary_edges:
        v1o = e.verts[0].co.copy()
        v2o = e.verts[1].co.copy()

        # Project vertices to top surface, slightly embedded
        v1_top = v1o.normalized() * (RADIUS + above - EMBED_EPS)
        v2_top = v2o.normalized() * (RADIUS + above - EMBED_EPS)

        edge_dir = v2_top - v1_top
        if edge_dir.length < 1e-10:
            continue
        edge_dir.normalize()

        # Perpendicular in the tangent plane
        perp1 = v1_top.normalized().cross(edge_dir).normalized()
        perp2 = v2_top.normalized().cross(edge_dir).normalized()

        v1a = v1_top + perp1 * (width / 2)
        v1b = v1_top - perp1 * (width / 2)
        v2a = v2_top + perp2 * (width / 2)
        v2b = v2_top - perp2 * (width / 2)

        ring = [v1a, v2a, v2b, v1b]
        top = [p + p.normalized() * height for p in ring]

        verts_all = ring + top
        verts_new = [bm_out.verts.new(co) for co in verts_all]

        faces_idx = [
            (0, 1, 5, 4),  # front
            (1, 2, 6, 5),  # right
            (2, 3, 7, 6),  # back
            (3, 0, 4, 7),  # left
            (4, 5, 6, 7),  # top cap
        ]
        for fidx in faces_idx:
            try:
                bm_out.faces.new([verts_new[i] for i in fidx])
            except ValueError:
                pass

    bm_out.normal_update()

    # Derive clean object name
    src_name = source_obj.name
    for pfx in ("country_", "cell_", "_temp_group_"):
        if src_name.startswith(pfx):
            src_name = src_name[len(pfx):]
            break
    target_name = f"{name_prefix}_{src_name}"

    me = bpy.data.meshes.new(target_name)
    bm_out.to_mesh(me)
    bm_out.free()
    bm.free()

    ob = bpy.data.objects.new(target_name, me)
    bpy.context.collection.objects.link(ob)
    ob.parent = parent
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.shade_smooth()
    return ob


# --- CITY GENERATION ---------------------------------------------------------
def load_places_data(path):
    """Load city/places data from Natural Earth JSON."""
    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    places = []
    # Handle both GeoJSON FeatureCollection and raw array
    items = data.get('features', data) if isinstance(data, dict) else data

    for item in items:
        props = item.get('properties', item)
        geom = item.get('geometry', {})

        # Extract coordinates (GeoJSON or flat schema)
        if geom and geom.get('type') == 'Point':
            lon, lat = geom['coordinates']
        else:
            lat = props.get('LATITUDE') or props.get('LAT') or props.get('LATDD')
            lon = props.get('LONGITUDE') or props.get('LON') or props.get('LONDD')

        if lat is None or lon is None:
            continue

        name = props.get('NAME') or props.get('NAMEASCII') or 'Unknown'
        pop = props.get('POP_MAX') or props.get('pop_max') or 0

        # Clean name for mesh naming
        name_clean = ''.join(c if c.isalnum() else '_' for c in name)

        places.append({
            "name": name_clean,
            "lon": lon,
            "lat": lat,
            "pop": pop,
        })

    # Sort by population descending
    places.sort(key=lambda p: p['pop'], reverse=True)
    return places


def create_city_marker(name, lat_deg, lon_deg, above=EXTRUDE_ABOVE_CITY,
                       radius=CITY_MARKER_RADIUS, sides=CITY_MARKER_SIDES,
                       parent=None):
    """
    Create a hexagonal prism city marker oriented to the globe surface.
    """
    lat_rad = math.radians(lat_deg)
    lon_rad = math.radians(lon_deg)

    # Surface normal direction
    n = Vector((
        math.cos(lat_rad) * math.cos(lon_rad),
        math.cos(lat_rad) * math.sin(lon_rad),
        math.sin(lat_rad),
    )).normalized()

    # Create tangent vectors
    up = Vector((0, 0, 1))
    if abs(n.dot(up)) > 0.99:
        up = Vector((1, 0, 0))
    tangent_u = n.cross(up).normalized()
    tangent_v = n.cross(tangent_u).normalized()

    # Base center on globe surface
    base_center = n * (RADIUS + above - EMBED_EPS)

    # Create base vertices (hexagon)
    base_verts = []
    for i in range(sides):
        angle = 2 * math.pi * i / sides
        offset = tangent_u * (radius * math.cos(angle)) + tangent_v * (radius * math.sin(angle))
        base_verts.append(base_center + offset)

    # Top vertices (extruded along normal)
    top_verts = [v + n * above for v in base_verts]

    # Create mesh
    bm = bmesh.new()
    bm_base = [bm.verts.new(v) for v in base_verts]
    bm_top = [bm.verts.new(v) for v in top_verts]

    # Bottom face
    bm.faces.new(bm_base[::-1])
    # Top face
    bm.faces.new(bm_top)
    # Side faces
    for i in range(sides):
        j = (i + 1) % sides
        bm.faces.new([bm_base[i], bm_base[j], bm_top[j], bm_top[i]])

    bm.normal_update()

    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()

    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    if parent:
        obj.parent = parent
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.shade_smooth()

    return obj


def create_city_border(name, lat_deg, lon_deg, above=EXTRUDE_ABOVE_CITY,
                       radius=CITY_MARKER_RADIUS, sides=CITY_MARKER_SIDES,
                       width=CITY_BORDER_WIDTH, height=CITY_BORDER_HEIGHT,
                       parent=None):
    """
    Create a hexagonal border ring around a city marker.
    """
    lat_rad = math.radians(lat_deg)
    lon_rad = math.radians(lon_deg)

    # Surface normal direction
    n = Vector((
        math.cos(lat_rad) * math.cos(lon_rad),
        math.cos(lat_rad) * math.sin(lon_rad),
        math.sin(lat_rad),
    )).normalized()

    # Create tangent vectors
    up = Vector((0, 0, 1))
    if abs(n.dot(up)) > 0.99:
        up = Vector((1, 0, 0))
    tangent_u = n.cross(up).normalized()
    tangent_v = n.cross(tangent_u).normalized()

    # Border sits at the TOP of the city marker (front face)
    # City top is at: base + n * above, so border center = RADIUS + 2*above - EMBED_EPS
    base_center = n * (RADIUS + 2 * above - EMBED_EPS)

    # Inner and outer radius for the border ring
    inner_radius = radius + width * 0.5
    outer_radius = radius + width * 1.5

    # Create vertices for hexagonal ring
    bm = bmesh.new()
    inner_bottom = []
    outer_bottom = []
    inner_top = []
    outer_top = []

    for i in range(sides):
        angle = 2 * math.pi * i / sides
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)

        inner_offset = tangent_u * (inner_radius * cos_a) + tangent_v * (inner_radius * sin_a)
        outer_offset = tangent_u * (outer_radius * cos_a) + tangent_v * (outer_radius * sin_a)

        inner_bottom.append(bm.verts.new(base_center + inner_offset))
        outer_bottom.append(bm.verts.new(base_center + outer_offset))
        inner_top.append(bm.verts.new(base_center + inner_offset + n * height))
        outer_top.append(bm.verts.new(base_center + outer_offset + n * height))

    # Create faces for the ring
    for i in range(sides):
        j = (i + 1) % sides
        # Top face (outer ring surface)
        bm.faces.new([outer_top[i], outer_top[j], inner_top[j], inner_top[i]])
        # Outer side face
        bm.faces.new([outer_bottom[i], outer_bottom[j], outer_top[j], outer_top[i]])
        # Inner side face
        bm.faces.new([inner_top[i], inner_top[j], inner_bottom[j], inner_bottom[i]])
        # Bottom face
        bm.faces.new([inner_bottom[i], inner_bottom[j], outer_bottom[j], outer_bottom[i]])

    bm.normal_update()

    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()

    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    if parent:
        obj.parent = parent
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.shade_smooth()

    return obj


def find_cell_for_city(lat, lon, cells, cell_countries, features):
    """
    Find the best cell for a city based on:
    1. Country containing the city
    2. Closest cell centroid belonging to that country
    """
    # Find which country contains this city
    city_country = None
    for feat in features:
        minx, maxx, miny, maxy = feat["bbox"]
        if not (minx <= lon <= maxx and miny <= lat <= maxy):
            continue
        if point_in_poly(lon, lat, feat["rings"][0]):
            city_country = feat["admin"]
            break

    if not city_country:
        return None, None

    # Find closest cell in that country
    city_dir = Vector((
        math.cos(math.radians(lat)) * math.cos(math.radians(lon)),
        math.cos(math.radians(lat)) * math.sin(math.radians(lon)),
        math.sin(math.radians(lat)),
    )).normalized()

    best_cell_idx = None
    best_dot = -1

    for idx, (cell, country) in enumerate(zip(cells, cell_countries)):
        if country is None:
            continue
        # Get admin name from cell
        cell_admin = cell.get('admin')
        if cell_admin != city_country:
            continue
        cell_dir = cell['centroid'].normalized()
        dot = city_dir.dot(cell_dir)
        if dot > best_dot:
            best_dot = dot
            best_cell_idx = idx

    return best_cell_idx, city_country


# =============================================================================
# MAIN
# =============================================================================
print("=" * 60)
print("Goldberg Polyhedron Hex Globe Generator")
print("=" * 60)
print(f"  Mode:            {MODE}")
print(f"  ICO subdivision: {ICO_SUBDIV}")
print(f"  Hex label:       {HEX_LABEL}")
print(f"  Extrusion:       above={EXTRUDE_ABOVE}, below={EXTRUDE_BELOW}")
print(f"  Borders:         {'ON' if ENABLE_BORDER else 'OFF'} (w={BORDER_WIDTH}, h={BORDER_HEIGHT})")
print(f"  Cities:          {'ON' if ENABLE_CITIES else 'OFF'} (max={CITY_MAX})")
print(f"  Output:          {OUT_GLB}")
print("-" * 60)

# --- Load GeoJSON -----------------------------------------------------------
print("\nLoading GeoJSON...")
features = load_geojson_features(GEOJSON_COUNTRIES)
print(f"  {len(features)} country polygons loaded")

# --- Compute Goldberg dual cells --------------------------------------------
print("\nComputing Goldberg polyhedron dual mesh...")
cells = compute_goldberg_cells(ICO_SUBDIV, RADIUS)
n_pent = sum(1 for c in cells if c['sides'] == 5)
n_hex = sum(1 for c in cells if c['sides'] == 6)
print(f"  {len(cells)} cells ({n_pent} pentagons, {n_hex} hexagons)")

# --- Assign cells to countries ----------------------------------------------
print("\nAssigning cells to countries...")
cell_countries = assign_cells_to_countries(cells, features)
n_assigned = sum(1 for c in cell_countries if c is not None)
print(f"  {n_assigned}/{len(cells)} cells assigned to countries")

# --- Scene setup ------------------------------------------------------------
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
parent = bpy.data.objects.new(PARENT_NAME, None)
bpy.context.collection.objects.link(parent)

# Group cells
country_cells = {}    # {feature_name: [(global_idx, cell), ...]}
ocean_cells = []       # [(global_idx, cell), ...]

# City objects (populated in atlas mode if enabled)
city_objs = []
city_border_objs = []

for idx, (cell, country) in enumerate(zip(cells, cell_countries)):
    if country:
        country_cells.setdefault(country, []).append((idx, cell))
    else:
        ocean_cells.append((idx, cell))

# --- Create GlobeFill (ocean) -----------------------------------------------
print(f"\nCreating {GLOBE_FILL_NAME} ({len(ocean_cells)} ocean cells)...")
if ocean_cells:
    ocean_verts = [cell['verts'] for _, cell in ocean_cells]
    create_cell_mesh(GLOBE_FILL_NAME, ocean_verts, parent=parent, merge_verts=True)


# =============================================================================
# ATLAS MODE
# =============================================================================
if MODE == "atlas":
    print(f"\n--- Atlas Mode: {len(country_cells)} countries ---")
    country_objs = []
    total_countries = len(country_cells)

    for ci, (cname, cell_list) in enumerate(country_cells.items()):
        if ci % BATCH_LOG == 0:
            print(f"  Countries: {ci}/{total_countries} ({ci * 100 / total_countries:.0f}%)")

        cell_verts = [cell['verts'] for _, cell in cell_list]
        surf = create_cell_mesh(f"country_{cname}", cell_verts, parent=parent, merge_verts=True)

        if ENABLE_BORDER:
            create_border_ribbons(
                surf, EXTRUDE_ABOVE, "border", parent,
                width=BORDER_WIDTH, height=BORDER_HEIGHT,
            )

        if ENABLE_EXTRUSION:
            extrude_mesh_radially_bi(surf, EXTRUDE_ABOVE, EXTRUDE_BELOW)

        country_objs.append(surf)

    print(f"  Created {len(country_objs)} country objects")

    # --- CITY GENERATION (Atlas Mode Only) ---
    if ENABLE_CITIES:
        print("\n--- Generating Cities ---")
        try:
            places = load_places_data(GEOJSON_PLACES)
            places = places[:CITY_MAX]
            print(f"  Loaded {len(places)} cities (top by population)")

            for i, p in enumerate(places):
                cell_idx, city_country = find_cell_for_city(p['lat'], p['lon'], cells, cell_countries, features)
                if cell_idx is None:
                    continue

                # Use cell centroid for positioning (centers city in hex cell)
                cell_centroid = cells[cell_idx]['centroid']
                cell_lat, cell_lon = xyz_to_latlon(cell_centroid)

                # Use country name in mesh name for proper indexing
                city_name = f"city_{city_country}_{p['name']}_{i}"
                obj = create_city_marker(city_name, cell_lat, cell_lon, parent=parent)
                city_objs.append(obj)

                # Create hexagonal border around city
                border_name = f"border_city_{city_country}_{p['name']}_{i}"
                border_obj = create_city_border(border_name, cell_lat, cell_lon, parent=parent)
                city_border_objs.append(border_obj)

                if (i + 1) % 50 == 0:
                    print(f"    Cities: {i + 1}/{len(places)}...")

            print(f"  Created {len(city_objs)} city markers with {len(city_border_objs)} borders")
        except Exception as e:
            print(f"  Warning: Failed to load cities: {e}")


# =============================================================================
# WEATHER MODE
# =============================================================================
elif MODE == "weather":
    print(f"\n--- Weather Mode: {len(country_cells)} countries, individual cells ---")
    cell_count = 0

    # Create individual cell meshes for country cells
    for cname, cell_list in country_cells.items():
        for local_idx, (global_idx, cell) in enumerate(cell_list):
            cell_name = f"cell_{cname}_{local_idx}"
            cell_obj = create_cell_mesh(cell_name, [cell['verts']], parent=parent, merge_verts=False)
            # Apply extrusion to each cell
            if ENABLE_EXTRUSION:
                extrude_mesh_radially_bi(cell_obj, EXTRUDE_ABOVE, EXTRUDE_BELOW)
            cell_count += 1

        if cell_count % BATCH_LOG == 0:
            print(f"  Cells: {cell_count}...")

    # Generate borders from grouped country meshes
    if ENABLE_BORDER:
        print("  Generating country borders...")
        for cname, cell_list in country_cells.items():
            cell_verts = [cell['verts'] for _, cell in cell_list]
            group_mesh = create_cell_mesh(
                f"_temp_group_{cname}", cell_verts, parent=parent, merge_verts=True,
            )
            create_border_ribbons(
                group_mesh, 0.0, "border", parent,
                width=BORDER_WIDTH, height=BORDER_HEIGHT,
            )
            bpy.data.objects.remove(group_mesh, do_unlink=True)

    print(f"  Created {cell_count} individual cell meshes")

    # Generate mapping JSON
    mapping = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "total_cells": len(cells),
        "assigned_cells": n_assigned,
        "ocean_cells": len(ocean_cells),
        "cells": [],
    }

    for idx, (cell, country) in enumerate(zip(cells, cell_countries)):
        raw_country = cell.get('admin') if country else None
        mapping["cells"].append({
            "idx": idx,
            "lat": round(cell.get('lat', 0), 4),
            "lon": round(cell.get('lon', 0), 4),
            "country": raw_country,
            "sides": cell['sides'],
        })

    with open(OUT_MAPPING, 'w', encoding='utf-8') as f:
        json.dump(mapping, f)
    print(f"  Wrote mapping: {OUT_MAPPING}")


# --- Export GLB --------------------------------------------------------------
print(f"\nExporting to: {OUT_GLB}")
bpy.ops.object.select_all(action='DESELECT')
select_hierarchy(parent)
bpy.context.view_layer.objects.active = parent

bpy.ops.export_scene.gltf(
    filepath=OUT_GLB,
    export_format='GLB',
    use_selection=True,
    export_apply=True,
)
print(f"Export complete: {OUT_GLB}")

# --- Write config JSON -------------------------------------------------------
try:
    cfg = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "mode": MODE,
        "ico_subdiv": ICO_SUBDIV,
        "hex_label": HEX_LABEL,
        "radius": RADIUS,
        "total_cells": len(cells),
        "pentagons": n_pent,
        "hexagons": n_hex,
        "assigned_cells": n_assigned,
        "ocean_cells": len(ocean_cells),
        "countries": len(country_cells),
        "extrusions": {"above": EXTRUDE_ABOVE, "below": EXTRUDE_BELOW},
        "border": {"width": BORDER_WIDTH, "height": BORDER_HEIGHT, "enabled": ENABLE_BORDER},
        "cities": {
            "enabled": ENABLE_CITIES,
            "count": len(city_objs),
            "borders": len(city_border_objs),
            "sides": CITY_MARKER_SIDES,
        },
    }
    with open(OUT_CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    print(f"Wrote config: {OUT_CFG}")
except Exception as e:
    print(f"Warning: failed to write config: {e}")

print("\nDone.")
