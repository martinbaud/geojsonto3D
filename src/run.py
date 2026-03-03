import bpy
import json
import math
import bmesh
import sys
import os
from mathutils import Vector
from datetime import datetime
from pathlib import Path

# --- CONFIGURATION (can be overridden by CLI arguments) ----------------------
# Project root directory (parent of src/)
PROJECT_ROOT = Path(bpy.path.abspath("//")).parent if "//" in bpy.path.abspath("//") else Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RES_DIR = PROJECT_ROOT / "res"

# Ensure res directory exists
RES_DIR.mkdir(exist_ok=True)

# Default values
GEOJSON_COUNTRIES = str(DATA_DIR / "ne_50m_admin_0_countries.geojson")
GEOJSON_PLACES = str(DATA_DIR / "ne_50m_populated_places.json")

RADIUS = 1.0
ICO_SUBDIV = 7
MAX_COUNTRIES = None  # None = process all countries

# Radial extrusion (countries & cities)
EXTRUDE_ABOVE_COUNTRY = 0.1
EXTRUDE_BELOW_COUNTRY = 0.0
EXTRUDE_ABOVE_CITY = EXTRUDE_ABOVE_COUNTRY
EXTRUDE_BELOW_CITY = EXTRUDE_BELOW_COUNTRY

# Borders (placed on top face)
BORDER_WIDTH = 0.0005
BORDER_HEIGHT = 0.0015
BORDER_ZFIGHT_EPS = 0.00005  # Legacy epsilon (kept for CLI compat)
EMBED_EPS = 0.0002  # radial inset so the ribbon sits flush/inside the top face

# Cities (if enabled)
SHRINK = 0.4
CITY_MAX = 200  # limit number of generated cities to keep geometry reasonable
CITY_MARKER_RADIUS = 0.007  # approximate tangent radius of city marker base
CITY_MARKER_SIDES = 3  # triangular prism per requirement
CITY_CLOSING_RADIUS_SCALE = 1.1  # closing slightly larger than city marker
CITY_CLOSING_GAP = 0.0005       # small gap above city top to avoid z-fight

# Feature toggles (harmonized)
# ENABLE_BORDER: generate border ribbons for countries
# ENABLE_CLOSING: generate triangular caps above cities (not country top faces)
# ENABLE_CITIES: generate triangular city prisms
ENABLE_BORDER = True
ENABLE_CLOSING = False
ENABLE_CITIES = False

PARENT_NAME = "Atlas"

# --- Parse CLI arguments (if provided) ---------------------------------------
if "--" in sys.argv:
    args_start = sys.argv.index("--") + 1
    args = sys.argv[args_start:]

    i = 0
    while i < len(args):
        arg = args[i]

        if arg == "--ico-subdiv" and i + 1 < len(args):
            ICO_SUBDIV = int(args[i + 1])
            i += 2
        elif arg == "--extrude-above" and i + 1 < len(args):
            EXTRUDE_ABOVE_COUNTRY = float(args[i + 1])
            EXTRUDE_ABOVE_CITY = EXTRUDE_ABOVE_COUNTRY
            i += 2
        elif arg == "--extrude-below" and i + 1 < len(args):
            EXTRUDE_BELOW_COUNTRY = float(args[i + 1])
            EXTRUDE_BELOW_CITY = EXTRUDE_BELOW_COUNTRY
            i += 2
        elif arg == "--border-width" and i + 1 < len(args):
            BORDER_WIDTH = float(args[i + 1])
            i += 2
        elif arg == "--border-height" and i + 1 < len(args):
            BORDER_HEIGHT = float(args[i + 1])
            i += 2
        elif arg in ("--enable-border", "--enable-borders"):
            # Backward compatibility for --enable-borders
            ENABLE_BORDER = True
            i += 1
        elif arg in ("--disable-border", "--disable-borders"):
            ENABLE_BORDER = False
            i += 1
        elif arg == "--enable-closing":
            ENABLE_CLOSING = True
            i += 1
        elif arg == "--disable-closing":
            ENABLE_CLOSING = False
            i += 1
        elif arg == "--enable-cities":
            ENABLE_CITIES = True
            i += 1
        elif arg == "--disable-cities":
            ENABLE_CITIES = False
            i += 1
        else:
            i += 1

# Output file paths in res/ directory
OUT_GLB = str(RES_DIR / f"atlas_ico_subdiv_{ICO_SUBDIV}.glb")
OUT_CFG = str(RES_DIR / f"atlas_ico_subdiv_{ICO_SUBDIV}.config.json")


# --- UTILITY FUNCTIONS -------------------------------------------------------
def xyz_to_latlon(v):
    """Convert 3D Cartesian coordinates to latitude/longitude in degrees."""
    r = v.length
    return math.degrees(math.asin(v.z/r)), math.degrees(math.atan2(v.y, v.x))


def point_in_poly(lon, lat, poly):
    """Ray-casting algorithm to test if a point is inside a polygon."""
    inside = False
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i+1) % len(poly)]
        if ((y1 > lat) != (y2 > lat)) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def select_hierarchy(obj):
    """Recursively select an object and all its children."""
    obj.select_set(True)
    for c in obj.children:
        select_hierarchy(c)


def new_mesh_object(name, verts, faces, parent=None, smooth=True):
    """Create a new mesh object from vertices and faces."""
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


def extrude_mesh_radially_bi(obj, depth_above, depth_below):
    """Bidirectional radial extrusion aligned to base sphere (RADIUS)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()

    # Always normalize base position to the base sphere
    for v in bm.verts:
        v.co = v.co.normalized() * RADIUS

    # Extrude outward
    if depth_above > 0:
        res_up = bmesh.ops.extrude_face_region(bm, geom=bm.faces)
        verts_up = [v for v in res_up["geom"] if isinstance(v, bmesh.types.BMVert)]
        for v in verts_up:
            v.co = v.co.normalized() * (RADIUS + depth_above)

    # Extrude inward
    if depth_below > 0:
        res_down = bmesh.ops.extrude_face_region(bm, geom=bm.faces)
        verts_down = [v for v in res_down["geom"] if isinstance(v, bmesh.types.BMVert)]
        for v in verts_down:
            v.co = v.co.normalized() * (RADIUS - depth_below)

    # Always apply the changes
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()


def create_border_ribbons_from_planar_source_on_top(source_obj, above, name_prefix, parent,
                                                    width=BORDER_WIDTH, height=BORDER_HEIGHT,
                                                    zfight_eps=BORDER_ZFIGHT_EPS):
    """
    Generate 3D border ribbons on top surface only.

    Process:
    - Read boundary edges from source mesh (pre-extrusion surface)
    - Project edges radially to 'above' height (top face)
    - Build ribbon geometry (ring + cap) with radial extrusion for height
    - No border on bottom since we only use original surface
    """
    bm = bmesh.new()
    bm.from_mesh(source_obj.data)
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    # Find boundary edges (country contour)
    boundary_edges = [e for e in bm.edges if len(e.link_faces) == 1]

    bm_out = bmesh.new()

    for e in boundary_edges:
        v1o = e.verts[0].co.copy()
        v2o = e.verts[1].co.copy()

        # Project vertices to top height, embedded slightly to avoid a floating look
        v1_top = v1o.normalized() * (RADIUS + above - EMBED_EPS)
        v2_top = v2o.normalized() * (RADIUS + above - EMBED_EPS)

        # Edge direction on top surface
        edge_dir = (v2_top - v1_top).normalized()

        # Perpendicular tangent in the local tangent plane
        perp1 = v1_top.normalized().cross(edge_dir).normalized()
        perp2 = v2_top.normalized().cross(edge_dir).normalized()

        # Ring quad (annular base)
        v1a = v1_top + perp1 * (width / 2)
        v1b = v1_top - perp1 * (width / 2)
        v2a = v2_top + perp2 * (width / 2)
        v2b = v2_top - perp2 * (width / 2)

        ring = [v1a, v2a, v2b, v1b]

        # Top cap of ribbon: radial extrusion of ring
        top = [p + p.normalized() * height for p in ring]

        verts_all = ring + top
        verts_new = [bm_out.verts.new(co) for co in verts_all]

        # Faces: 4 walls + top cap (bottom left open)
        faces_idx = [
            (0, 1, 5, 4),
            (1, 2, 6, 5),
            (2, 3, 7, 6),
            (3, 0, 4, 7),
            (4, 5, 6, 7),  # top cap
        ]
        for idx in faces_idx:
            try:
                bm_out.faces.new([verts_new[i] for i in idx])
            except ValueError:
                pass

    bm_out.normal_update()
    # Standardize naming: strip known prefixes from source (e.g., 'country_', 'city_')
    src_name = source_obj.name
    for pfx in ("country_", "city_"):
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


def create_closing_rings_from_planar_source_on_top(source_obj, above, name_prefix, parent,
                                                   width=BORDER_WIDTH):
    """
    Generate flat ring quads along the country's top-edge contours (no height extrusion).
    This matches the country "bordure" at the top face for optimized naming.
    Output name format: f"{name_prefix}_{countryName}_{segmentIndex}" similar to borders.
    """
    bm = bmesh.new()
    bm.from_mesh(source_obj.data)
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    boundary_edges = [e for e in bm.edges if len(e.link_faces) == 1]
    bm_out = bmesh.new()

    for e in boundary_edges:
        v1o = e.verts[0].co.copy()
        v2o = e.verts[1].co.copy()

        # Project vertices to top height, embedded slightly
        v1_top = v1o.normalized() * (RADIUS + above - EMBED_EPS)
        v2_top = v2o.normalized() * (RADIUS + above - EMBED_EPS)

        edge_dir = (v2_top - v1_top).normalized()
        # Perpendicular tangent vectors in local tangent plane
        perp1 = v1_top.normalized().cross(edge_dir).normalized()
        perp2 = v2_top.normalized().cross(edge_dir).normalized()

        v1a = v1_top + perp1 * (width / 2)
        v1b = v1_top - perp1 * (width / 2)
        v2a = v2_top + perp2 * (width / 2)
        v2b = v2_top - perp2 * (width / 2)

        # Create a single quad (two triangles) per edge segment
        p0 = bm_out.verts.new(v1a)
        p1 = bm_out.verts.new(v2a)
        p2 = bm_out.verts.new(v2b)
        p3 = bm_out.verts.new(v1b)
        try:
            bm_out.faces.new([p0, p1, p2, p3])
        except ValueError:
            # Face may already exist in rare degeneracies; skip
            pass

    bm_out.normal_update()

    src_name = source_obj.name
    for pfx in ("country_", "city_"):
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

def create_city_marker(name, lat_deg, lon_deg, above=EXTRUDE_ABOVE_CITY,
                       radius=CITY_MARKER_RADIUS, sides=CITY_MARKER_SIDES,
                       parent=None):
    """
    Create a small low-poly city marker oriented to the globe surface using a hex prism.
    Naming: f"city_{name}_{index}" should be provided by caller with unique name.
    """
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    # Normal vector on sphere
    n = Vector((math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)))
    base_center = n * (RADIUS + above - EMBED_EPS)

    # Build tangent basis
    up = Vector((0.0, 0.0, 1.0))
    t1 = n.cross(up)
    if t1.length < 1e-6:
        up = Vector((0.0, 1.0, 0.0))
        t1 = n.cross(up)
    t1.normalize()
    t2 = n.cross(t1).normalized()

    # Base ring verts
    verts_base = []
    verts_top = []
    for i in range(sides):
        theta = 2 * math.pi * (i / sides)
        offset = t1 * math.cos(theta) * radius + t2 * math.sin(theta) * radius
        vb = base_center + offset
        vt = base_center + offset + n * above
        verts_base.append(vb)
        verts_top.append(vt)

    # Build faces
    verts_all = verts_base + verts_top
    faces = []
    # walls
    for i in range(sides):
        a = i
        b = (i + 1) % sides
        c = sides + (i + 1) % sides
        d = sides + i
        faces.append([a, b, c, d])
    # top cap
    faces.append([sides + i for i in range(sides)])

    obj = new_mesh_object(name, verts_all, faces, parent=parent, smooth=True)
    return obj

def create_city_marker_at_direction(name, dir_normal: Vector, above=EXTRUDE_ABOVE_CITY,
                                    radius=CITY_MARKER_RADIUS, sides=CITY_MARKER_SIDES,
                                    parent=None):
    """
    Create a city marker oriented by a given surface normal direction.
    Returns (obj, verts_top) where verts_top are the 3 top vertices positions.
    """
    n = dir_normal.normalized()
    base_center = n * (RADIUS + above - EMBED_EPS)

    up = Vector((0.0, 0.0, 1.0))
    t1 = n.cross(up)
    if t1.length < 1e-6:
        up = Vector((0.0, 1.0, 0.0))
        t1 = n.cross(up)
    t1.normalize()
    t2 = n.cross(t1).normalized()

    verts_base = []
    verts_top = []
    for i in range(sides):
        theta = 2 * math.pi * (i / sides)
        offset = t1 * math.cos(theta) * radius + t2 * math.sin(theta) * radius
        vb = base_center + offset
        vt = base_center + offset + n * above
        verts_base.append(vb)
        verts_top.append(vt)

    verts_all = verts_base + verts_top
    faces = []
    for i in range(sides):
        a = i
        b = (i + 1) % sides
        c = sides + (i + 1) % sides
        d = sides + i
        faces.append([a, b, c, d])
    faces.append([sides + i for i in range(sides)])

    obj = new_mesh_object(name, verts_all, faces, parent=parent, smooth=True)
    return obj, verts_top

def create_city_marker_from_face(name, face_index: int, shrink=SHRINK, above=EXTRUDE_ABOVE_CITY,
                                 parent=None):
    """
    Create a triangular city marker aligned to the given icosphere face.
    Uses face vertex directions and shrinks them toward the centroid for robust in-face placement.
    Returns (obj, verts_top).
    """
    verts_dir = FACE_VERTS[face_index] if 0 <= face_index < len(FACE_VERTS) else None
    n = FACE_CENTROIDS[face_index] if 0 <= face_index < len(FACE_CENTROIDS) else None
    if not verts_dir or not n or len(verts_dir) < 3:
        return None, []

    n = n.normalized()
    cdir = n

    verts_base = []
    verts_top = []
    for vdir in verts_dir[:3]:
        shrunk = vdir.lerp(cdir, shrink).normalized()
        # Base sits slightly embedded into the country top to avoid z-fighting
        vb = shrunk * (RADIUS + above - EMBED_EPS)
        # Top is offset from base by the same height along the local normal (visible prism height)
        vt = vb + cdir * above
        verts_base.append(vb)
        verts_top.append(vt)

    # Build walls + top cap
    verts_all = verts_base + verts_top
    faces = []
    for i in range(3):
        a = i
        b = (i + 1) % 3
        c = 3 + (i + 1) % 3
        d = 3 + i
        faces.append([a, b, c, d])
    faces.append([3 + i for i in range(3)])

    obj = new_mesh_object(name, verts_all, faces, parent=parent, smooth=True)
    return obj, verts_top

def create_city_closing_ribbon_from_top(name_prefix, verts_top, height=BORDER_HEIGHT, width=BORDER_WIDTH,
                                        parent=None):
    """
    Create a thin ribbon along the edges of a triangular city top face, placed above that face.
    """
    if len(verts_top) < 3:
        return None

    # Normal from the three top vertices
    n = (verts_top[0] + verts_top[1] + verts_top[2]) / 3.0
    n = n.normalized()

    bm_out = bmesh.new()
    edges = [(0,1), (1,2), (2,0)]
    for (i0, i1) in edges:
        v0 = verts_top[i0] + n * CITY_CLOSING_GAP
        v1 = verts_top[i1] + n * CITY_CLOSING_GAP
        edge_dir = (v1 - v0).normalized()
        perp = n.cross(edge_dir).normalized()

        a0 = v0 + perp * (width/2)
        b0 = v0 - perp * (width/2)
        a1 = v1 + perp * (width/2)
        b1 = v1 - perp * (width/2)

        ta0 = a0 + a0.normalized() * height
        tb0 = b0 + b0.normalized() * height
        ta1 = a1 + a1.normalized() * height
        tb1 = b1 + b1.normalized() * height

        vs = [a0, a1, b1, b0, ta0, ta1, tb1, tb0]
        verts_new = [bm_out.verts.new(co) for co in vs]

        faces_idx = [
            (0,1,5,4),
            (1,2,6,5),
            (2,3,7,6),
            (3,0,4,7),
            (4,5,6,7)
        ]
        for idx in faces_idx:
            try:
                bm_out.faces.new([verts_new[i] for i in idx])
            except ValueError:
                pass

    bm_out.normal_update()
    me = bpy.data.meshes.new(f"{name_prefix}")
    bm_out.to_mesh(me)
    bm_out.free()
    ob = bpy.data.objects.new(f"{name_prefix}", me)
    bpy.context.collection.objects.link(ob)
    if parent:
        ob.parent = parent
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.shade_smooth()
    return ob

def create_city_closing_cap(name, lat_deg, lon_deg,
                            city_above=EXTRUDE_ABOVE_CITY,
                            height=BORDER_HEIGHT,
                            radius=CITY_MARKER_RADIUS * CITY_CLOSING_RADIUS_SCALE,
                            sides=3,
                            parent=None):
    """
    Create a thin triangular cap (closing) above a city marker.
    - Base positioned just above the city's top (city_above + CITY_CLOSING_GAP)
    - Height matches border height for visual consistency
    - Slightly larger radius than the city marker
    """
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    n = Vector((math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)))
    base_center = n * (RADIUS + city_above + CITY_CLOSING_GAP - EMBED_EPS)

    up = Vector((0.0, 0.0, 1.0))
    t1 = n.cross(up)
    if t1.length < 1e-6:
        up = Vector((0.0, 1.0, 0.0))
        t1 = n.cross(up)
    t1.normalize()
    t2 = n.cross(t1).normalized()

    verts_base = []
    verts_top = []
    for i in range(sides):
        theta = 2 * math.pi * (i / sides)
        offset = t1 * math.cos(theta) * radius + t2 * math.sin(theta) * radius
        vb = base_center + offset
        vt = base_center + offset + n * height
        verts_base.append(vb)
        verts_top.append(vt)

    verts_all = verts_base + verts_top
    faces = []
    for i in range(sides):
        a = i
        b = (i + 1) % sides
        c = sides + (i + 1) % sides
        d = sides + i
        faces.append([a, b, c, d])
    faces.append([sides + i for i in range(sides)])

    obj = new_mesh_object(name, verts_all, faces, parent=parent, smooth=True)
    return obj


# --- LOAD GEOJSON DATA -------------------------------------------------------
with open(GEOJSON_COUNTRIES, encoding='utf-8') as f:
    gj = json.load(f)

features = []
for feat in gj.get("features", [])[:MAX_COUNTRIES]:
    name = feat["properties"]["ADMIN"]
    geom = feat.get("geometry", {})
    if not geom:
        continue
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for idx, poly in enumerate(polys):
        rings = []
        for ring in poly:
            pts = [(lon, lat) for lon, lat in ring if isinstance(lon, (int, float))]
            if len(pts) >= 3:
                rings.append(pts)
        if not rings:
            continue
        outer = rings[0]
        bbox = (min(x for x, y in outer), max(x for x, y in outer),
                min(y for x, y in outer), max(y for x, y in outer))
        features.append({"name": f"{name}_{idx}", "rings": rings, "bbox": bbox})

# --- SCENE SETUP -------------------------------------------------------------
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
parent = bpy.data.objects.new(PARENT_NAME, None)
bpy.context.collection.objects.link(parent)

bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=ICO_SUBDIV, radius=RADIUS - 1e-4)
core = bpy.context.object
core.name = "GlobeCore"
core.parent = parent
bpy.ops.object.shade_smooth()
mesh_sphere = core.data

# Assign faces to countries and cache face centroids + vertex directions
faces_by_country = {feat["name"]: [] for feat in features}
used_faces = set()
FACE_CENTROIDS = [None] * len(mesh_sphere.polygons)
FACE_VERTS = [None] * len(mesh_sphere.polygons)
for poly in mesh_sphere.polygons:
    # Cache centroid direction
    cent = sum((mesh_sphere.vertices[v].co for v in poly.vertices), Vector()) / len(poly.vertices)
    FACE_CENTROIDS[poly.index] = cent.normalized()
    # Cache vertex directions (icosphere faces are triangles)
    FACE_VERTS[poly.index] = [mesh_sphere.vertices[vid].co.copy().normalized() for vid in poly.vertices]

    # Assign face to a country using centroid point-in-polygon
    lat, lon = xyz_to_latlon(cent)
    for feat in features:
        minx, maxx, miny, maxy = feat["bbox"]
        if not (minx <= lon <= maxx and miny <= lat <= maxy):
            continue
        if point_in_poly(lon, lat, feat["rings"][0]):
            faces_by_country[feat["name"]].append(poly.index)
            used_faces.add(poly.index)
            break


def create_surface(name, fids):
    """Create a mesh surface from face indices."""
    cmap, verts, faces = {}, [], []
    for fid in fids:
        poly = mesh_sphere.polygons[fid]
        idxs = []
        for vid in poly.vertices:
            co = mesh_sphere.vertices[vid].co.copy()
            key = (round(co.x, 5), round(co.y, 5), round(co.z, 5))
            if key not in cmap:
                cmap[key] = len(verts)
                verts.append(co)
            idxs.append(cmap[key])
        faces.append(idxs)
    return new_mesh_object(name, verts, faces, parent=parent, smooth=True)


# Ocean (GlobeFill) = all faces not assigned to countries
all_faces = set(range(len(mesh_sphere.polygons)))
ocean = create_surface("GlobeFill", list(all_faces - used_faces))
bpy.data.objects.remove(core, do_unlink=True)

# --- COUNTRIES ---------------------------------------------------------------
country_objs = []
for name, fids in faces_by_country.items():
    if not fids:
        continue

    # 1) Create original surface (source for top borders)
    # Countries follow the 'country_{name}' convention
    surf = create_surface(f"country_{name}", fids)

    # 2) Generate borders on top surface (by projecting original surface to +above)
    if ENABLE_BORDER:
        create_border_ribbons_from_planar_source_on_top(
            surf, EXTRUDE_ABOVE_COUNTRY, "border", parent,
            width=BORDER_WIDTH, height=BORDER_HEIGHT, zfight_eps=BORDER_ZFIGHT_EPS
        )

    # 2b) Closing handled per-city; no country-based closing

    # 3) Extrude country (up + down) without affecting borders
    extrude_mesh_radially_bi(surf, EXTRUDE_ABOVE_COUNTRY, EXTRUDE_BELOW_COUNTRY)

    country_objs.append(surf)

# --- CITIES (OPTIONAL) -------------------------------------------------------
city_objs = []
if ENABLE_CITIES:
    try:
        with open(GEOJSON_PLACES, encoding='utf-8') as pf:
            pj = json.load(pf)

        # Extract candidate places
        places = []
        feats = pj.get('features') or pj  # support raw array files
        for idx, feat in enumerate(feats):
            props = feat.get('properties', {}) if isinstance(feat, dict) else {}
            geom = feat.get('geometry', {}) if isinstance(feat, dict) else None
            if geom and geom.get('type') == 'Point':
                lon, lat = geom.get('coordinates', [None, None])
            else:
                # Try common flat schema
                lon = props.get('longitude') or props.get('LON') or props.get('LONDD') or props.get('LONGITUDE')
                lat = props.get('latitude') or props.get('LAT') or props.get('LATDD') or props.get('LATITUDE')
            if lon is None or lat is None:
                continue
            name = props.get('NAME') or props.get('NAMEASCII') or props.get('name') or props.get('nameascii') or f"Place_{idx}"
            pop = props.get('POP_MAX') or props.get('pop_max') or props.get('POP') or 0
            try:
                pop = float(pop)
            except Exception:
                pop = 0
            places.append({'name': name, 'lat': float(lat), 'lon': float(lon), 'pop': pop})

        # Keep top-N by population if available
        places.sort(key=lambda p: p.get('pop', 0), reverse=True)
        places = places[:CITY_MAX]

        # Helper to find containing feature and best face index by alignment
        def find_city_face(lat_deg, lon_deg):
            # Direction from lat/lon
            lat_r = math.radians(lat_deg)
            lon_r = math.radians(lon_deg)
            n_dir = Vector((math.cos(lat_r) * math.cos(lon_r), math.cos(lat_r) * math.sin(lon_r), math.sin(lat_r)))

            # Find containing feature
            containing_feat_name = None
            for feat in features:
                minx, maxx, miny, maxy = feat["bbox"]
                if not (minx <= lon_deg <= maxx and miny <= lat_deg <= maxy):
                    continue
                if point_in_poly(lon_deg, lat_deg, feat["rings"][0]):
                    containing_feat_name = feat["name"]
                    break

            # Collect candidate faces
            if containing_feat_name and faces_by_country.get(containing_feat_name):
                candidate_faces = faces_by_country[containing_feat_name]
            else:
                # Fallback to any used (country) faces only to avoid ocean placement
                candidate_faces = used_faces

            # Pick face whose centroid aligns best with city direction
            best_face = None
            best_dot = -1.0
            for fi in candidate_faces:
                c = FACE_CENTROIDS[fi]
                if c is None:
                    continue
                d = c.dot(n_dir)
                if d > best_dot:
                    best_dot = d
                    best_face = fi
            return best_face

        for i, p in enumerate(places):
            face_index = find_city_face(p['lat'], p['lon'])
            city_name = f"city_{p['name']}_{i}"
            if face_index is None:
                # Fallback to directional placement using computed normal
                lat_r = math.radians(p['lat'])
                lon_r = math.radians(p['lon'])
                n_dir = Vector((math.cos(lat_r) * math.cos(lon_r), math.cos(lat_r) * math.sin(lon_r), math.sin(lat_r)))
                obj, verts_top = create_city_marker_at_direction(city_name, n_dir, parent=parent)
            else:
                obj, verts_top = create_city_marker_from_face(city_name, face_index, parent=parent)
            city_objs.append(obj)
            if ENABLE_CLOSING:
                closing_name = f"closing_{p['name']}_{i}"
                create_city_closing_ribbon_from_top(
                    closing_name,
                    verts_top,
                    height=BORDER_HEIGHT,
                    width=BORDER_WIDTH,
                    parent=parent,
                )
    except Exception as e:
        print(f"Warning: failed to generate cities: {e}")

# --- EXPORT ------------------------------------------------------------------
bpy.ops.object.select_all(action='DESELECT')
select_hierarchy(parent)
bpy.context.view_layer.objects.active = parent

print(f"Exporting to: {OUT_GLB}")

bpy.ops.export_scene.gltf(
    filepath=OUT_GLB,
    export_format='GLB',
    use_selection=True,
    export_apply=True
)

print(f"Export complete: {OUT_GLB}")

# --- WRITE CONFIG ------------------------------------------------------------
try:
    cfg = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "ico_subdiv": ICO_SUBDIV,
        "radius": RADIUS,
        "extrusions": {
            "country": {"above": EXTRUDE_ABOVE_COUNTRY, "below": EXTRUDE_BELOW_COUNTRY},
            "city": {"above": EXTRUDE_ABOVE_CITY, "below": EXTRUDE_BELOW_CITY},
        },
        "border": {
            "width": BORDER_WIDTH,
            "height": BORDER_HEIGHT,
            "embed_eps": EMBED_EPS,
            "zfight_eps": BORDER_ZFIGHT_EPS,
        },
        "features": {
            "border": ENABLE_BORDER,
            "closing": ENABLE_CLOSING,
            "cities": ENABLE_CITIES,
        },
        "counts": {
            "countries": len(country_objs),
            "cities": len(city_objs),
        },
    }
    with open(OUT_CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    print(f"Wrote config: {OUT_CFG}")
except Exception as e:
    print(f"Warning: failed to write config: {e}")
