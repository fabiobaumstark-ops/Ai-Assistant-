"""
Porsche 911 GT3 RS (992) - prozedurales 3D-Modell fuer Blender (bpy)
=====================================================================

Benutzung
---------
  A) In Blender:  Tab "Scripting" -> Datei oeffnen -> "Skript ausfuehren" (Alt+P)
  B) Ohne Oberflaeche:
         blender -b -P porsche_gt3_rs.py                     -> speichert porsche_gt3_rs.blend
         blender -b -P porsche_gt3_rs.py -- --render         -> zusaetzlich porsche_gt3_rs.png
         blender -b -P porsche_gt3_rs.py -- --render --fast  -> schnelle Vorschau

Farbe aendern: BODY_COLOR unten (RGB, 0..1).
Koordinaten: Laenge = X (Front bei +X), Breite = Y, Hoehe = Z, Einheit = Meter.
Massstab: ca. 4,57 m lang, 1,95 m breit, 1,32 m hoch, Radstand 2,45 m.
Die Karosserie wird aus Querschnitten (Superellipsen) geformt - keine Bilder noetig.
"""
import math
import os
import random
import sys
from bisect import bisect_right

import bpy
import bmesh
from mathutils import Euler, Vector

random.seed(3)
REAR = '--rear' in sys.argv

BODY_COLOR = (0.9, 0.48, 0.0)     # Racing Yellow (Guards Red: (0.55, 0.01, 0.01), Shark Blue: (0.02, 0.10, 0.35))

# --------------------------------------------------------------------------
# Szene leeren
# --------------------------------------------------------------------------
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
    for d in list(coll):
        coll.remove(d)
scene = bpy.context.scene
COLL = scene.collection


# --------------------------------------------------------------------------
# Geometrie-Helfer
# --------------------------------------------------------------------------
def obj(name, mesh, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, parent=None, bevel=0.0):
    o = bpy.data.objects.new(name, mesh)
    COLL.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    if mat is not None:
        o.data.materials.append(mat)
    if parent is not None:
        o.parent = parent
    if bevel:
        m = o.modifiers.new("Bevel", 'BEVEL')
        m.width = bevel
        m.segments = 3
        m.limit_method = 'ANGLE'
    return o


def mesh_box(sx, sy, sz):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    me = bpy.data.meshes.new("box")
    bm.to_mesh(me)
    bm.free()
    return me


def mesh_cyl(r, h, seg=32, r2=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r,
                          radius2=r if r2 is None else r2, depth=h)
    me = bpy.data.meshes.new("cyl")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    return me


def mesh_sphere(sx, sy, sz, sub=3):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    me = bpy.data.meshes.new("sph")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    return me


def box(name, loc, size, mat, rot=(0, 0, 0), parent=None, bevel=0.0):
    return obj(name, mesh_box(*size), loc, rot, mat, parent, bevel)


def cyl(name, loc, r, h, mat, rot=(0, 0, 0), parent=None, seg=32, r2=None):
    return obj(name, mesh_cyl(r, h, seg, r2), loc, rot, mat, parent)


def ellipsoid(name, loc, size, mat, rot=(0, 0, 0), parent=None):
    return obj(name, mesh_sphere(*size), loc, rot, mat, parent)


def empty(name, loc=(0, 0, 0), rot=(0, 0, 0), parent=None):
    o = bpy.data.objects.new(name, None)
    COLL.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    if parent:
        o.parent = parent
    return o


def tube(name, p0, p1, r, mat, seg=12):
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    o = cyl(name, tuple((p0 + p1) / 2), r, d.length, mat, seg=seg)
    for p in o.data.polygons:
        p.use_smooth = len(p.vertices) == 4
    o.rotation_mode = 'QUATERNION'
    o.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    return o


def lathe(profile, seg=64, name="lathe"):
    """Rotationskoerper um die Y-Achse. profile = geschlossene Liste (radius, y)."""
    bm = bmesh.new()
    rings = []
    for (r, y) in profile:
        rings.append([bm.verts.new((r * math.cos(2 * math.pi * k / seg), y,
                                    r * math.sin(2 * math.pi * k / seg))) for k in range(seg)])
    n = len(rings)
    for i in range(n):
        a, b = rings[i], rings[(i + 1) % n]
        for k in range(seg):
            k2 = (k + 1) % seg
            try:
                bm.faces.new((a[k], a[k2], b[k2], b[k]))
            except ValueError:
                pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    return me


def cut(target, cutters):
    if not isinstance(cutters, (list, tuple)):
        cutters = [cutters]
    for i, c in enumerate(cutters):
        m = target.modifiers.new(f"cut{i}", 'BOOLEAN')
        m.operation = 'DIFFERENCE'
        m.solver = 'EXACT'
        m.object = c
        m.material_mode = 'TRANSFER'
        with bpy.context.temp_override(object=target, active_object=target):
            bpy.ops.object.modifier_apply(modifier=m.name)
    for c in cutters:
        bpy.data.objects.remove(c, do_unlink=True)


# --------------------------------------------------------------------------
# Materialien
# --------------------------------------------------------------------------
def _new(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    return m, m.node_tree, m.node_tree.nodes["Principled BSDF"]


def mat(name, color, rough=0.5, metal=0.0, **kw):
    m, nt, b = _new(name)
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    for k, v in kw.items():
        b.inputs[k.replace("_", " ")].default_value = v
    return m


def mat_emit(name, color, strength):
    m, nt, b = _new(name)
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Emission Color"].default_value = (*color, 1)
    b.inputs["Emission Strength"].default_value = strength
    return m


def mat_carbon(name="Carbon"):
    m, nt, b = _new(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    ch = nt.nodes.new("ShaderNodeTexChecker")
    ch.inputs["Scale"].default_value = 260
    ch.inputs["Color1"].default_value = (0.012, 0.012, 0.014, 1)
    ch.inputs["Color2"].default_value = (0.05, 0.05, 0.055, 1)
    nt.links.new(tc.outputs["Object"], ch.inputs["Vector"])
    nt.links.new(ch.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.22
    b.inputs["Coat Weight"].default_value = 1.0
    b.inputs["Coat Roughness"].default_value = 0.03
    return m


def mat_paint(name, color):
    m = mat(name, color, rough=0.3, metal=0.15, Coat_Weight=1.0, Coat_Roughness=0.02)
    return m


MP = mat_paint("Lack", BODY_COLOR)
MB = mat("Schwarz matt", (0.012, 0.012, 0.013), rough=0.55)
MK = mat_carbon()
MG = mat("Getoentes Glas", (0.004, 0.006, 0.008), rough=0.03, metal=0.0, Specular_IOR_Level=1.0)
MRUB = mat("Gummi", (0.015, 0.015, 0.016), rough=0.85)
MRIM = mat("Felge", (0.02, 0.02, 0.022), rough=0.28, metal=1.0)
MRIM2 = mat("Felge poliert", (0.7, 0.7, 0.72), rough=0.2, metal=1.0)
MDISC = mat("Bremsscheibe", (0.35, 0.35, 0.37), rough=0.4, metal=1.0)
MCAL = mat("Bremssattel", (0.75, 0.02, 0.02), rough=0.3, Coat_Weight=1.0)
MCHR = mat("Chrom", (0.8, 0.8, 0.82), rough=0.08, metal=1.0)
MEXH = mat("Auspuff", (0.45, 0.42, 0.40), rough=0.25, metal=1.0)
MHL = mat("Scheinwerferglas", (0.08, 0.09, 0.10), rough=0.03, metal=0.6)
MBG = mat("Schwarz glaenzend", (0.01, 0.01, 0.012), rough=0.2)
MDRL = mat_emit("LED weiss", (1.0, 0.98, 0.9), 25.0)
MTAIL = mat_emit("Ruecklicht", (1.0, 0.02, 0.01), 12.0)
MPLATE = mat("Kennzeichen", (0.9, 0.9, 0.85), rough=0.5)
MFLOOR = mat("Boden", (0.09, 0.09, 0.10), rough=0.18)


# --------------------------------------------------------------------------
# Karosserieprofile (x von hinten nach vorn)
# --------------------------------------------------------------------------
def interp(xs, ys, x):
    """Kubische Hermite-Interpolation (Catmull-Rom-Tangenten)."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect_right(xs, x) - 1
    x0, x1 = xs[i], xs[i + 1]
    t = (x - x0) / (x1 - x0)

    def slope(k):
        a, b = max(k - 1, 0), min(k + 1, len(xs) - 1)
        return (ys[b] - ys[a]) / (xs[b] - xs[a])

    h = x1 - x0
    m0, m1 = slope(i) * h, slope(i + 1) * h
    t2, t3 = t * t, t ** 3
    return ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * m0 +
            (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * m1)


XS = [-2.36, -2.30, -2.20, -1.80, -1.20, -0.50, 0.30, 1.00, 1.40, 1.90, 2.20, 2.30, 2.33]
ZT = [0.66, 0.78, 0.90, 1.00, 1.00, 0.95, 0.92, 0.85, 0.76, 0.60, 0.48, 0.41, 0.36]
ZB = [0.36, 0.32, 0.27, 0.19, 0.16, 0.15, 0.14, 0.13, 0.12, 0.10, 0.10, 0.12, 0.22]
WW = [0.50, 0.70, 0.87, 0.97, 0.99, 0.95, 0.93, 0.95, 0.94, 0.82, 0.64, 0.50, 0.32]
N_LOW = 3.2

CX = [-1.95, -1.70, -1.40, -1.00, -0.60, -0.20, 0.20, 0.50, 0.75, 1.00, 1.20]
CT = [0.90, 1.03, 1.15, 1.27, 1.31, 1.31, 1.27, 1.18, 1.07, 0.96, 0.85]
CW = [0.58, 0.66, 0.72, 0.75, 0.77, 0.77, 0.77, 0.74, 0.70, 0.65, 0.58]
CB = 0.76
N_CAB = 2.6

X_FRONT, X_REAR = 1.35, -1.10
R_FRONT, R_REAR = 0.35, 0.367
TRACK_F, TRACK_R = 0.795, 0.815


def low(x):
    return interp(XS, ZT, x), interp(XS, ZB, x), interp(XS, WW, x)


def body_z(x, y):
    zt, zb, w = low(x)
    zm, hh = (zt + zb) / 2, (zt - zb) / 2
    f = min(abs(y) / w, 0.999)
    return zm + hh * (1 - f ** N_LOW) ** (1 / N_LOW)


def body_y(x, z):
    zt, zb, w = low(x)
    zm, hh = (zt + zb) / 2, (zt - zb) / 2
    f = min(abs(z - zm) / hh, 0.999)
    return w * (1 - f ** N_LOW) ** (1 / N_LOW)


def slope_angle(x):
    return -math.atan((body_z(x + 0.02, 0) - body_z(x - 0.02, 0)) / 0.04)


def sgnpow(v, p):
    return math.copysign(abs(v) ** p, v)


# --------------------------------------------------------------------------
# Loft-Koerper aus Querschnitten
# --------------------------------------------------------------------------
def loft(stations, ring_fn, nring, name, closed_ring=True, poly_mat=None):
    bm = bmesh.new()
    rings = []
    for x in stations:
        rings.append([bm.verts.new(ring_fn(x, k)) for k in range(nring)])
    for i in range(len(rings) - 1):
        a, b = rings[i], rings[i + 1]
        for k in range(nring):
            k2 = (k + 1) % nring
            if not closed_ring and k2 == 0:
                pass
            bm.faces.new((a[k], b[k], b[k2], a[k2]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def stations(x0, x1, n):
    return [x0 + (x1 - x0) * (1 - math.cos(math.pi * i / (n - 1))) / 2 for i in range(n)]


def build_body():
    NR = 48

    def ring_low(x, k):
        zt, zb, w = low(x)
        a = 2 * math.pi * k / NR
        return (x, w * sgnpow(math.cos(a), 2 / N_LOW),
                (zt + zb) / 2 + (zt - zb) / 2 * sgnpow(math.sin(a), 2 / N_LOW))

    me = loft(stations(XS[0], XS[-1], 90), ring_low, NR, "Karosserie")
    me.materials.append(MP)
    me.materials.append(MB)
    for p in me.polygons:
        p.use_smooth = True
        if p.normal.z < -0.55:
            p.material_index = 1
    body = obj("Karosserie", me)

    # Radhaeuser
    cutters = []
    black = MB
    for (xw, R) in ((X_FRONT, R_FRONT), (X_REAR, R_REAR)):
        for sgn in (1, -1):
            c = cyl("cut", (xw, sgn * 0.8, R), R + 0.06, 0.75, black, (math.radians(90), 0, 0), seg=64)
            cutters.append(c)
    cut(body, cutters)

    # Unterboden schwarz
    # Kabine (Glashaus)
    NC = 40

    def ring_cab(x, k):
        a = math.pi * k / (NC - 1)
        w = interp(CX, CW, x)
        zt = interp(CX, CT, x)
        return (x, w * sgnpow(math.cos(a), 2 / N_CAB),
                CB + (zt - CB) * abs(math.sin(a)) ** (2 / N_CAB))

    me = loft(stations(CX[0], CX[-1], 70), ring_cab, NC, "Kabine")
    me.materials.append(MG)     # 0 Glas
    me.materials.append(MK)     # 1 Dach Carbon
    me.materials.append(MP)     # 2 Saeulen / Lack
    for p in me.polygons:
        p.use_smooth = True
        c = p.center
        x, nz = c.x, p.normal.z
        idx = 0
        if nz > 0.6 and -1.25 < x < 0.35:
            idx = 1
        elif abs(p.normal.y) > 0.5 and (x < -1.35 or x > 0.95):
            idx = 2
        elif abs(p.normal.y) > 0.5 and abs(x + 0.10) < 0.05:
            idx = 2                       # B-Saeule
        elif nz < 0.02 and c.z < CB + 0.03:
            idx = 2
        p.material_index = idx
    cab = obj("Kabine", me)
    try:
        with bpy.context.temp_override(object=body, active_object=body, selected_objects=[body]):
            bpy.ops.object.shade_auto_smooth(angle=math.radians(50))
    except Exception:
        pass
    return body, cab


# --------------------------------------------------------------------------
# Auflagen (Patches) auf der Karosserieoberflaeche
# --------------------------------------------------------------------------
def side_patch(name, x0, x1, z0, z1, off, m, nx=8, nz=8):
    for sgn in (1, -1):
        bm = bmesh.new()
        g = []
        for i in range(nx + 1):
            x = x0 + (x1 - x0) * i / nx
            row = []
            for j in range(nz + 1):
                z = z0 + (z1 - z0) * j / nz
                row.append(bm.verts.new((x, sgn * (body_y(x, z) + off), z)))
            g.append(row)
        for i in range(nx):
            for j in range(nz):
                q = (g[i][j], g[i + 1][j], g[i + 1][j + 1], g[i][j + 1])
                bm.faces.new(q if sgn < 0 else q[::-1])
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        for p in me.polygons:
            p.use_smooth = True
        obj(name, me, mat=m)


def top_patch(name, x0, x1, y0, y1, off, m, nx=8, ny=6, mirror=True):
    for sgn in ((1, -1) if mirror else (1,)):
        bm = bmesh.new()
        g = []
        for i in range(nx + 1):
            x = x0 + (x1 - x0) * i / nx
            row = []
            for j in range(ny + 1):
                y = y0 + (y1 - y0) * j / ny
                row.append(bm.verts.new((x, sgn * y, body_z(x, y) + off)))
            g.append(row)
        for i in range(nx):
            for j in range(ny):
                q = (g[i][j], g[i + 1][j], g[i + 1][j + 1], g[i][j + 1])
                bm.faces.new(q if sgn > 0 else q[::-1])
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        obj(name, me, mat=m)


# --------------------------------------------------------------------------
# Raeder
# --------------------------------------------------------------------------
def wheel(name, loc, R, hw, rr, outward=1):
    root = empty(name, loc, (0, 0, 0 if outward > 0 else math.pi))
    # Reifen
    prof = [(rr, -hw * 0.8), (rr + 0.012, -hw * 0.9), (R - 0.05, -hw), (R - 0.015, -hw * 0.88),
            (R, -hw * 0.5), (R, hw * 0.5), (R - 0.015, hw * 0.88), (R - 0.05, hw),
            (rr + 0.012, hw * 0.9), (rr, hw * 0.8)]
    obj("Reifen", lathe(prof, 72), (0, 0, 0), (0, 0, 0), MRUB, root)
    # Felgenbett
    fr = [(rr + 0.006, hw * 0.86), (rr - 0.02, hw * 0.88), (rr - 0.045, hw * 0.62), (rr - 0.05, -hw * 0.6),
          (rr + 0.004, -hw * 0.8)]
    obj("Felgenbett", lathe(fr, 72), (0, 0, 0), (0, 0, 0), MRIM, root)
    obj("Felgenring", lathe([(rr + 0.008, hw * 0.83), (rr + 0.008, hw * 0.9), (rr - 0.015, hw * 0.9)], 72),
        (0, 0, 0), (0, 0, 0), MRIM2, root)
    # Speichen (10 Doppelspeichen)
    ys = hw * 0.72
    for i in range(10):
        th = 2 * math.pi * i / 10
        for d in (-0.075, 0.075):
            a = th + d
            rl = rr - 0.075
            rc = 0.06 + rl / 2
            box("Speiche", (rc * math.cos(a), ys, -rc * math.sin(a)), (rl, 0.03, 0.028), MRIM,
                (0, a, 0), root, bevel=0.004)
    cyl("Nabe", (0, hw * 0.72, 0), 0.075, 0.05, MRIM, (math.radians(90), 0, 0), root)
    cyl("Zentralverschluss", (0, hw * 0.78, 0), 0.042, 0.05, MRIM2, (math.radians(90), 0, 0), root, seg=6)
    # Bremse
    cyl("Bremsscheibe", (0, hw * 0.25, 0), rr * 0.78, 0.035, MDISC, (math.radians(90), 0, 0), root, seg=64)
    cyl("Bremstopf", (0, hw * 0.4, 0), rr * 0.42, 0.05, MB, (math.radians(90), 0, 0), root, seg=32)
    a = math.radians(50)
    rc = rr * 0.7
    box("Bremssattel", (rc * math.cos(a), hw * 0.28, rc * math.sin(a)), (0.14, 0.07, 0.10), MCAL,
        (0, -a + math.pi / 2, 0), root, bevel=0.01)
    return root


# --------------------------------------------------------------------------
# Heckfluegel
# --------------------------------------------------------------------------
def build_wing():
    chord, span, tmax = 0.34, 1.78, 0.06
    pts = []
    n = 24
    up = [(u, tmax * 5 * (0.2969 * math.sqrt(u) - 0.1260 * u - 0.3516 * u * u + 0.2843 * u ** 3
                           - 0.1015 * u ** 4) * 1.0 - 0.05 * math.sin(math.pi * u))
          for u in [i / n for i in range(n + 1)]]
    lo = [(u, -tmax * 5 * (0.2969 * math.sqrt(u) - 0.1260 * u - 0.3516 * u * u + 0.2843 * u ** 3
                            - 0.1015 * u ** 4) * 1.0 - 0.05 * math.sin(math.pi * u))
          for u in [i / n for i in range(1, n)][::-1]]
    poly = [(-u * chord, z) for u, z in up] + [(-u * chord, z) for u, z in lo]
    bm = bmesh.new()
    a = [bm.verts.new((px, -span / 2, pz)) for px, pz in poly]
    b = [bm.verts.new((px, span / 2, pz)) for px, pz in poly]
    bm.faces.new(a[::-1])
    bm.faces.new(b)
    for i in range(len(poly)):
        j = (i + 1) % len(poly)
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("Fluegel")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    xle, zc = -2.13, 1.44
    wing = obj("Heckfluegel", me, (xle, 0, zc), (0, math.radians(9), 0), MK)
    # Endplatten
    for sgn in (1, -1):
        box("Endplatte", (xle - chord / 2 - 0.02, sgn * (span / 2 + 0.01), zc), (0.46, 0.02, 0.24), MK,
            (0, math.radians(9), 0), bevel=0.006)
        box("Endplatte Lack", (xle - chord / 2 - 0.02, sgn * (span / 2 + 0.022), zc), (0.30, 0.004, 0.11), MP,
            (0, math.radians(9), 0))
        # Swan-Neck-Streben
        pts = [(-1.88, 0.5, 1.00), (-1.95, 0.5, 1.12), (-2.05, 0.5, 1.30), (-2.13, 0.5, 1.43), (-2.22, 0.5, 1.52),
               (-2.30, 0.5, 1.53)]
        # Kurve als Bezier-aehnliche Polylinie
        pp = []
        p0, p1, p2, p3 = Vector((-1.86, 0, 0.98)), Vector((-1.90, 0, 1.40)), Vector((-2.15, 0, 1.62)), Vector((-2.28, 0, 1.53))
        for i in range(7):
            t = i / 6
            q = (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3
            pp.append(q)
        for i in range(6):
            a_ = pp[i] + Vector((0, sgn * 0.52, 0))
            b_ = pp[i + 1] + Vector((0, sgn * 0.52, 0))
            tube("Strebe", a_, b_, 0.03, MBG, seg=16)
            ellipsoid("Gelenk", tuple(b_), (0.031, 0.031, 0.031), MBG)


# --------------------------------------------------------------------------
# Details
# --------------------------------------------------------------------------
def build_details():
    # Front: Splitter, Lufteinlaesse
    box("Frontsplitter", (2.14, 0, 0.085), (0.30, 1.62, 0.02), MK, bevel=0.006)
    box("Splitter Lippe", (2.28, 0, 0.10), (0.02, 1.3, 0.04), MK, bevel=0.006)
    box("Frontgrill Mitte", (2.27, 0, 0.30), (0.07, 0.95, 0.15), MB, bevel=0.02)
    for sgn in (1, -1):
        box("Frontgrill Seite", (2.13, sgn * 0.62, 0.28), (0.08, 0.42, 0.14), MB,
            (0, 0, sgn * math.radians(-18)), bevel=0.02)
        box("Splitter Flosse", (2.05, sgn * 0.90, 0.13), (0.42, 0.02, 0.09), MK, (0, 0, sgn * 0.12))
    box("Kuehlerrippe", (2.27, 0, 0.30), (0.075, 0.95, 0.012), MEXH)
    # Scheinwerfer
    for sgn in (1, -1):
        x, y = 1.93, sgn * 0.60
        z = body_z(x, abs(y))
        ang = slope_angle(x)
        ellipsoid("Kotfluegelbeule", (x - 0.02, y, z - 0.035), (0.30, 0.20, 0.05), MP, (0, ang, 0))
        ellipsoid("Scheinwerfer", (x, y, z + 0.03), (0.20, 0.17, 0.05), MHL, (0, ang, 0))
        box("LED Tagfahrlicht", (x + 0.05, y, z + 0.075), (0.14, 0.012, 0.006), MDRL, (0, ang, 0))
        box("LED Tagfahrlicht", (x + 0.02, y, z + 0.075), (0.16, 0.012, 0.006), MDRL, (0, ang, 0.0))
        ellipsoid("Scheinwerfer Linse", (x + 0.06, y - sgn * 0.05, z + 0.055), (0.06, 0.06, 0.025), MDRL,
                  (0, ang, 0))
        # Blinker
        ellipsoid("Blinker", (x + 0.02, y + sgn * 0.13, z + 0.03), (0.05, 0.04, 0.025), MDRL, (0, ang, 0))
    # Fronthaube: Entlueftung
    top_patch("Haubenschlitz", 1.15, 1.6, 0.16, 0.34, 0.006, MB, 6, 3)
    top_patch("Haubenschlitz 2", 1.15, 1.6, 0.42, 0.52, 0.006, MB, 6, 3)
    for k in (0.18, 0.22, 0.26, 0.30):
        pass
    box("Haubenfuge Mitte", (1.75, 0, body_z(1.75, 0) + 0.002), (0.012, 0.012, 0.004), MB)
    # Fugen (Tuer)
    side_patch("Tuerfuge vorn", 0.80, 0.812, 0.34, 0.90, 0.004, MB, 1, 10)
    side_patch("Tuerfuge hinten", -0.12, -0.108, 0.30, 0.92, 0.004, MB, 1, 10)
    side_patch("Tuerfuge oben", -0.12, 0.80, 0.900, 0.905, 0.004, MB, 8, 1)
    # Seitenschweller & Lufteinlass Hinterrad
    side_patch("Schweller", -0.35, 0.95, 0.13, 0.27, 0.006, MB, 10, 3)
    side_patch("Lufteinlass hinten", -0.62, -0.18, 0.46, 0.80, 0.008, MB, 8, 6)
    side_patch("Lufteinlass Rippe", -0.62, -0.18, 0.63, 0.645, 0.012, MK, 8, 1)
    # Tuergriffe
    side_patch("Tuergriff", 0.05, 0.32, 0.82, 0.85, 0.008, MP, 4, 1)
    # Seitenspiegel
    for sgn in (1, -1):
        tube("Spiegelstiel", (0.70, sgn * 0.70, 0.96), (0.62, sgn * 0.90, 1.00), 0.016, MB)
        ellipsoid("Spiegel", (0.60, sgn * 0.95, 1.02), (0.09, 0.07, 0.05), MK, (0, 0, sgn * -0.2))
        ellipsoid("Spiegel Lack", (0.60, sgn * 0.95, 1.05), (0.075, 0.055, 0.02), MP, (0, 0, sgn * -0.2))
    # Heck: Motorhaube mit Luftgitter
    top_patch("Motorhaubengitter", -1.98, -1.6, 0.20, 0.55, 0.006, MB, 10, 6)
    for i in range(6):
        top_patch("Gitterrippe", -1.98 + i * 0.065, -1.98 + i * 0.065 + 0.012, 0.20, 0.55, 0.014, MK, 1, 2)
    # Rueck- / Diffusor
    box("Heckband schwarz", (-2.285, 0, 0.775), (0.05, 1.42, 0.085), MB, (0, math.radians(-8), 0), bevel=0.01)
    box("Ruecklicht LED", (-2.305, 0, 0.775), (0.03, 1.34, 0.04), MTAIL, (0, math.radians(-8), 0), bevel=0.005)
    box("Diffusor", (-2.22, 0, 0.27), (0.25, 1.4, 0.03), MB, (0, math.radians(-12), 0))
    for i in range(-4, 5):
        box("Diffusorfinne", (-2.24, i * 0.15, 0.25), (0.22, 0.012, 0.07), MB, (0, math.radians(-12), 0))
    for sgn in (1, -1):
        cyl("Auspuff", (-2.34, sgn * 0.12, 0.33), 0.058, 0.25, MEXH, (0, math.radians(90), 0), seg=32)
        cyl("Auspuff innen", (-2.42, sgn * 0.12, 0.33), 0.046, 0.05, MB, (0, math.radians(90), 0), seg=32)
    box("Kennzeichen", (-2.32, 0, 0.55), (0.02, 0.5, 0.11), MPLATE)
    # Radhaus-Verkleidung
    for (xw, R) in ((X_FRONT, R_FRONT), (X_REAR, R_REAR)):
        for sgn in (1, -1):
            cyl("Radhaus", (xw, sgn * 0.47, R), R + 0.055, 0.02, MB, (math.radians(90), 0, 0), seg=64)
    # Unterboden
    box("Unterboden", (0, 0, 0.125), (4.1, 1.5, 0.02), MB)


def build_wheels():
    hwf, hwr = 0.145, 0.175
    wheel("Rad VR", (X_FRONT, TRACK_F, R_FRONT), R_FRONT, hwf, 0.254, 1)
    wheel("Rad VL", (X_FRONT, -TRACK_F, R_FRONT), R_FRONT, hwf, 0.254, -1)
    wheel("Rad HR", (X_REAR, TRACK_R, R_REAR), R_REAR, hwr, 0.267, 1)
    wheel("Rad HL", (X_REAR, -TRACK_R, R_REAR), R_REAR, hwr, 0.267, -1)


# --------------------------------------------------------------------------
# Studio, Licht, Kamera
# --------------------------------------------------------------------------
def area_light(name, loc, size, size_y, energy, target, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.shape = 'RECTANGLE'
    ld.size, ld.size_y = size, size_y
    ld.energy = energy
    ld.color = color
    lo = bpy.data.objects.new(name, ld)
    COLL.objects.link(lo)
    lo.location = loc
    c = lo.constraints.new('TRACK_TO')
    c.target = target
    c.track_axis = 'TRACK_NEGATIVE_Z'
    c.up_axis = 'UP_Y'
    return lo


def setup_studio(fast):
    # Boden
    box("Studioboden", (0, 0, -0.005), (60, 60, 0.01), MFLOOR)

    world = bpy.data.worlds.new("Studio")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes["Background"]
    bg.inputs["Color"].default_value = (0.35, 0.37, 0.40, 1)
    bg.inputs["Strength"].default_value = 0.35

    tgt = empty("Ziel", (0, 0, 0.5))
    area_light("Key", (5.5, -6.0, 5.0), 5, 2.5, 1300, tgt)
    area_light("Fill", (-5.0, 5.5, 3.0), 4, 3, 500, tgt, (0.85, 0.92, 1.0))
    area_light("Oben", (0, 0, 5.5), 6, 1.8, 900, tgt)
    area_light("Rim", (-6.0, -4.0, 2.5), 2, 4, 700, tgt, (1.0, 0.95, 0.9))
    area_light("Front", (7.0, 3.0, 2.0), 3, 3, 450, tgt)

    cd = bpy.data.cameras.new("Kamera")
    cd.lens = 50
    cam = bpy.data.objects.new("Kamera", cd)
    COLL.objects.link(cam)
    cam.location = (-6.4, -5.4, 1.7) if REAR else (6.6, -5.6, 1.35)
    c = cam.constraints.new('TRACK_TO')
    c.target = tgt
    c.track_axis = 'TRACK_NEGATIVE_Z'
    c.up_axis = 'UP_Y'
    scene.camera = cam

    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 32 if fast else 96
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1280 if fast else 1920
    scene.render.resolution_y = 720 if fast else 1080
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.exposure = -0.6


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    fast = "--fast" in argv
    build_body()
    build_details()
    build_wing()
    build_wheels()
    setup_studio(fast)
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        here = os.path.dirname(bpy.data.filepath) or os.getcwd()
    if bpy.app.background or "--save" in argv:
        path = os.path.join(here, "porsche_gt3_rs.blend")
        bpy.ops.wm.save_as_mainfile(filepath=path)
        print("Gespeichert:", path)
    if "--render" in argv:
        scene.render.filepath = os.path.join(here, "porsche_gt3_rs_hinten.png" if REAR else "porsche_gt3_rs.png")
        bpy.ops.render.render(write_still=True)
        print("Render:", scene.render.filepath)


main()
