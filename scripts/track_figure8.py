import bpy
import math
import os
import sys
import random
from mathutils import Vector

# =============================================================================
#  OUTPUT PATH — pass after "--"
#  blender -b --python track_figure8.py -- /path/to/output.glb
# =============================================================================
argv = sys.argv
out_path = (
    argv[argv.index("--") + 1]
    if "--" in argv
    else "/Volumes/external/exports/racetrack_figure8.glb"
)
os.makedirs(os.path.dirname(out_path), exist_ok=True)

# =============================================================================
#  CONFIGURATION
# =============================================================================

LAYOUT_SCALE = 8.0                  # multiplier on control-point coords
COLLECTION_NAME = "RaceTrackFigure8"

# road
ROAD_WIDTH = 14.0

# walls
WALL_HEIGHT = 2.6
WALL_THICKNESS = 0.6

# bridge / overpass
BRIDGE_HEIGHT = 10.0                # peak elevation at crossing
BRIDGE_CENTER_FRAC = 0.475         # fraction of track where bridge peaks
BRIDGE_RAMP_HALF = 0.10            # ramp extends +/- this fraction
BRIDGE_SUPPORT_STEP = 25           # place support every N samples
BRIDGE_SUPPORT_W = 0.8
BRIDGE_DECK_THICK = 0.4
BRIDGE_MIN_Z = 3.0                 # only add supports where Z > this

# terrain / ground
GROUND_Z = -0.08
TERRAIN_MARGIN = 180.0
TERRAIN_GRID_X = 180
TERRAIN_GRID_Y = 180
TERRAIN_SHOULDER_PAD = 10.0
TERRAIN_BLEND = 80.0
TERRAIN_BERM_HEIGHT = 2.8
TERRAIN_BERM_OFFSET = 24.0
TERRAIN_BERM_WIDTH = 18.0

# curve sampling
CURVE_SAMPLES = 720
SAMPLES_PER_SEG = 36

# start / checkpoints
START_FRAC = 0.125
CP_FRACS = [0.25, 0.45, 0.65, 0.85]
CP_HEIGHT = 5.0
CP_THICK = 0.7
CP_EXTRA_W = 2.0

# curbs
CURB_W = 1.2
CURB_H = 0.18
CURB_STEP = 2
CURB_Z_OFF = 0.06

# center stripes
STRIPE_W = 0.30
STRIPE_H = 0.03
STRIPE_L = 2.0
STRIPE_STEP = 4

# forest
TREE_SEED = 42
TREE_CLEAR = 7.0
INNER_TREES = 200
INNER_JITTER = 14.0
OUTER_TREES = 500
OUTER_MIN = 22.0
OUTER_MAX = 65.0
BUSHES = 150
BUSH_CLEAR = 5.0
BUSH_JITTER = 20.0

# crossing exclusion — no trees within this radius of (0,0)
CROSSING_EXCL = 30.0

# ---------- figure-8 control points ----------
# Right lobe (clockwise) → bridge crossing NW → left lobe (clockwise) → ground crossing NE
_Z = 0.0
_BASE_CP = [
    #  right lobe
    Vector(( 4,   4,  _Z)),   #  0  depart ground crossing NE
    Vector((15,  18,  _Z)),   #  1  accel straight
    Vector((30,  28,  _Z)),   #  2  START LINE zone
    Vector((48,  30,  _Z)),   #  3  sweeping right entry
    Vector((58,  18,  _Z)),   #  4  fast right kink
    Vector((60,   0,  _Z)),   #  5  back straight
    Vector((55, -18,  _Z)),   #  6  braking zone
    Vector((38, -32,  _Z)),   #  7  tight hairpin
    Vector((20, -28,  _Z)),   #  8  hairpin exit
    Vector(( 4,  -4,  _Z)),   #  9  approach bridge crossing SW
    #  bridge crossing + left lobe
    Vector((-4,   4,  _Z)),   # 10  depart crossing NW  (BRIDGE PEAK)
    Vector((-15, 18,  _Z)),   # 11  bridge descent
    Vector((-30, 28,  _Z)),   # 12  left lobe entry
    Vector((-48, 25,  _Z)),   # 13  sweeping left
    Vector((-58, 10,  _Z)),   # 14  chicane entry
    Vector((-55, -8,  _Z)),   # 15  chicane mid
    Vector((-48,-25,  _Z)),   # 16  chicane exit
    Vector((-32,-32,  _Z)),   # 17  left lobe south
    Vector((-15,-20,  _Z)),   # 18  heading back NE
    Vector((-4,  -4,  _Z)),   # 19  approach ground crossing SE
]

CONTROL_POINTS = [
    Vector((p.x * LAYOUT_SCALE, p.y * LAYOUT_SCALE, p.z))
    for p in _BASE_CP
]

# =============================================================================
#  SCENE HELPERS
# =============================================================================

def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for block in list(bpy.data.meshes):
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for block in list(bpy.data.materials):
        if block.users == 0:
            bpy.data.materials.remove(block)

def make_material(name, color, roughness=0.8, metallic=0.0, specular=0.5):
    existing = bpy.data.materials.get(name)
    if existing:
        bpy.data.materials.remove(existing, do_unlink=True)
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["IOR"].default_value = 1.45
    return mat

def make_collection(name):
    existing = bpy.data.collections.get(name)
    if existing is not None:
        return existing
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col

def relink_object(obj, collection):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    collection.objects.link(obj)

def add_mesh_object(name, verts, faces, collection, material=None):
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if material:
        obj.data.materials.append(material)
    return obj

# =============================================================================
#  CURVE MATH
# =============================================================================

def closed_catmull_rom(p0, p1, p2, p3, t):
    t2, t3 = t * t, t * t * t
    return 0.5 * (
        (2.0 * p1)
        + (-p0 + p2) * t
        + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
        + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
    )

def sample_closed_catmull_rom(control_points, samples_per_segment=24):
    pts = []
    n = len(control_points)
    for i in range(n):
        p0 = control_points[(i - 1) % n]
        p1 = control_points[i]
        p2 = control_points[(i + 1) % n]
        p3 = control_points[(i + 2) % n]
        for s in range(samples_per_segment):
            pts.append(closed_catmull_rom(p0, p1, p2, p3, s / samples_per_segment))
    return pts

def resample_closed_polyline(points, target_count):
    n = len(points)
    if n < 2:
        return points[:]
    seg_lengths = []
    total = 0.0
    for i in range(n):
        d = (points[(i + 1) % n] - points[i]).length
        seg_lengths.append(d)
        total += d
    if total == 0:
        return points[:]
    out = []
    step = total / target_count
    seg_index = 0
    seg_start_dist = 0.0
    for k in range(target_count):
        target_dist = k * step
        while True:
            sl = seg_lengths[seg_index]
            if seg_start_dist + sl >= target_dist or sl == 0:
                break
            seg_start_dist += sl
            seg_index = (seg_index + 1) % n
        a = points[seg_index]
        b = points[(seg_index + 1) % n]
        sl = seg_lengths[seg_index]
        if sl == 0:
            out.append(a.copy())
        else:
            out.append(a.lerp(b, (target_dist - seg_start_dist) / sl))
    return out

# =============================================================================
#  ELEVATION  (bridge ramp — cosine bell centered at BRIDGE_CENTER_FRAC)
# =============================================================================

def compute_elevation(frac):
    dist = abs(frac - BRIDGE_CENTER_FRAC)
    if dist > 0.5:
        dist = 1.0 - dist
    if dist >= BRIDGE_RAMP_HALF:
        return 0.0
    return BRIDGE_HEIGHT * 0.5 * (1.0 + math.cos(math.pi * dist / BRIDGE_RAMP_HALF))

# =============================================================================
#  FRAME COMPUTATION (tangents + left normals, all in XY plane)
# =============================================================================

def compute_frames(centerline):
    tangents, left_normals = [], []
    n = len(centerline)
    for i in range(n):
        t = centerline[(i + 1) % n] - centerline[(i - 1) % n]
        t.z = 0.0
        if t.length < 1e-6:
            t = Vector((1, 0, 0))
        t.normalize()
        lft = Vector((-t.y, t.x, 0.0))
        lft.normalize()
        tangents.append(t)
        left_normals.append(lft)
    return tangents, left_normals

def signed_area_2d(a, b, p):
    return (b.x - a.x) * (p.y - a.y) - (p.x - a.x) * (b.y - a.y)

def winding_number_2d(point, polygon):
    winding = 0
    n = len(polygon)
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        if a.y <= point.y:
            if b.y > point.y and signed_area_2d(a, b, point) > 0:
                winding += 1
        else:
            if b.y <= point.y and signed_area_2d(a, b, point) < 0:
                winding -= 1
    return winding

def min_distance_to_polyline(point, polyline):
    best = float("inf")
    n = len(polyline)
    for i in range(n):
        a = polyline[i]
        b = polyline[(i + 1) % n]
        ab = b - a
        denom = ab.length_squared
        if denom == 0:
            dist = (point - a).length
        else:
            t = max(0.0, min(1.0, (point - a).dot(ab) / denom))
            proj = a + ab * t
            dist = (point - proj).length
        if dist < best:
            best = dist
    return best

def smoothstep(edge0, edge1, value):
    if edge0 == edge1:
        return 0.0 if value < edge0 else 1.0
    t = max(0.0, min(1.0, (value - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)

def terrain_macro_height(point, track_bounds):
    min_x, max_x, min_y, max_y = track_bounds
    span_x = max_x - min_x
    span_y = max_y - min_y
    max_span = max(span_x, span_y)
    x, y = point.x, point.y

    waves = (
        1.6 * math.sin(x * 0.0075)
        + 1.3 * math.cos(y * 0.0060)
        + 0.9 * math.sin((x + y) * 0.0042)
    )

    hills = 0.0
    hill_specs = [
        (min_x - 0.18 * span_x, max_y + 0.15 * span_y, 11.0, max_span * 0.32),
        (max_x + 0.12 * span_x, max_y + 0.08 * span_y, 8.0, max_span * 0.28),
        (max_x + 0.10 * span_x, min_y - 0.18 * span_y, 10.0, max_span * 0.30),
        (min_x - 0.20 * span_x, min_y - 0.10 * span_y, 9.0, max_span * 0.34),
        ((min_x + max_x) * 0.5, min_y - 0.26 * span_y, 5.0, max_span * 0.36),
    ]
    for hx, hy, height, radius in hill_specs:
        dist_sq = (x - hx) ** 2 + (y - hy) ** 2
        hills += height * math.exp(-dist_sq / (radius * radius))

    basin = -2.2 * math.exp(
        -(x * x + (y * 0.85) ** 2) / ((max_span * 0.24) ** 2)
    )
    return waves + hills + basin

def terrain_height_at(point, flat_centerline, track_bounds):
    road_dist = min_distance_to_polyline(point, flat_centerline)
    terrain_clearance = ROAD_WIDTH * 0.5 + CURB_W + WALL_THICKNESS + TERRAIN_SHOULDER_PAD
    corridor = smoothstep(
        terrain_clearance,
        terrain_clearance + TERRAIN_BLEND,
        road_dist
    )
    berm = TERRAIN_BERM_HEIGHT * math.exp(
        -((road_dist - (terrain_clearance + TERRAIN_BERM_OFFSET)) / TERRAIN_BERM_WIDTH) ** 2
    )
    shoulder = -0.25 * math.exp(
        -((road_dist - terrain_clearance * 0.85) / 8.0) ** 2
    )
    macro = terrain_macro_height(point, track_bounds)
    return GROUND_Z + shoulder + berm * corridor + macro * corridor

# =============================================================================
#  GEOMETRY BUILDERS
# =============================================================================

def build_ribbon(a_pts, b_pts, name, collection, material):
    n = len(a_pts)
    verts = [p.copy() for p in a_pts] + [p.copy() for p in b_pts]
    faces = [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
    return add_mesh_object(name, verts, faces, collection, material)

def build_road(left_pts, right_pts, collection, material):
    return build_ribbon(left_pts, right_pts, "Road", collection, material)

def build_wall(edge_pts, offset_dirs, thickness, height, name, collection, material):
    n = len(edge_pts)
    ba, bb, ta, tb = [], [], [], []
    for i in range(n):
        p = edge_pts[i]
        off = offset_dirs[i].normalized() * thickness
        a, b = p.copy(), p + off
        ba.append(a); bb.append(b)
        ta.append(a + Vector((0, 0, height)))
        tb.append(b + Vector((0, 0, height)))
    verts = ba + bb + ta + tb
    faces = []
    i0, i1, i2, i3 = 0, n, 2 * n, 3 * n
    for i in range(n):
        j = (i + 1) % n
        faces.append([i0+i, i0+j, i2+j, i2+i])
        faces.append([i1+j, i1+i, i3+i, i3+j])
        faces.append([i2+i, i2+j, i3+j, i3+i])
        faces.append([i1+i, i1+j, i0+j, i0+i])
    return add_mesh_object(name, verts, faces, collection, material)

def build_terrain(min_x, max_x, min_y, max_y,
                  flat_centerline, track_bounds, collection, material):
    verts, faces = [], []
    size_x = max_x - min_x
    size_y = max_y - min_y

    for iy in range(TERRAIN_GRID_Y + 1):
        fy = iy / TERRAIN_GRID_Y
        y = min_y + size_y * fy
        for ix in range(TERRAIN_GRID_X + 1):
            fx = ix / TERRAIN_GRID_X
            x = min_x + size_x * fx
            point = Vector((x, y, 0.0))
            z = terrain_height_at(point, flat_centerline, track_bounds)
            verts.append(Vector((x, y, z)))

    stride = TERRAIN_GRID_X + 1
    for iy in range(TERRAIN_GRID_Y):
        for ix in range(TERRAIN_GRID_X):
            a = iy * stride + ix
            b = a + 1
            d = (iy + 1) * stride + ix
            c = d + 1
            faces.append([a, b, c, d])

    terrain = add_mesh_object("Ground", verts, faces, collection, material)
    for poly in terrain.data.polygons:
        poly.use_smooth = True
    return terrain

def add_oriented_box(name, center, ax_x, ax_y, ax_z,
                     sx, sy, sz, collection, material=None):
    ax = ax_x.normalized(); ay = ax_y.normalized(); az = ax_z.normalized()
    hx, hy, hz = sx*0.5, sy*0.5, sz*0.5
    verts = [
        center + s1*ax*hx + s2*ay*hy + s3*az*hz
        for s1, s2, s3 in [
            (-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
            (-1,-1, 1),(1,-1, 1),(1,1, 1),(-1,1, 1),
        ]
    ]
    faces = [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]
    return add_mesh_object(name, verts, faces, collection, material)

def object_frame_at_fraction(centerline, tangents, left_normals, frac, z_off=0.0):
    n = len(centerline)
    idx = int((frac % 1.0) * n) % n
    center = centerline[idx] + Vector((0, 0, z_off))
    return center, tangents[idx], left_normals[idx], Vector((0, 0, 1)), idx

# =============================================================================
#  START LINE + CHECKPOINTS
# =============================================================================

def build_start_line(centerline, tangents, left_normals, frac, rw, col, mat):
    c, t, l, up, _ = object_frame_at_fraction(centerline, tangents, left_normals, frac, 0.03)
    return add_oriented_box("StartLine", c, t, l, up, 0.75, rw*0.92, 0.05, col, mat)

def build_checkpoint(centerline, tangents, left_normals, idx, frac, rw, col, mat):
    c, t, l, up, _ = object_frame_at_fraction(
        centerline, tangents, left_normals, frac, CP_HEIGHT*0.5)
    return add_oriented_box(f"Checkpoint_{idx:02d}", c, t, l, up,
                            CP_THICK, rw+CP_EXTRA_W, CP_HEIGHT, col, mat)

# =============================================================================
#  CURBS (ribbon segments — no gaps between red/white)
# =============================================================================

def build_curbs(centerline, tangents, left_normals, rw, col, mat_a, mat_b):
    objs = []
    n = len(centerline)
    half_road = rw * 0.5
    z_up = Vector((0, 0, CURB_Z_OFF))
    z_top = Vector((0, 0, CURB_H + CURB_Z_OFF))

    seg_start, seg_idx = 0, 0
    while seg_start < n:
        seg_end = min(seg_start + CURB_STEP, n)
        curb_mat = mat_a if (seg_idx % 2 == 0) else mat_b
        indices = [idx % n for idx in range(seg_start, seg_end + 1)]

        for side_name, side_sign in [("CurbL", 1.0), ("CurbR", -1.0)]:
            verts, faces = [], []
            for idx in indices:
                c = centerline[idx]
                lft = left_normals[idx]
                inner = c + lft * (half_road * side_sign)
                outer = c + lft * ((half_road + CURB_W) * side_sign)
                verts += [inner+z_up, outer+z_up, inner+z_top, outer+z_top]

            nv = len(indices)
            for k in range(nv - 1):
                b = k * 4; nx = (k+1) * 4
                faces += [[b+2,b+3,nx+3,nx+2], [b+1,b+3,nx+3,nx+1],
                          [b+2,b+0,nx+0,nx+2], [b+0,b+1,nx+1,nx+0]]
            objs.append(add_mesh_object(f"{side_name}_{seg_start:03d}",
                                        verts, faces, col, curb_mat))
        seg_start = seg_end
        seg_idx += 1
    return objs

# =============================================================================
#  CENTER STRIPES
# =============================================================================

def build_center_stripes(centerline, tangents, left_normals, col, mat):
    objs = []
    up = Vector((0, 0, 1))
    for i in range(0, len(centerline), STRIPE_STEP):
        c = centerline[i] + Vector((0, 0, STRIPE_H*0.5 + 0.01))
        objs.append(add_oriented_box(f"Stripe_{i:03d}", c,
                    tangents[i], left_normals[i], up,
                    STRIPE_L, STRIPE_W, STRIPE_H, col, mat))
    return objs

# =============================================================================
#  BRIDGE SUPPORTS  (vertical columns under elevated road)
# =============================================================================

def build_bridge_supports(centerline, left_normals, rw,
                          flat_centerline, track_bounds, col, mat):
    objs = []
    n = len(centerline)
    half_w = rw * 0.5
    up = Vector((0, 0, 1))

    for i in range(n):
        z = centerline[i].z
        if z < BRIDGE_MIN_Z or i % BRIDGE_SUPPORT_STEP != 0:
            continue
        c = centerline[i]
        lft = left_normals[i]
        tangent = Vector((lft.y, -lft.x, 0))  # perpendicular to normal

        for side in [1.0, -1.0]:
            base_xy = c + lft * (half_w * side * 0.85)
            base_point = Vector((base_xy.x, base_xy.y, 0.0))
            base_z = terrain_height_at(base_point, flat_centerline, track_bounds)
            support_h = max(0.2, z - base_z)
            col_center = Vector((base_xy.x, base_xy.y, base_z + support_h * 0.5))
            objs.append(add_oriented_box(
                f"BridgeSupport_{i:03d}_{'L' if side>0 else 'R'}",
                col_center, tangent, lft, up,
                BRIDGE_SUPPORT_W, BRIDGE_SUPPORT_W, support_h,
                col, mat))
    return objs

# =============================================================================
#  BRIDGE DECK UNDERSIDE  (visible when driving beneath)
# =============================================================================

def build_bridge_deck(centerline, left_normals, rw, col, mat):
    n = len(centerline)
    half_w = rw * 0.5
    indices = [i for i in range(n) if centerline[i].z > 1.0]
    if len(indices) < 2:
        return None
    verts, faces = [], []
    for idx in indices:
        c = centerline[idx]; lft = left_normals[idx]
        bz = c.z - BRIDGE_DECK_THICK
        l = c + lft * half_w; r = c - lft * half_w
        verts += [Vector((l.x, l.y, bz)), Vector((r.x, r.y, bz))]
    m = len(indices)
    for k in range(m - 1):
        b, nx = k*2, (k+1)*2
        faces.append([b+1, b, nx, nx+1])  # normal facing down
    return add_mesh_object("BridgeDeck", verts, faces, col, mat)

# =============================================================================
#  FOREST — tree species
# =============================================================================

def create_deciduous_tree(name, location, scale, col, trunk_mat, canopy_mats):
    x, y, z = location
    rng = random.Random(hash(name))

    trunk_h = rng.uniform(4.0, 6.0) * scale
    bpy.ops.mesh.primitive_cone_add(
        vertices=10, radius1=0.30*scale, radius2=0.12*scale,
        depth=trunk_h, location=(x, y, z + trunk_h*0.5))
    trunk = bpy.context.active_object
    trunk.name = f"{name}_Trunk"
    relink_object(trunk, col)
    trunk.data.materials.clear()
    trunk.data.materials.append(trunk_mat)

    canopy_count = rng.randint(3, 5)
    canopy_r = rng.uniform(2.2, 3.2) * scale
    canopy_base = z + trunk_h * 0.75
    for ci in range(canopy_count):
        ox = rng.uniform(-1.0, 1.0) * scale
        oy = rng.uniform(-1.0, 1.0) * scale
        oz = rng.uniform(0.0, 2.0) * scale
        r = canopy_r * rng.uniform(0.6, 1.0)
        bpy.ops.mesh.primitive_ico_sphere_add(
            subdivisions=2, radius=r,
            location=(x+ox, y+oy, canopy_base+oz))
        sp = bpy.context.active_object
        sp.name = f"{name}_C{ci}"
        relink_object(sp, col)
        sp.data.materials.clear()
        sp.data.materials.append(rng.choice(canopy_mats))
        sp.scale = (rng.uniform(0.85,1.15), rng.uniform(0.85,1.15),
                    rng.uniform(0.7,1.0))

def create_pine_tree(name, location, scale, col, trunk_mat, canopy_mats):
    x, y, z = location
    rng = random.Random(hash(name))

    trunk_h = rng.uniform(5.0, 8.0) * scale
    bpy.ops.mesh.primitive_cone_add(
        vertices=8, radius1=0.26*scale, radius2=0.10*scale,
        depth=trunk_h, location=(x, y, z + trunk_h*0.5))
    trunk = bpy.context.active_object
    trunk.name = f"{name}_Trunk"
    relink_object(trunk, col)
    trunk.data.materials.clear()
    trunk.data.materials.append(trunk_mat)

    tier_count = rng.randint(3, 4)
    tier_start = z + trunk_h * 0.3
    tier_span = trunk_h * 0.85
    for ti in range(tier_count):
        frac = ti / tier_count
        tier_z = tier_start + frac * tier_span
        tier_r = (2.5 - frac*1.8) * scale * rng.uniform(0.85, 1.1)
        tier_h = (3.0 - frac*1.2) * scale * rng.uniform(0.8, 1.1)
        bpy.ops.mesh.primitive_cone_add(
            vertices=8, radius1=tier_r, radius2=0,
            depth=tier_h, location=(x, y, tier_z + tier_h*0.3))
        cone = bpy.context.active_object
        cone.name = f"{name}_T{ti}"
        relink_object(cone, col)
        cone.data.materials.clear()
        cone.data.materials.append(rng.choice(canopy_mats))

def create_bush(name, location, scale, col, bush_mats):
    x, y, z = location
    rng = random.Random(hash(name))
    for bi in range(rng.randint(2, 3)):
        ox = rng.uniform(-0.6, 0.6) * scale
        oy = rng.uniform(-0.6, 0.6) * scale
        r = rng.uniform(0.8, 1.5) * scale
        bpy.ops.mesh.primitive_ico_sphere_add(
            subdivisions=2, radius=r, location=(x+ox, y+oy, z + r*0.4))
        sp = bpy.context.active_object
        sp.name = f"{name}_B{bi}"
        relink_object(sp, col)
        sp.data.materials.clear()
        sp.data.materials.append(rng.choice(bush_mats))
        sp.scale = (rng.uniform(0.9,1.2), rng.uniform(0.9,1.2),
                    rng.uniform(0.45,0.65))

# =============================================================================
#  FOREST SCATTER
# =============================================================================

def scatter_forest(centerline, left_normals, rw,
                   flat_centerline, track_bounds, col,
                   trunk_mat, canopy_mats, bush_mats):
    random.seed(TREE_SEED)
    n = len(centerline)
    edge_off = rw * 0.5 + CURB_W + WALL_THICKNESS
    positions = []

    def too_close(loc, min_d=3.5):
        for p in positions:
            if (loc - p).length < min_d:
                return True
        return False

    def near_crossing(loc):
        return Vector((loc.x, loc.y)).length < CROSSING_EXCL

    def inside_track(loc):
        return winding_number_2d(loc, flat_centerline) != 0

    def too_close_to_any_road(loc, clearance):
        return min_distance_to_polyline(loc, flat_centerline) < edge_off + clearance

    def rand_loc(idx, clearance, jitter):
        side = random.choice([-1.0, 1.0])
        normal = left_normals[idx] * side
        dist = edge_off + clearance + random.uniform(0, jitter)
        c = centerline[idx]
        return Vector((c.x, c.y, 0)) + normal * dist

    # inner ring
    placed = 0
    for _ in range(INNER_TREES * 15):
        if placed >= INNER_TREES:
            break
        idx = random.randrange(n)
        loc = rand_loc(idx, TREE_CLEAR, INNER_JITTER)
        if (
            too_close(loc)
            or near_crossing(loc)
            or inside_track(loc)
            or too_close_to_any_road(loc, TREE_CLEAR)
        ):
            continue
        s = random.uniform(0.8, 1.6)
        xy = (
            loc.x,
            loc.y,
            terrain_height_at(loc, flat_centerline, track_bounds)
        )
        if random.random() < 0.55:
            create_deciduous_tree(f"Tree_{placed:03d}", xy, s, col, trunk_mat, canopy_mats)
        else:
            create_pine_tree(f"Tree_{placed:03d}", xy, s, col, trunk_mat, canopy_mats)
        positions.append(loc)
        placed += 1

    # outer ring
    placed = 0
    for _ in range(OUTER_TREES * 15):
        if placed >= OUTER_TREES:
            break
        idx = random.randrange(n)
        loc = rand_loc(idx, OUTER_MIN, OUTER_MAX - OUTER_MIN)
        if (
            too_close(loc, 2.5)
            or near_crossing(loc)
            or inside_track(loc)
            or too_close_to_any_road(loc, OUTER_MIN)
        ):
            continue
        s = random.uniform(1.0, 2.2)
        xy = (
            loc.x,
            loc.y,
            terrain_height_at(loc, flat_centerline, track_bounds)
        )
        if random.random() < 0.45:
            create_pine_tree(f"Forest_{placed:03d}", xy, s, col, trunk_mat, canopy_mats)
        else:
            create_deciduous_tree(f"Forest_{placed:03d}", xy, s, col, trunk_mat, canopy_mats)
        positions.append(loc)
        placed += 1

    # bushes
    placed = 0
    for _ in range(BUSHES * 15):
        if placed >= BUSHES:
            break
        idx = random.randrange(n)
        loc = rand_loc(idx, BUSH_CLEAR, BUSH_JITTER)
        if (
            too_close(loc, 2.0)
            or near_crossing(loc)
            or inside_track(loc)
            or too_close_to_any_road(loc, BUSH_CLEAR)
        ):
            continue
        s = random.uniform(0.6, 1.2)
        create_bush(
            f"Bush_{placed:03d}",
            (
                loc.x,
                loc.y,
                terrain_height_at(loc, flat_centerline, track_bounds)
            ),
            s,
            col,
            bush_mats
        )
        positions.append(loc)
        placed += 1

# =============================================================================
#  EXPORT
# =============================================================================

def export_glb(filepath):
    bpy.ops.export_scene.gltf(
        filepath=filepath,
        export_format='GLB',
        use_selection=True,
    )

# =============================================================================
#  BUILD SCENE
# =============================================================================

clear_scene()
collection = make_collection(COLLECTION_NAME)

# ---------- materials ----------
road_mat       = make_material("Road_Mat",       (0.055,0.055,0.06,1), roughness=0.92, specular=0.3)
wall_mat       = make_material("Wall_Mat",       (0.55,0.56,0.58,1),  roughness=0.75, specular=0.4)
ground_mat     = make_material("Ground_Mat",     (0.12,0.28,0.08,1),  roughness=1.0,  specular=0.1)
start_mat      = make_material("StartLine_Mat",  (0.95,0.95,0.95,1),  roughness=0.35, specular=0.6)
cp_mat         = make_material("Checkpoint_Mat", (1.0,0.75,0.1,0.3),  roughness=0.4)
curb_red       = make_material("Curb_Red",       (0.75,0.08,0.08,1),  roughness=0.65, specular=0.4)
curb_white     = make_material("Curb_White",     (0.92,0.92,0.92,1),  roughness=0.65, specular=0.4)
stripe_mat     = make_material("Stripe_Mat",     (0.90,0.88,0.65,1),  roughness=0.40, specular=0.5)
support_mat    = make_material("Support_Mat",    (0.48,0.46,0.44,1),  roughness=0.82, specular=0.3)
deck_mat       = make_material("Deck_Mat",       (0.40,0.40,0.42,1),  roughness=0.85, specular=0.25)
trunk_mat      = make_material("Trunk_Mat",      (0.14,0.08,0.03,1),  roughness=1.0,  specular=0.05)
canopy_mats = [
    make_material("Canopy_A", (0.06,0.22,0.05,1), roughness=0.92, specular=0.1),
    make_material("Canopy_B", (0.10,0.30,0.08,1), roughness=0.88, specular=0.12),
    make_material("Canopy_C", (0.15,0.35,0.10,1), roughness=0.85, specular=0.14),
    make_material("Canopy_D", (0.22,0.34,0.06,1), roughness=0.90, specular=0.10),
]
bush_mats = [
    make_material("Bush_A", (0.08,0.20,0.06,1), roughness=0.95, specular=0.08),
    make_material("Bush_B", (0.14,0.28,0.08,1), roughness=0.92, specular=0.10),
]

# ---------- centerline with elevation ----------
raw_2d = sample_closed_catmull_rom(CONTROL_POINTS, SAMPLES_PER_SEG)
flat_cl = resample_closed_polyline(raw_2d, CURVE_SAMPLES)

centerline = []
for i, pt in enumerate(flat_cl):
    z = compute_elevation(i / len(flat_cl))
    centerline.append(Vector((pt.x, pt.y, z)))

tangents, left_normals = compute_frames(centerline)
flat_centerline = [Vector((p.x, p.y, 0.0)) for p in centerline]
track_bounds = (
    min(p.x for p in flat_centerline),
    max(p.x for p in flat_centerline),
    min(p.y for p in flat_centerline),
    max(p.y for p in flat_centerline),
)

# ---------- edges ----------
half_w = ROAD_WIDTH * 0.5
left_edge  = [centerline[i] + left_normals[i] * half_w  for i in range(len(centerline))]
right_edge = [centerline[i] - left_normals[i] * half_w  for i in range(len(centerline))]

# ---------- road ----------
road = build_road(left_edge, right_edge, collection, road_mat)

# ---------- walls ----------
left_wall  = build_wall(left_edge,  left_normals,
                        WALL_THICKNESS, WALL_HEIGHT, "LeftWall", collection, wall_mat)
right_wall = build_wall(right_edge, [(-n) for n in left_normals],
                        WALL_THICKNESS, WALL_HEIGHT, "RightWall", collection, wall_mat)

# ---------- curbs ----------
build_curbs(centerline, tangents, left_normals, ROAD_WIDTH, collection, curb_red, curb_white)

# ---------- stripes ----------
build_center_stripes(centerline, tangents, left_normals, collection, stripe_mat)

# ---------- terrain ----------
ground = build_terrain(
    track_bounds[0] - TERRAIN_MARGIN,
    track_bounds[1] + TERRAIN_MARGIN,
    track_bounds[2] - TERRAIN_MARGIN,
    track_bounds[3] + TERRAIN_MARGIN,
    flat_centerline,
    track_bounds,
    collection,
    ground_mat
)

# ---------- start line ----------
build_start_line(centerline, tangents, left_normals, START_FRAC, ROAD_WIDTH, collection, start_mat)

# ---------- checkpoints ----------
for idx, frac in enumerate(CP_FRACS, start=1):
    build_checkpoint(centerline, tangents, left_normals, idx, frac, ROAD_WIDTH, collection, cp_mat)

# ---------- bridge supports ----------
build_bridge_supports(
    centerline,
    left_normals,
    ROAD_WIDTH,
    flat_centerline,
    track_bounds,
    collection,
    support_mat
)

# ---------- bridge deck underside ----------
build_bridge_deck(centerline, left_normals, ROAD_WIDTH, collection, deck_mat)

# ---------- forest ----------
scatter_forest(centerline, left_normals, ROAD_WIDTH,
               flat_centerline, track_bounds, collection,
               trunk_mat, canopy_mats, bush_mats)

# ---------- export ----------
bpy.ops.object.select_all(action='DESELECT')
for obj in collection.objects:
    if obj.type == 'MESH':
        obj.select_set(True)
bpy.context.view_layer.objects.active = road
export_glb(out_path)

print(f"Exported figure-8 track: {out_path}")
print(f"  {CURVE_SAMPLES} centerline samples, bridge height {BRIDGE_HEIGHT}")
print(f"  Layout scale {LAYOUT_SCALE}x, ~{len(centerline)} road segments")
