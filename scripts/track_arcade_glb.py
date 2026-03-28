import bpy
import math
import os
import sys
import random
from mathutils import Vector

# ---------------------------------
# output path passed after "--"
# example:
# blender -b --python track_arcade_glb.py -- /Volumes/external/exports/racetrack_arcade_v2.glb
# ---------------------------------
argv = sys.argv
if "--" in argv:
    out_path = argv[argv.index("--") + 1]
else:
    out_path = "/Volumes/external/exports/racetrack_arcade_v2.glb"

os.makedirs(os.path.dirname(out_path), exist_ok=True)

# ---------------------------------
# config
# ---------------------------------
COLLECTION_NAME = "RaceTrackArcade"

ROAD_WIDTH = 8.0
ROAD_Z = 0.0
ROAD_THICKNESS = 0.02

WALL_HEIGHT = 1.8
WALL_THICKNESS = 0.35

GROUND_MARGIN = 18.0
GROUND_Z = -0.05

CURVE_SAMPLES = 240

START_LINE_FRACTION = 0.02
CHECKPOINT_FRACTIONS = [0.18, 0.38, 0.58, 0.78]

CHECKPOINT_HEIGHT = 3.2
CHECKPOINT_THICKNESS = 0.45
CHECKPOINT_EXTRA_WIDTH = 1.2

# curbs
CURB_WIDTH = 0.7
CURB_HEIGHT = 0.16
CURB_LENGTH = 1.9
CURB_STEP = 3   # place one curb every N sampled points

# center stripes
STRIPE_WIDTH = 0.22
STRIPE_HEIGHT = 0.035
STRIPE_LENGTH = 1.4
STRIPE_STEP = 6

# trees
TREE_COUNT = 42
TREE_CLEARANCE = 5.0
TREE_JITTER = 4.0
TREE_SEED = 11
TREE_MIN_SCALE = 0.85
TREE_MAX_SCALE = 1.4

# Closed control points for an arcade-style track.
TRACK_CONTROL_POINTS = [
    Vector((-30.0, -4.0, ROAD_Z)),
    Vector((-24.0, -16.0, ROAD_Z)),
    Vector((-8.0, -21.0, ROAD_Z)),
    Vector((10.0, -19.0, ROAD_Z)),
    Vector((28.0, -10.0, ROAD_Z)),
    Vector((31.0,  3.0, ROAD_Z)),
    Vector((21.0, 16.0, ROAD_Z)),
    Vector((5.0,  22.0, ROAD_Z)),
    Vector((-12.0, 20.0, ROAD_Z)),
    Vector((-28.0, 12.0, ROAD_Z)),
]

# ---------------------------------
# helpers
# ---------------------------------
def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

    for block in list(bpy.data.meshes):
        if block.users == 0:
            bpy.data.meshes.remove(block)

    for block in list(bpy.data.materials):
        if block.users == 0:
            bpy.data.materials.remove(block)

def make_material(name, color, roughness=0.8):
    existing = bpy.data.materials.get(name)
    if existing:
        bpy.data.materials.remove(existing, do_unlink=True)

    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
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

def closed_catmull_rom(p0, p1, p2, p3, t):
    t2 = t * t
    t3 = t2 * t
    return 0.5 * (
        (2.0 * p1) +
        (-p0 + p2) * t +
        (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2 +
        (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
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
            t = s / samples_per_segment
            pts.append(closed_catmull_rom(p0, p1, p2, p3, t))

    return pts

def resample_closed_polyline(points, target_count):
    n = len(points)
    if n < 2:
        return points[:]

    seg_lengths = []
    total = 0.0
    for i in range(n):
        j = (i + 1) % n
        d = (points[j] - points[i]).length
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
            seg_len = seg_lengths[seg_index]
            if seg_start_dist + seg_len >= target_dist or seg_len == 0:
                break
            seg_start_dist += seg_len
            seg_index = (seg_index + 1) % n

        a = points[seg_index]
        b = points[(seg_index + 1) % n]
        seg_len = seg_lengths[seg_index]

        if seg_len == 0:
            out.append(a.copy())
        else:
            local_t = (target_dist - seg_start_dist) / seg_len
            out.append(a.lerp(b, local_t))

    return out

def compute_frames(centerline):
    tangents = []
    left_normals = []

    n = len(centerline)
    for i in range(n):
        prev_pt = centerline[(i - 1) % n]
        next_pt = centerline[(i + 1) % n]
        tangent = next_pt - prev_pt
        tangent.z = 0.0
        if tangent.length == 0:
            tangent = Vector((1.0, 0.0, 0.0))
        tangent.normalize()

        left = Vector((-tangent.y, tangent.x, 0.0))
        if left.length == 0:
            left = Vector((0.0, 1.0, 0.0))
        left.normalize()

        tangents.append(tangent)
        left_normals.append(left)

    return tangents, left_normals

def build_ribbon(a_pts, b_pts, name, collection, material):
    n = len(a_pts)
    verts = [p.copy() for p in a_pts] + [p.copy() for p in b_pts]
    faces = []

    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, n + j, n + i])

    return add_mesh_object(name, verts, faces, collection, material)

def build_road(left_pts, right_pts, collection, material):
    return build_ribbon(left_pts, right_pts, "Road", collection, material)

def build_wall(edge_pts, offset_dirs, thickness, height, name, collection, material):
    n = len(edge_pts)

    base_a = []
    base_b = []
    top_a = []
    top_b = []

    for i in range(n):
        p = edge_pts[i]
        offset = offset_dirs[i].normalized() * thickness

        a = p.copy()
        b = p + offset
        a_top = a + Vector((0, 0, height))
        b_top = b + Vector((0, 0, height))

        base_a.append(a)
        base_b.append(b)
        top_a.append(a_top)
        top_b.append(b_top)

    verts = base_a + base_b + top_a + top_b
    faces = []

    i0 = 0
    i1 = n
    i2 = 2 * n
    i3 = 3 * n

    for i in range(n):
        j = (i + 1) % n
        faces.append([i0 + i, i0 + j, i2 + j, i2 + i])
        faces.append([i1 + j, i1 + i, i3 + i, i3 + j])
        faces.append([i2 + i, i2 + j, i3 + j, i3 + i])
        faces.append([i1 + i, i1 + j, i0 + j, i0 + i])

    return add_mesh_object(name, verts, faces, collection, material)

def build_ground(size_x, size_y, z, collection, material):
    hx = size_x * 0.5
    hy = size_y * 0.5
    verts = [
        Vector((-hx, -hy, z)),
        Vector(( hx, -hy, z)),
        Vector(( hx,  hy, z)),
        Vector((-hx,  hy, z)),
    ]
    faces = [[0, 1, 2, 3]]
    return add_mesh_object("Ground", verts, faces, collection, material)

def add_oriented_box(name, center, axis_x, axis_y, axis_z, size_x, size_y, size_z, collection, material=None):
    ax = axis_x.normalized()
    ay = axis_y.normalized()
    az = axis_z.normalized()

    hx = size_x * 0.5
    hy = size_y * 0.5
    hz = size_z * 0.5

    verts = [
        center + (-ax * hx) + (-ay * hy) + (-az * hz),
        center + ( ax * hx) + (-ay * hy) + (-az * hz),
        center + ( ax * hx) + ( ay * hy) + (-az * hz),
        center + (-ax * hx) + ( ay * hy) + (-az * hz),
        center + (-ax * hx) + (-ay * hy) + ( az * hz),
        center + ( ax * hx) + (-ay * hy) + ( az * hz),
        center + ( ax * hx) + ( ay * hy) + ( az * hz),
        center + (-ax * hx) + ( ay * hy) + ( az * hz),
    ]

    faces = [
        [0, 3, 2, 1],
        [4, 5, 6, 7],
        [0, 1, 5, 4],
        [1, 2, 6, 5],
        [2, 3, 7, 6],
        [3, 0, 4, 7],
    ]

    return add_mesh_object(name, verts, faces, collection, material)

def object_frame_at_fraction(centerline, tangents, left_normals, fraction, z_offset=0.0):
    n = len(centerline)
    idx = int((fraction % 1.0) * n) % n
    center = centerline[idx] + Vector((0.0, 0.0, z_offset))
    tangent = tangents[idx]
    left = left_normals[idx]
    up = Vector((0.0, 0.0, 1.0))
    return center, tangent, left, up, idx

def build_start_line(centerline, tangents, left_normals, fraction, road_width, z, collection, material):
    center, tangent, left, up, _ = object_frame_at_fraction(
        centerline, tangents, left_normals, fraction, z_offset=0.03
    )

    return add_oriented_box(
        name="StartLine",
        center=center,
        axis_x=tangent,
        axis_y=left,
        axis_z=up,
        size_x=0.55,
        size_y=road_width * 0.92,
        size_z=0.04,
        collection=collection,
        material=material,
    )

def build_checkpoint(centerline, tangents, left_normals, index, fraction, road_width, z, collection, material):
    center, tangent, left, up, _ = object_frame_at_fraction(
        centerline, tangents, left_normals, fraction, z_offset=CHECKPOINT_HEIGHT * 0.5
    )

    return add_oriented_box(
        name=f"Checkpoint_{index:02d}",
        center=center,
        axis_x=tangent,
        axis_y=left,
        axis_z=up,
        size_x=CHECKPOINT_THICKNESS,
        size_y=road_width + CHECKPOINT_EXTRA_WIDTH,
        size_z=CHECKPOINT_HEIGHT,
        collection=collection,
        material=material,
    )

def build_curbs(centerline, tangents, left_normals, road_width, collection, mat_a, mat_b):
    objs = []
    n = len(centerline)
    half_road = road_width * 0.5
    up = Vector((0.0, 0.0, 1.0))

    for i in range(0, n, CURB_STEP):
        tangent = tangents[i]
        left = left_normals[i]
        center = centerline[i]

        curb_mat = mat_a if ((i // CURB_STEP) % 2 == 0) else mat_b

        left_center = center + left * (half_road + CURB_WIDTH * 0.5)
        right_center = center - left * (half_road + CURB_WIDTH * 0.5)

        objs.append(add_oriented_box(
            name=f"CurbL_{i:03d}",
            center=left_center + Vector((0.0, 0.0, CURB_HEIGHT * 0.5)),
            axis_x=tangent,
            axis_y=left,
            axis_z=up,
            size_x=CURB_LENGTH,
            size_y=CURB_WIDTH,
            size_z=CURB_HEIGHT,
            collection=collection,
            material=curb_mat,
        ))

        objs.append(add_oriented_box(
            name=f"CurbR_{i:03d}",
            center=right_center + Vector((0.0, 0.0, CURB_HEIGHT * 0.5)),
            axis_x=tangent,
            axis_y=left,
            axis_z=up,
            size_x=CURB_LENGTH,
            size_y=CURB_WIDTH,
            size_z=CURB_HEIGHT,
            collection=collection,
            material=curb_mat,
        ))

    return objs

def build_center_stripes(centerline, tangents, left_normals, collection, material):
    objs = []
    up = Vector((0.0, 0.0, 1.0))

    for i in range(0, len(centerline), STRIPE_STEP):
        center = centerline[i] + Vector((0.0, 0.0, STRIPE_HEIGHT * 0.5 + 0.01))
        tangent = tangents[i]
        left = left_normals[i]

        objs.append(add_oriented_box(
            name=f"Stripe_{i:03d}",
            center=center,
            axis_x=tangent,
            axis_y=left,
            axis_z=up,
            size_x=STRIPE_LENGTH,
            size_y=STRIPE_WIDTH,
            size_z=STRIPE_HEIGHT,
            collection=collection,
            material=material,
        ))

    return objs

def create_tree(name, location, scale, collection, trunk_material, leaves_material):
    x, y, z = location

    trunk_h = 2.2 * scale
    trunk_r = 0.18 * scale
    crown1_h = 2.4 * scale
    crown1_r = 1.2 * scale
    crown2_h = 1.9 * scale
    crown2_r = 0.85 * scale

    bpy.ops.mesh.primitive_cylinder_add(
        vertices=8,
        radius=trunk_r,
        depth=trunk_h,
        location=(x, y, z + trunk_h * 0.5),
    )
    trunk = bpy.context.active_object
    trunk.name = f"{name}_Trunk"
    relink_object(trunk, collection)
    trunk.data.materials.clear()
    trunk.data.materials.append(trunk_material)

    bpy.ops.mesh.primitive_cone_add(
        vertices=7,
        radius1=crown1_r,
        radius2=0.0,
        depth=crown1_h,
        location=(x, y, z + trunk_h + crown1_h * 0.5 - 0.15 * scale),
    )
    crown1 = bpy.context.active_object
    crown1.name = f"{name}_CrownA"
    relink_object(crown1, collection)
    crown1.data.materials.clear()
    crown1.data.materials.append(leaves_material)

    bpy.ops.mesh.primitive_cone_add(
        vertices=7,
        radius1=crown2_r,
        radius2=0.0,
        depth=crown2_h,
        location=(x, y, z + trunk_h + crown1_h * 0.7),
    )
    crown2 = bpy.context.active_object
    crown2.name = f"{name}_CrownB"
    relink_object(crown2, collection)
    crown2.data.materials.clear()
    crown2.data.materials.append(leaves_material)

def scatter_trees(centerline, left_normals, road_width, count, collection, trunk_material, leaves_material):
    random.seed(TREE_SEED)
    n = len(centerline)

    start_idx = int(START_LINE_FRACTION * n) % n

    placed = 0
    attempts = 0

    while placed < count and attempts < count * 12:
        attempts += 1
        idx = random.randrange(n)

        wrapped = min((idx - start_idx) % n, (start_idx - idx) % n)
        if wrapped < n * 0.06:
            continue

        side = random.choice([-1.0, 1.0])
        normal = left_normals[idx] * side

        base = centerline[idx] + normal * (road_width * 0.5 + CURB_WIDTH + WALL_THICKNESS + TREE_CLEARANCE)
        jitter = normal * random.uniform(0.0, TREE_JITTER)
        loc = base + jitter

        scale = random.uniform(TREE_MIN_SCALE, TREE_MAX_SCALE)

        create_tree(
            name=f"Tree_{placed:03d}",
            location=(loc.x, loc.y, ROAD_Z),
            scale=scale,
            collection=collection,
            trunk_material=trunk_material,
            leaves_material=leaves_material,
        )
        placed += 1

def export_selected(filepath):
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".glb":
        bpy.ops.export_scene.gltf(
            filepath=filepath,
            export_format='GLB',
            use_selection=True,
        )
    elif ext == ".fbx":
        bpy.ops.export_scene.fbx(
            filepath=filepath,
            use_selection=True,
            object_types={'MESH'},
            apply_unit_scale=True,
            bake_space_transform=False,
            axis_forward='-Z',
            axis_up='Y'
        )
    else:
        raise ValueError(f"Unsupported export format: {ext}. Use .glb or .fbx")

# ---------------------------------
# build scene
# ---------------------------------
clear_scene()
collection = make_collection(COLLECTION_NAME)

road_mat = make_material("Road_Mat", (0.08, 0.08, 0.08, 1.0), roughness=0.96)
wall_mat = make_material("Wall_Mat", (0.72, 0.72, 0.75, 1.0), roughness=0.7)
ground_mat = make_material("Ground_Mat", (0.08, 0.22, 0.08, 1.0), roughness=1.0)

start_line_mat = make_material("StartLine_Mat", (1.0, 1.0, 1.0, 1.0), roughness=0.45)
checkpoint_mat = make_material("Checkpoint_Mat", (1.0, 0.75, 0.1, 1.0), roughness=0.4)

curb_red_mat = make_material("Curb_Red_Mat", (0.82, 0.14, 0.14, 1.0), roughness=0.7)
curb_white_mat = make_material("Curb_White_Mat", (0.95, 0.95, 0.95, 1.0), roughness=0.7)
stripe_mat = make_material("Stripe_Mat", (0.95, 0.95, 0.75, 1.0), roughness=0.5)

trunk_mat = make_material("Trunk_Mat", (0.22, 0.12, 0.05, 1.0), roughness=1.0)
leaves_mat = make_material("Leaves_Mat", (0.08, 0.32, 0.10, 1.0), roughness=1.0)

raw_curve = sample_closed_catmull_rom(TRACK_CONTROL_POINTS, samples_per_segment=28)
centerline = resample_closed_polyline(raw_curve, CURVE_SAMPLES)
tangents, left_normals = compute_frames(centerline)

left_edge = []
right_edge = []
half_width = ROAD_WIDTH * 0.5

for i in range(len(centerline)):
    c = centerline[i]
    left = left_normals[i]
    left_edge.append(c + left * half_width)
    right_edge.append(c - left * half_width)

road = build_road(left_edge, right_edge, collection, road_mat)

left_wall_dirs = left_normals
right_wall_dirs = [(-n) for n in left_normals]

left_wall = build_wall(left_edge, left_wall_dirs, WALL_THICKNESS, WALL_HEIGHT, "LeftWall", collection, wall_mat)
right_wall = build_wall(right_edge, right_wall_dirs, WALL_THICKNESS, WALL_HEIGHT, "RightWall", collection, wall_mat)

curbs = build_curbs(
    centerline=centerline,
    tangents=tangents,
    left_normals=left_normals,
    road_width=ROAD_WIDTH,
    collection=collection,
    mat_a=curb_red_mat,
    mat_b=curb_white_mat,
)

stripes = build_center_stripes(
    centerline=centerline,
    tangents=tangents,
    left_normals=left_normals,
    collection=collection,
    material=stripe_mat,
)

xs = [p.x for p in centerline]
ys = [p.y for p in centerline]
ground_size_x = (max(xs) - min(xs)) + 2.0 * (GROUND_MARGIN + ROAD_WIDTH)
ground_size_y = (max(ys) - min(ys)) + 2.0 * (GROUND_MARGIN + ROAD_WIDTH)
ground_center_x = (max(xs) + min(xs)) * 0.5
ground_center_y = (max(ys) + min(ys)) * 0.5

ground = build_ground(ground_size_x, ground_size_y, GROUND_Z, collection, ground_mat)
ground.location.x = ground_center_x
ground.location.y = ground_center_y

start_line = build_start_line(
    centerline=centerline,
    tangents=tangents,
    left_normals=left_normals,
    fraction=START_LINE_FRACTION,
    road_width=ROAD_WIDTH,
    z=ROAD_Z,
    collection=collection,
    material=start_line_mat,
)

checkpoints = []
for idx, fraction in enumerate(CHECKPOINT_FRACTIONS, start=1):
    cp = build_checkpoint(
        centerline=centerline,
        tangents=tangents,
        left_normals=left_normals,
        index=idx,
        fraction=fraction,
        road_width=ROAD_WIDTH,
        z=ROAD_Z,
        collection=collection,
        material=checkpoint_mat,
    )
    checkpoints.append(cp)

scatter_trees(
    centerline=centerline,
    left_normals=left_normals,
    road_width=ROAD_WIDTH,
    count=TREE_COUNT,
    collection=collection,
    trunk_material=trunk_mat,
    leaves_material=leaves_mat,
)

# ---------------------------------
# export all mesh objects in collection
# ---------------------------------
bpy.ops.object.select_all(action='DESELECT')
for obj in collection.objects:
    if obj.type == 'MESH':
        obj.select_set(True)

bpy.context.view_layer.objects.active = road
export_selected(out_path)

print(f"Exported: {out_path}")
