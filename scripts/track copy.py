import bpy
import math
import os
import sys
import random
from mathutils import Vector

# ---------------------------------
# output path passed after "--"
# example:
# blender -b --python track.py -- /Volumes/external/exports/racetrack_proto_v2.fbx
# ---------------------------------
argv = sys.argv
if "--" in argv:
    out_path = argv[argv.index("--") + 1]
else:
    out_path = "/Volumes/external/exports/racetrack_proto_v2.fbx"

os.makedirs(os.path.dirname(out_path), exist_ok=True)

# ---------------------------------
# config
# ---------------------------------
SEGMENTS = 96
RADIUS_X = 28.0
RADIUS_Y = 18.0
ROAD_WIDTH = 8.0
ROAD_Z = 0.0

WALL_HEIGHT = 1.8
WALL_THICKNESS = 0.35

GROUND_MARGIN = 24.0
GROUND_Z = -0.05

COLLECTION_NAME = "RaceTrackProto"

# gameplay / decor
START_LINE_ANGLE = 0.0  # 0 = right side of the oval

CHECKPOINT_ANGLES = [
    0.0,
    math.pi * 0.5,
    math.pi,
    math.pi * 1.5,
]

CHECKPOINT_HEIGHT = 3.2
CHECKPOINT_THICKNESS = 0.35
CHECKPOINT_EXTRA_WIDTH = 1.2

TREE_COUNT = 36
TREE_CLEARANCE = 4.5
TREE_JITTER = 3.5
TREE_SEED = 7
TREE_MIN_SCALE = 0.85
TREE_MAX_SCALE = 1.35

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

def make_material(name, color):
    existing = bpy.data.materials.get(name)
    if existing:
        bpy.data.materials.remove(existing, do_unlink=True)

    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 0.8
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

def loop_points(rx, ry, z, count):
    pts = []
    for i in range(count):
        t = (i / count) * math.tau
        pts.append(Vector((math.cos(t) * rx, math.sin(t) * ry, z)))
    return pts

def tangent_normal(prev_pt, next_pt):
    tangent = next_pt - prev_pt
    tangent.z = 0.0
    if tangent.length == 0:
        tangent = Vector((1.0, 0.0, 0.0))
    tangent.normalize()

    inward = Vector((-tangent.y, tangent.x, 0.0))
    if inward.length == 0:
        inward = Vector((0.0, 1.0, 0.0))
    inward.normalize()
    return inward

def ellipse_frame(rx, ry, angle, z=0.0):
    p = Vector((math.cos(angle) * rx, math.sin(angle) * ry, z))

    tangent = Vector((
        -math.sin(angle) * rx,
         math.cos(angle) * ry,
         0.0
    ))
    if tangent.length == 0:
        tangent = Vector((0.0, 1.0, 0.0))
    tangent.normalize()

    inward = Vector((-tangent.y, tangent.x, 0.0))
    if inward.length == 0:
        inward = Vector((-1.0, 0.0, 0.0))
    inward.normalize()

    return p, tangent, inward

def add_oriented_box(name, center, axis_x, axis_y, axis_z, size_x, size_y, size_z, collection, material=None):
    ax = axis_x.normalized()
    ay = axis_y.normalized()
    az = axis_z.normalized()

    hx = size_x * 0.5
    hy = size_y * 0.5
    hz = size_z * 0.5

    verts = [
        center + (-ax * hx) + (-ay * hy) + (-az * hz),  # 0
        center + ( ax * hx) + (-ay * hy) + (-az * hz),  # 1
        center + ( ax * hx) + ( ay * hy) + (-az * hz),  # 2
        center + (-ax * hx) + ( ay * hy) + (-az * hz),  # 3
        center + (-ax * hx) + (-ay * hy) + ( az * hz),  # 4
        center + ( ax * hx) + (-ay * hy) + ( az * hz),  # 5
        center + ( ax * hx) + ( ay * hy) + ( az * hz),  # 6
        center + (-ax * hx) + ( ay * hy) + ( az * hz),  # 7
    ]

    faces = [
        [0, 3, 2, 1],  # bottom
        [4, 5, 6, 7],  # top
        [0, 1, 5, 4],
        [1, 2, 6, 5],
        [2, 3, 7, 6],
        [3, 0, 4, 7],
    ]

    return add_mesh_object(name, verts, faces, collection, material)

def build_road(outer_pts, inner_pts, collection, material):
    n = len(outer_pts)
    verts = [p.copy() for p in outer_pts] + [p.copy() for p in inner_pts]
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, n + j, n + i])
    return add_mesh_object("Road", verts, faces, collection, material)

def build_wall(path_pts, thickness, height, direction_sign, name, collection, material):
    n = len(path_pts)

    base_a = []
    base_b = []
    top_a = []
    top_b = []

    for i in range(n):
        prev_pt = path_pts[(i - 1) % n]
        next_pt = path_pts[(i + 1) % n]
        p = path_pts[i]

        inward = tangent_normal(prev_pt, next_pt)
        offset = inward * direction_sign * thickness

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

        faces.append([i0 + i, i0 + j, i2 + j, i2 + i])  # side 1
        faces.append([i1 + j, i1 + i, i3 + i, i3 + j])  # side 2
        faces.append([i2 + i, i2 + j, i3 + j, i3 + i])  # top
        faces.append([i1 + i, i1 + j, i0 + j, i0 + i])  # bottom

    return add_mesh_object(name, verts, faces, collection, material)

def build_ground(size_x, size_y, z, collection, material):
    hx = size_x / 2
    hy = size_y / 2
    verts = [
        Vector((-hx, -hy, z)),
        Vector(( hx, -hy, z)),
        Vector(( hx,  hy, z)),
        Vector((-hx,  hy, z)),
    ]
    faces = [[0, 1, 2, 3]]
    return add_mesh_object("Ground", verts, faces, collection, material)

def build_start_line(angle, rx, ry, road_width, z, collection, material):
    p, tangent, inward = ellipse_frame(rx, ry, angle, z + 0.03)
    up = Vector((0.0, 0.0, 1.0))

    return add_oriented_box(
        name="StartLine",
        center=p,
        axis_x=tangent,
        axis_y=inward,
        axis_z=up,
        size_x=0.5,
        size_y=road_width * 0.92,
        size_z=0.04,
        collection=collection,
        material=material,
    )

def build_checkpoint(index, angle, rx, ry, road_width, z, collection, material):
    p, tangent, inward = ellipse_frame(rx, ry, angle, z + CHECKPOINT_HEIGHT * 0.5)
    up = Vector((0.0, 0.0, 1.0))
    width = road_width + CHECKPOINT_EXTRA_WIDTH

    return add_oriented_box(
        name=f"Checkpoint_{index:02d}",
        center=p,
        axis_x=tangent,
        axis_y=inward,
        axis_z=up,
        size_x=CHECKPOINT_THICKNESS,
        size_y=width,
        size_z=CHECKPOINT_HEIGHT,
        collection=collection,
        material=material,
    )

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

def scatter_trees(count, outer_rx, outer_ry, z, collection, trunk_material, leaves_material):
    random.seed(TREE_SEED)

    placed = 0
    attempts = 0

    while placed < count and attempts < count * 8:
        attempts += 1
        angle = random.uniform(0.0, math.tau)

        # keep some open space near the start line
        delta = abs((angle - START_LINE_ANGLE + math.pi) % math.tau - math.pi)
        if delta < 0.35:
            continue

        p, _, inward = ellipse_frame(outer_rx, outer_ry, angle, z)
        outward = -inward

        dist = TREE_CLEARANCE + random.uniform(0.0, TREE_JITTER)
        loc = p + outward * dist

        scale = random.uniform(TREE_MIN_SCALE, TREE_MAX_SCALE)

        create_tree(
            name=f"Tree_{placed:03d}",
            location=(loc.x, loc.y, z),
            scale=scale,
            collection=collection,
            trunk_material=trunk_material,
            leaves_material=leaves_material,
        )
        placed += 1

# ---------------------------------
# build scene
# ---------------------------------
clear_scene()
collection = make_collection(COLLECTION_NAME)

road_mat = make_material("Road_Mat", (0.08, 0.08, 0.08, 1.0))
wall_mat = make_material("Wall_Mat", (0.72, 0.72, 0.75, 1.0))
ground_mat = make_material("Ground_Mat", (0.08, 0.22, 0.08, 1.0))
start_line_mat = make_material("StartLine_Mat", (1.0, 1.0, 1.0, 1.0))
checkpoint_mat = make_material("Checkpoint_Mat", (1.0, 0.75, 0.1, 1.0))
trunk_mat = make_material("Trunk_Mat", (0.22, 0.12, 0.05, 1.0))
leaves_mat = make_material("Leaves_Mat", (0.08, 0.32, 0.10, 1.0))

outer_rx = RADIUS_X + ROAD_WIDTH / 2
outer_ry = RADIUS_Y + ROAD_WIDTH / 2
inner_rx = RADIUS_X - ROAD_WIDTH / 2
inner_ry = RADIUS_Y - ROAD_WIDTH / 2

if inner_rx <= 0 or inner_ry <= 0:
    raise ValueError("ROAD_WIDTH is too large for the chosen radii")

outer_pts = loop_points(outer_rx, outer_ry, ROAD_Z, SEGMENTS)
inner_pts = loop_points(inner_rx, inner_ry, ROAD_Z, SEGMENTS)

road = build_road(outer_pts, inner_pts, collection, road_mat)
outer_wall = build_wall(outer_pts, WALL_THICKNESS, WALL_HEIGHT, -1, "OuterWall", collection, wall_mat)
inner_wall = build_wall(inner_pts, WALL_THICKNESS, WALL_HEIGHT, +1, "InnerWall", collection, wall_mat)

ground_size_x = (outer_rx + GROUND_MARGIN) * 2
ground_size_y = (outer_ry + GROUND_MARGIN) * 2
ground = build_ground(ground_size_x, ground_size_y, GROUND_Z, collection, ground_mat)

start_line = build_start_line(
    angle=START_LINE_ANGLE,
    rx=RADIUS_X,
    ry=RADIUS_Y,
    road_width=ROAD_WIDTH,
    z=ROAD_Z,
    collection=collection,
    material=start_line_mat,
)

checkpoints = []
for idx, angle in enumerate(CHECKPOINT_ANGLES, start=1):
    cp = build_checkpoint(
        index=idx,
        angle=angle,
        rx=RADIUS_X,
        ry=RADIUS_Y,
        road_width=ROAD_WIDTH,
        z=ROAD_Z,
        collection=collection,
        material=checkpoint_mat,
    )
    checkpoints.append(cp)

scatter_trees(
    count=TREE_COUNT,
    outer_rx=outer_rx + WALL_THICKNESS,
    outer_ry=outer_ry + WALL_THICKNESS,
    z=ROAD_Z,
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

bpy.ops.export_scene.fbx(
    filepath=out_path,
    use_selection=True,
    object_types={'MESH'},
    apply_unit_scale=True,
    bake_space_transform=False,
    axis_forward='-Z',
    axis_up='Y'
)

print(f"Exported: {out_path}")
