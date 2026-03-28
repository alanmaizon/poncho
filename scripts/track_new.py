import bpy
import math
import os
import sys
from mathutils import Vector

# ---------------------------------
# output path passed after "--"
# example:
# blender -b --python track.py -- /Volumes/external/exports/racetrack_proto.fbx
# ---------------------------------
argv = sys.argv
if "--" in argv:
    out_path = argv[argv.index("--") + 1]
else:
    out_path = "/Volumes/external/exports/racetrack_proto.fbx"

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

# ---------------------------------
# helpers
# ---------------------------------
def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)

    for block in bpy.data.materials:
        if block.users == 0:
            bpy.data.materials.remove(block)

def make_material(name, color):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 0.8
    return mat

def make_collection(name):
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col

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
    tangent.z = 0
    tangent.normalize()
    inward = Vector((-tangent.y, tangent.x, 0.0))
    inward.normalize()
    return inward

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

        # side 1
        faces.append([i0 + i, i0 + j, i2 + j, i2 + i])
        # side 2
        faces.append([i1 + j, i1 + i, i3 + i, i3 + j])
        # top
        faces.append([i2 + i, i2 + j, i3 + j, i3 + i])
        # bottom
        faces.append([i1 + i, i1 + j, i0 + j, i0 + i])

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

# ---------------------------------
# build scene
# ---------------------------------
clear_scene()
collection = make_collection(COLLECTION_NAME)

road_mat = make_material("Road_Mat", (0.08, 0.08, 0.08, 1.0))
wall_mat = make_material("Wall_Mat", (0.72, 0.72, 0.75, 1.0))
ground_mat = make_material("Ground_Mat", (0.08, 0.22, 0.08, 1.0))

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

# select exportable objects
bpy.ops.object.select_all(action='DESELECT')
for obj in [road, outer_wall, inner_wall, ground]:
    obj.select_set(True)

bpy.context.view_layer.objects.active = road

# export FBX
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
