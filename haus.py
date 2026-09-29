"""
Sehr detailliertes Haus in Blender (bpy)
=========================================

Benutzung
---------
  A) In Blender:  Tab "Scripting" -> Datei oeffnen -> "Skript ausfuehren" (Alt+P)
  B) Ohne Oberflaeche:
         blender -b -P haus.py                      -> baut Szene, speichert haus.blend
         blender -b -P haus.py -- --render          -> zusaetzlich Bild haus_render.png
         blender -b -P haus.py -- --render --fast   -> schnelle Vorschau (wenig Samples)

Was gebaut wird
---------------
Zweistoeckiges Backsteinhaus mit Satteldach, Gauben, Kamin, Vordach mit Saeulen,
Garage, Fenster mit Rahmen/Sprossen/Fensterbank/Klappladen/Blumenkasten,
Haustuer mit Kassetten, Dachrinnen, Fallrohren, Eckquadern, Gesimsband,
Einrichtung, Garten mit Zaun, Baeumen, Buschwerk, Blumenbeeten, Weg, Einfahrt,
Strasse, Briefkasten, Laternen und Himmel (Nishita Sky). Alle Materialien sind
prozedural (keine externen Bilder noetig).

Koordinaten: Haus 10 m (x) x 8 m (y), Vorderseite zeigt nach -Y, Einheit = Meter.
"""
import math
import random
import sys

import bpy
import bmesh
from mathutils import Euler, Vector

random.seed(7)

# --------------------------------------------------------------------------
# Massangaben
# --------------------------------------------------------------------------
HW, HD = 5.0, 4.0          # halbe Hausbreite (x) / halbe Haustiefe (y)
WT = 0.30                  # Wanddicke
Z0 = 0.5                   # Oberkante Sockel = Boden EG
ZW = 6.5                   # Oberkante Aussenwand
PITCH = math.radians(35)   # Dachneigung
RIDGE = ZW + HD * math.tan(PITCH)
OVER = 0.6                 # Dachueberstand


# --------------------------------------------------------------------------
# Szene aufraeumen
# --------------------------------------------------------------------------
def clear_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.curves, bpy.data.lights,
                 bpy.data.cameras):
        for d in list(coll):
            coll.remove(d)


clear_scene()
scene = bpy.context.scene
COLL = scene.collection


# --------------------------------------------------------------------------
# Geometrie-Helfer
# --------------------------------------------------------------------------
def _link(o):
    COLL.objects.link(o)
    return o


def mesh_box(sx, sy, sz):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    me = bpy.data.meshes.new("box")
    bm.to_mesh(me)
    bm.free()
    return me


def mesh_cyl(r, h, seg=24, r2=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r,
                          radius2=r if r2 is None else r2, depth=h)
    me = bpy.data.meshes.new("cyl")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    return me


def mesh_sphere(r, sub=2, lumpy=0.0, squash=1.0):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=r)
    for v in bm.verts:
        v.co.z *= squash
        if lumpy:
            v.co *= 1.0 + random.uniform(-lumpy, lumpy)
    me = bpy.data.meshes.new("sph")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    return me


def mesh_prism(pts, thick):
    """Polygon (Liste von (y, z)) in der YZ-Ebene, entlang -X um `thick` extrudiert."""
    bm = bmesh.new()
    a = [bm.verts.new((0, y, z)) for y, z in pts]
    b = [bm.verts.new((-thick, y, z)) for y, z in pts]
    bm.faces.new(a)
    bm.faces.new(b[::-1])
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("prism")
    bm.to_mesh(me)
    bm.free()
    return me


def obj(name, mesh, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, parent=None, bevel=0.0):
    o = bpy.data.objects.new(name, mesh)
    _link(o)
    o.location = loc
    o.rotation_euler = rot
    if mat is not None:
        o.data.materials.append(mat)
    if parent is not None:
        o.parent = parent
    if bevel:
        m = o.modifiers.new("Bevel", 'BEVEL')
        m.width = bevel
        m.segments = 2
        m.limit_method = 'ANGLE'
    return o


def box(name, loc, size, mat, rot=(0, 0, 0), parent=None, bevel=0.0):
    return obj(name, mesh_box(*size), loc, rot, mat, parent, bevel)


def cyl(name, loc, r, h, mat, rot=(0, 0, 0), parent=None, seg=24, r2=None):
    return obj(name, mesh_cyl(r, h, seg, r2), loc, rot, mat, parent)


def sphere(name, loc, r, mat, parent=None, sub=2, lumpy=0.0, squash=1.0):
    return obj(name, mesh_sphere(r, sub, lumpy, squash), loc, (0, 0, 0), mat, parent)


def empty(name, loc=(0, 0, 0), rot=(0, 0, 0), parent=None):
    o = bpy.data.objects.new(name, None)
    _link(o)
    o.location = loc
    o.rotation_euler = rot
    if parent:
        o.parent = parent
    return o


def cut(target, cutters):
    """Zieht die Cutter-Objekte per Boolean (Exact) vom Zielobjekt ab und loescht sie."""
    if not isinstance(cutters, (list, tuple)):
        cutters = [cutters]
    bpy.context.view_layer.objects.active = target
    for i, c in enumerate(cutters):
        m = target.modifiers.new(f"cut{i}", 'BOOLEAN')
        m.operation = 'DIFFERENCE'
        m.solver = 'EXACT'
        m.object = c
        with bpy.context.temp_override(object=target, active_object=target):
            bpy.ops.object.modifier_apply(modifier=m.name)
    for c in cutters:
        bpy.data.objects.remove(c, do_unlink=True)


# --------------------------------------------------------------------------
# Materialien (alles prozedural)
# --------------------------------------------------------------------------
def _new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    return m, nt, bsdf


def _set(bsdf, **kw):
    names = {"base": "Base Color", "rough": "Roughness", "metal": "Metallic",
             "trans": "Transmission Weight", "ior": "IOR", "emit": "Emission Color",
             "emit_s": "Emission Strength", "alpha": "Alpha", "spec": "Specular IOR Level"}
    for k, v in kw.items():
        bsdf.inputs[names[k]].default_value = v


def mat(name, color, rough=0.5, metal=0.0, **kw):
    m, nt, b = _new_mat(name)
    _set(b, base=(*color, 1), rough=rough, metal=metal, **kw)
    return m


def mat_glass(name="Glas"):
    m, nt, b = _new_mat(name)
    _set(b, base=(0.85, 0.95, 1.0, 1), rough=0.0, trans=1.0, ior=1.45)
    return m


def mat_emit(name, color, strength):
    m, nt, b = _new_mat(name)
    _set(b, base=(*color, 1), emit=(*color, 1), emit_s=strength, rough=0.4)
    return m


def _bump(nt, b, height_socket, strength, dist, invert=False):
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = dist
    bump.invert = invert
    nt.links.new(height_socket, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])


def mat_noise(name, c1, c2, scale=8.0, rough=0.8, bump=0.3, dist=0.02, detail=8.0):
    """Zweifarbig verrauschte Oberflaeche (Putz, Rasen, Beton, Laub ...)."""
    m, nt, b = _new_mat(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*c1, 1)
    ramp.color_ramp.elements[1].color = (*c2, 1)
    nt.links.new(n.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    _set(b, rough=rough)
    _bump(nt, b, n.outputs["Fac"], bump, dist)
    return m


def mat_brick(name, c1, c2, mortar, bw=0.24, rh=0.075, msize=0.008,
              triplanar=True, rough=0.85, bump=0.6):
    """Ziegel-/Ziegelmuster.  triplanar=True: Muster in Weltkoordinaten auf allen
    senkrechten Waenden (XZ- und YZ-Ebene); sonst Objektkoordinaten (z. B. Dachziegel)."""
    m, nt, b = _new_mat(name)
    N = nt.nodes

    def brick(vec_socket):
        t = N.new("ShaderNodeTexBrick")
        t.offset = 0.5
        t.inputs["Color1"].default_value = (*c1, 1)
        t.inputs["Color2"].default_value = (*c2, 1)
        t.inputs["Mortar"].default_value = (*mortar, 1)
        t.inputs["Scale"].default_value = 1.0
        t.inputs["Mortar Size"].default_value = msize
        t.inputs["Mortar Smooth"].default_value = 0.1
        t.inputs["Brick Width"].default_value = bw
        t.inputs["Row Height"].default_value = rh
        nt.links.new(vec_socket, t.inputs["Vector"])
        return t

    if not triplanar:
        tc = N.new("ShaderNodeTexCoord")
        t = brick(tc.outputs["Object"])
        nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
        _bump(nt, b, t.outputs["Fac"], bump, 0.02)
        _set(b, rough=rough)
        return m

    geo = N.new("ShaderNodeNewGeometry")
    sp = N.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sp.inputs["Vector"])
    cxz = N.new("ShaderNodeCombineXYZ")
    cyz = N.new("ShaderNodeCombineXYZ")
    nt.links.new(sp.outputs["X"], cxz.inputs["X"])
    nt.links.new(sp.outputs["Z"], cxz.inputs["Y"])
    nt.links.new(sp.outputs["Y"], cyz.inputs["X"])
    nt.links.new(sp.outputs["Z"], cyz.inputs["Y"])
    ta, tb = brick(cxz.outputs["Vector"]), brick(cyz.outputs["Vector"])

    ns = N.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], ns.inputs["Vector"])
    ab = N.new("ShaderNodeMath")
    ab.operation = 'ABSOLUTE'
    nt.links.new(ns.outputs["X"], ab.inputs[0])
    gt = N.new("ShaderNodeMath")
    gt.operation = 'GREATER_THAN'
    gt.inputs[1].default_value = 0.5
    nt.links.new(ab.outputs[0], gt.inputs[0])

    mixc = N.new("ShaderNodeMix")
    mixc.data_type = 'RGBA'
    nt.links.new(gt.outputs[0], mixc.inputs[0])
    nt.links.new(ta.outputs["Color"], mixc.inputs[6])
    nt.links.new(tb.outputs["Color"], mixc.inputs[7])
    mixf = N.new("ShaderNodeMix")
    mixf.data_type = 'FLOAT'
    nt.links.new(gt.outputs[0], mixf.inputs[0])
    nt.links.new(ta.outputs["Fac"], mixf.inputs[2])
    nt.links.new(tb.outputs["Fac"], mixf.inputs[3])

    nt.links.new(mixc.outputs[2], b.inputs["Base Color"])
    _bump(nt, b, mixf.outputs[0], bump, 0.02)
    _set(b, rough=rough)
    return m


def mat_wood(name, dark, light, scale=6.0, rough=0.45, direction='Z'):
    m, nt, b = _new_mat(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    w = nt.nodes.new("ShaderNodeTexWave")
    w.wave_type = 'BANDS'
    w.bands_direction = 'X'
    w.inputs["Scale"].default_value = scale
    w.inputs["Distortion"].default_value = 6.0
    w.inputs["Detail"].default_value = 3.0
    nt.links.new(tc.outputs["Object"], w.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*dark, 1)
    ramp.color_ramp.elements[1].color = (*light, 1)
    nt.links.new(w.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    _set(b, rough=rough)
    _bump(nt, b, w.outputs["Fac"], 0.15, 0.01)
    return m


# Materialpalette ---------------------------------------------------------
M = {}
M["brick"] = mat_brick("Backstein", (0.42, 0.14, 0.08), (0.30, 0.09, 0.055), (0.62, 0.60, 0.55))
M["roof"] = mat_brick("Dachziegel", (0.10, 0.10, 0.115), (0.06, 0.06, 0.07), (0.02, 0.02, 0.02),
                      bw=0.35, rh=0.28, msize=0.02, triplanar=False, rough=0.6, bump=1.0)
M["paving"] = mat_brick("Pflaster", (0.42, 0.40, 0.38), (0.30, 0.29, 0.28), (0.12, 0.12, 0.12),
                        bw=0.24, rh=0.12, msize=0.012, triplanar=False, rough=0.9)
M["stonepath"] = mat_brick("Gehwegplatten", (0.55, 0.54, 0.52), (0.45, 0.44, 0.42), (0.2, 0.2, 0.2),
                           bw=0.6, rh=0.6, msize=0.02, triplanar=False, rough=0.85)
M["plaster"] = mat_noise("Putz", (0.86, 0.83, 0.76), (0.94, 0.92, 0.86), scale=25, rough=0.9, bump=0.25)
M["concrete"] = mat_noise("Beton", (0.45, 0.45, 0.44), (0.62, 0.62, 0.60), scale=12, rough=0.9, bump=0.2)
M["stone"] = mat_noise("Naturstein", (0.55, 0.53, 0.48), (0.78, 0.76, 0.70), scale=6, rough=0.75, bump=0.3)
M["asphalt"] = mat_noise("Asphalt", (0.05, 0.05, 0.055), (0.11, 0.11, 0.12), scale=90, rough=0.95, bump=0.5,
                         dist=0.01)
M["grass"] = mat_noise("Rasen", (0.06, 0.20, 0.03), (0.18, 0.38, 0.08), scale=60, rough=0.95, bump=0.8,
                       dist=0.05)
M["leaf"] = mat_noise("Laub", (0.05, 0.19, 0.04), (0.20, 0.42, 0.07), scale=9, rough=0.7, bump=0.4, dist=0.05)
M["leaf2"] = mat_noise("Laub hell", (0.13, 0.32, 0.05), (0.32, 0.55, 0.10), scale=9, rough=0.7, bump=0.4,
                       dist=0.05)
M["soil"] = mat_noise("Erde", (0.06, 0.035, 0.02), (0.14, 0.09, 0.05), scale=40, rough=1.0, bump=0.8)
M["bark"] = mat_noise("Rinde", (0.09, 0.06, 0.04), (0.22, 0.16, 0.11), scale=14, rough=0.95, bump=1.0,
                      dist=0.05)
M["wood_door"] = mat_wood("Tuerholz", (0.10, 0.04, 0.015), (0.24, 0.10, 0.04))
M["wood_fence"] = mat_wood("Zaunholz", (0.55, 0.53, 0.50), (0.80, 0.78, 0.74), rough=0.6)
M["wood_floor"] = mat_wood("Parkett", (0.35, 0.20, 0.09), (0.62, 0.40, 0.20), scale=14)
M["wood_dark"] = mat_wood("Moebel", (0.08, 0.04, 0.02), (0.20, 0.10, 0.05), scale=9)
M["white"] = mat("Weiss lackiert", (0.93, 0.93, 0.90), rough=0.35)
M["shutter"] = mat("Klappladen", (0.06, 0.24, 0.16), rough=0.45)
M["metal_dark"] = mat("Metall dunkel", (0.03, 0.03, 0.035), rough=0.35, metal=1.0)
M["zinc"] = mat("Zink", (0.55, 0.57, 0.60), rough=0.35, metal=1.0)
M["brass"] = mat("Messing", (0.85, 0.62, 0.20), rough=0.25, metal=1.0)
M["glass"] = mat_glass()
M["garage"] = mat("Garagentor", (0.75, 0.76, 0.78), rough=0.4, metal=0.3)
M["lamp"] = mat_emit("Lampe", (1.0, 0.75, 0.4), 12.0)
M["flower_r"] = mat("Blume rot", (0.8, 0.05, 0.06), rough=0.5)
M["flower_y"] = mat("Blume gelb", (0.95, 0.75, 0.05), rough=0.5)
M["flower_p"] = mat("Blume lila", (0.45, 0.12, 0.65), rough=0.5)
M["flower_w"] = mat("Blume weiss", (0.95, 0.95, 0.92), rough=0.5)
M["fabric_g"] = mat("Stoff grau", (0.22, 0.24, 0.27), rough=0.95)
M["fabric_b"] = mat("Stoff blau", (0.10, 0.20, 0.42), rough=0.95)
M["rug"] = mat("Teppich", (0.55, 0.15, 0.12), rough=1.0)
M["mail"] = mat("Briefkasten", (0.75, 0.05, 0.05), rough=0.4, metal=0.5)
M["line"] = mat("Markierung", (0.9, 0.9, 0.85), rough=0.7)


# --------------------------------------------------------------------------
# Wand-Oeffnungen und Fenster / Tueren
# --------------------------------------------------------------------------
def _rot_vec(v, rz):
    return Euler((0, 0, rz)).to_matrix() @ Vector(v)


def opening(outer, rz, w, h, zc):
    """Boolean-Cutter fuer eine Wandoeffnung. outer = Punkt (x, y) auf der Aussenflaeche."""
    p = Vector((outer[0], outer[1], zc)) + _rot_vec((0, WT / 2, 0), rz)
    return box("cutter", p, (w, WT + 0.6, h), None, (0, 0, rz))


def window(name, outer, rz, zc, w=1.4, h=1.5, shutters=False, flowerbox=False, sill=True):
    """Fenster in lokalen Koordinaten (Aussenflaeche y=0, Blick nach -Y) -> gedreht."""
    root = empty(name, (outer[0], outer[1], zc), (0, 0, rz))
    fw = 0.07
    P = root
    # Rahmen
    box("Rahmen o", (0, 0.10, h / 2 - fw / 2), (w, 0.16, fw), M["white"], parent=P, bevel=0.01)
    box("Rahmen u", (0, 0.10, -h / 2 + fw / 2), (w, 0.16, fw), M["white"], parent=P, bevel=0.01)
    box("Rahmen l", (-w / 2 + fw / 2, 0.10, 0), (fw, 0.16, h), M["white"], parent=P, bevel=0.01)
    box("Rahmen r", (w / 2 - fw / 2, 0.10, 0), (fw, 0.16, h), M["white"], parent=P, bevel=0.01)
    # Glas + Sprossen
    box("Glas", (0, 0.11, 0), (w - 2 * fw, 0.015, h - 2 * fw), M["glass"], parent=P)
    box("Sprosse v", (0, 0.11, 0), (0.045, 0.06, h - 2 * fw), M["white"], parent=P)
    box("Sprosse h", (0, 0.11, 0.12), (w - 2 * fw, 0.06, 0.045), M["white"], parent=P)
    box("Mittelstab", (0, 0.11, -h * 0.5 + h * 0.3), (w - 2 * fw, 0.06, 0.03), M["white"], parent=P)
    # Fensterbank + Sturz
    if sill:
        box("Fensterbank", (0, -0.07, -h / 2 - 0.04), (w + 0.35, 0.26, 0.07), M["stone"], parent=P, bevel=0.01)
        box("Sturz", (0, -0.02, h / 2 + 0.07), (w + 0.25, 0.10, 0.14), M["stone"], parent=P, bevel=0.01)
        box("Schlussstein", (0, -0.04, h / 2 + 0.10), (0.22, 0.12, 0.22), M["stone"], parent=P, bevel=0.01)
    # Klappladen mit Lamellen
    if shutters:
        sw = w * 0.48
        for sgn in (-1, 1):
            cx = sgn * (w / 2 + sw / 2 + 0.06)
            box("Laden", (cx, -0.03, 0), (sw, 0.03, h + 0.05), M["shutter"], parent=P, bevel=0.005)
            n = 11
            for i in range(n):
                z = -h / 2 + 0.16 + i * (h - 0.25) / (n - 1)
                box("Lamelle", (cx, -0.06, z), (sw - 0.12, 0.02, 0.05), M["shutter"], parent=P,
                    rot=(math.radians(-25), 0, 0))
    # Blumenkasten
    if flowerbox:
        box("Blumenkasten", (0, -0.20, -h / 2 - 0.20), (w + 0.1, 0.24, 0.20), M["wood_door"], parent=P,
            bevel=0.01)
        box("Erde", (0, -0.20, -h / 2 - 0.10), (w + 0.05, 0.20, 0.03), M["soil"], parent=P)
        fm = [M["flower_r"], M["flower_w"], M["flower_p"], M["flower_y"]]
        for i in range(9):
            x = -w / 2 + 0.1 + i * (w - 0.2) / 8
            sphere("Busch", (x, -0.20, -h / 2 - 0.03), 0.09, M["leaf"], P, sub=1, lumpy=0.2)
            sphere("Bluete", (x + random.uniform(-.03, .03), -0.22, -h / 2 + 0.06), 0.05,
                   random.choice(fm), P, sub=1)
    return root


def door(outer, rz, zbot, w=1.2, h=2.4):
    root = empty("Haustuer", (outer[0], outer[1], zbot), (0, 0, rz))
    P = root
    fw = 0.10
    # Zarge
    box("Zarge l", (-w / 2 + fw / 2, 0.06, h / 2), (fw, 0.2, h), M["white"], parent=P, bevel=0.01)
    box("Zarge r", (w / 2 - fw / 2, 0.06, h / 2), (fw, 0.2, h), M["white"], parent=P, bevel=0.01)
    box("Zarge o", (0, 0.06, h - fw / 2), (w, 0.2, fw), M["white"], parent=P, bevel=0.01)
    box("Tuerschwelle", (0, -0.05, 0.02), (w + 0.1, 0.35, 0.05), M["stone"], parent=P)
    # Blatt
    dw, dh = w - 2 * fw, h - fw
    box("Tuerblatt", (0, 0.12, dh / 2), (dw, 0.06, dh), M["wood_door"], parent=P, bevel=0.005)
    # Kassetten
    for cx in (-dw * 0.24, dw * 0.24):
        box("Kassette u", (cx, 0.075, 0.55), (dw * 0.38, 0.03, 0.7), M["wood_door"], parent=P, bevel=0.01)
        box("Kassette m", (cx, 0.075, 1.25), (dw * 0.38, 0.03, 0.55), M["wood_door"], parent=P, bevel=0.01)
    # Glasfeld oben
    box("Tuerglas", (0, 0.09, 1.95), (dw * 0.8, 0.02, 0.3), M["glass"], parent=P)
    box("Glasrahmen", (0, 0.10, 1.95), (dw * 0.85, 0.015, 0.03), M["brass"], parent=P)
    # Beschlaege
    cyl("Klinke Rosette", (dw / 2 - 0.1, 0.06, 1.05), 0.035, 0.02, M["brass"], (math.radians(90), 0, 0), P)
    box("Klinke", (dw / 2 - 0.16, 0.04, 1.05), (0.12, 0.02, 0.02), M["brass"], parent=P)
    cyl("Tuerspion", (0, 0.06, 1.65), 0.012, 0.02, M["brass"], (math.radians(90), 0, 0), P, 12)
    box("Hausnummer", (w / 2 + 0.25, 0.0, 1.7), (0.16, 0.02, 0.16), M["white"], parent=P)
    box("Klingel", (-w / 2 - 0.2, 0.0, 1.3), (0.07, 0.02, 0.11), M["brass"], parent=P)
    box("Fussmatte", (0, -0.55, 0.01), (0.9, 0.55, 0.025), M["rug"], parent=P)
    return root


def wall_lamp(loc, rz):
    root = empty("Wandlampe", loc, (0, 0, rz))
    box("Halter", (0, 0.03, 0), (0.08, 0.06, 0.2), M["metal_dark"], parent=root)
    cyl("Lampenglas", (0, -0.07, 0), 0.07, 0.2, M["lamp"], parent=root, seg=16)
    cyl("Lampendach", (0, -0.07, 0.13), 0.09, 0.03, M["metal_dark"], parent=root, seg=16)
    return root


# --------------------------------------------------------------------------
# Fundament, Waende, Geschossdecken
# --------------------------------------------------------------------------
def build_house():
    # Sockel
    box("Sockel", (0, 0, Z0 / 2), (2 * HW + 0.3, 2 * HD + 0.3, Z0), M["concrete"], bevel=0.02)
    box("Sockelabsatz", (0, 0, 0.02), (2 * HW + 0.6, 2 * HD + 0.6, 0.06), M["concrete"])

    # Aussenwand als Hohlkoerper
    wall = box("Aussenwand", (0, 0, (Z0 + ZW) / 2), (2 * HW, 2 * HD, ZW - Z0), M["brick"])
    inner = box("innen", (0, 0, (Z0 - 0.05 + ZW + 0.2) / 2),
                (2 * HW - 2 * WT, 2 * HD - 2 * WT, ZW + 0.2 - Z0 + 0.05), None)
    cut(wall, inner)

    cutters = []
    # --- Vorderseite (-Y) ---
    F = lambda u: ((u, -HD), 0.0)
    B = lambda u: ((u, HD), math.pi)
    L = lambda u: ((-HW, u), -math.pi / 2)
    R = lambda u: ((HW, u), math.pi / 2)

    GF, UF = 2.0, 5.25
    specs = []
    # (Seitenfunktion, u, zc, w, h, Laden, Blumenkasten)
    specs += [(F, -3.3, GF, 1.4, 1.5, True, True), (F, 3.3, GF, 1.4, 1.5, True, True)]
    specs += [(F, -3.3, UF, 1.4, 1.5, True, False), (F, 0.0, UF, 1.4, 1.5, True, False),
              (F, 3.3, UF, 1.4, 1.5, True, False)]
    specs += [(B, -3.3, GF, 1.4, 1.5, False, False), (B, 3.3, GF, 1.4, 1.5, False, False)]
    specs += [(B, -3.3, UF, 1.4, 1.5, False, False), (B, 0.0, UF, 1.4, 1.5, False, False),
              (B, 3.3, UF, 1.4, 1.5, False, False)]
    specs += [(L, -1.6, GF, 1.2, 1.5, True, False), (L, 1.6, GF, 1.2, 1.5, True, False),
              (L, -1.6, UF, 1.2, 1.5, True, False), (L, 1.6, UF, 1.2, 1.5, True, False)]
    specs += [(R, 3.0, GF, 1.0, 1.5, False, False),
              (R, -1.6, UF, 1.2, 1.5, True, False), (R, 1.6, UF, 1.2, 1.5, True, False)]

    for side, u, zc, w, h, sh, fb in specs:
        outer, rz = side(u)
        cutters.append(opening(outer, rz, w, h, zc))
        window("Fenster", outer, rz, zc, w, h, sh, fb)

    # Haustuer
    outer, rz = F(0.0)
    cutters.append(opening(outer, rz, 1.2, 2.4, Z0 + 1.2))
    door(outer, rz, Z0, 1.2, 2.4)
    # Terrassentuer hinten
    outer, rz = B(0.0)
    cutters.append(opening(outer, rz, 2.0, 2.3, Z0 + 1.15))
    tw = window("Terrassentuer", outer, rz, Z0 + 1.15, 2.0, 2.3, False, False, sill=False)

    cut(wall, cutters)

    # Giebelwaende (mit Rundfenster)
    for sgn in (-1, 1):
        pts = [(-HD, ZW - 0.02), (HD, ZW - 0.02), (0, RIDGE)]
        g = obj("Giebel", mesh_prism(pts, WT), (sgn * HW if sgn > 0 else -HW + WT, 0, 0), (0, 0, 0), M["brick"])
        rc = cyl("cutter", (sgn * HW, 0, ZW + 1.35), 0.55, 1.0, None, (0, math.radians(90), 0), seg=40)
        cut(g, rc)
        # Rundfenster: Ring, Glas, Kreuz
        outer = sgn * HW
        bpy.ops.mesh.primitive_torus_add(major_radius=0.58, minor_radius=0.06, major_segments=40,
                                         minor_segments=12, location=(outer, 0, ZW + 1.35),
                                         rotation=(0, math.radians(90), 0))
        t = bpy.context.active_object
        t.name = "Rundfenster Ring"
        t.data.materials.append(M["white"])
        for p in t.data.polygons:
            p.use_smooth = True
        cyl("Rundfenster Glas", (outer + sgn * -0.15, 0, ZW + 1.35), 0.55, 0.02, M["glass"],
            (0, math.radians(90), 0), seg=40)
        for a in (0, 90):
            box("Rundfenster Sprosse", (outer - sgn * 0.15, 0, ZW + 1.35), (0.04, 1.1, 0.04), M["white"],
                (math.radians(a), 0, 0))

    # Geschossdecken + Boeden
    box("Decke OG", (0, 0, 3.65), (2 * HW - 2 * WT, 2 * HD - 2 * WT, 0.3), M["plaster"])
    box("Boden EG", (0, 0, Z0 + 0.03), (2 * HW - 2 * WT, 2 * HD - 2 * WT, 0.06), M["wood_floor"])
    box("Boden OG", (0, 0, 3.83), (2 * HW - 2 * WT, 2 * HD - 2 * WT, 0.05), M["wood_floor"])
    box("Decke DG", (0, 0, ZW - 0.1), (2 * HW - 2 * WT, 2 * HD - 2 * WT, 0.2), M["plaster"])
    # Innenwand
    box("Innenwand EG", (1.0, 0.6, (Z0 + 3.5) / 2), (0.15, 4.0, 3.0), M["plaster"])
    box("Innenwand OG", (-1.0, -0.4, (3.8 + ZW - 0.2) / 2), (0.15, 5.0, 2.7), M["plaster"])

    # Eckquader
    for sx in (-1, 1):
        for sy in (-1, 1):
            k, z = 0, Z0
            while z + 0.4 <= ZW + 0.001:
                a, b = (0.55, 0.32) if k % 2 == 0 else (0.32, 0.55)
                cx = sx * (HW + 0.03 - a / 2)
                cy = sy * (HD + 0.03 - b / 2)
                box("Quader", (cx, cy, z + 0.2), (a + 0.03, b + 0.03, 0.38), M["stone"], bevel=0.01)
                z += 0.4
                k += 1

    # Gesimsband zwischen den Geschossen
    zb = 3.65
    box("Band v", (0, -HD - 0.06, zb), (2 * HW + 0.2, 0.14, 0.16), M["stone"], bevel=0.015)
    box("Band h", (0, HD + 0.06, zb), (2 * HW + 0.2, 0.14, 0.16), M["stone"], bevel=0.015)
    box("Band l", (-HW - 0.06, 0, zb), (0.14, 2 * HD + 0.2, 0.16), M["stone"], bevel=0.015)
    box("Band r", (HW + 0.06, 0, zb), (0.14, 2 * HD + 0.2, 0.16), M["stone"], bevel=0.015)


# --------------------------------------------------------------------------
# Dach
# --------------------------------------------------------------------------
def build_roof():
    run = HD + OVER
    L = run / math.cos(PITCH)           # Hanglaenge
    W = 2 * (HW + OVER)
    T = 0.16
    for sgn in (-1, 1):                  # sgn=-1 -> Vorderseite (-Y)
        yc = sgn * run / 2
        zc = RIDGE - (run / 2) * math.tan(PITCH)
        nrm = Vector((0, -sgn * math.sin(PITCH), math.cos(PITCH)))
        c = Vector((0, yc, zc)) + nrm * (T / 2)
        rot = (sgn * math.radians(35), 0, 0)
        # Rotation: sgn=-1 (vorn) => Hang faellt nach -Y => +35 Grad um X
        rot = (-sgn * PITCH, 0, 0)
        slab = box("Dachflaeche", tuple(c), (W, L, T), M["roof"], rot)
        rows = int(L / 0.28)
        for i in range(rows):
            y = -L / 2 + 0.14 + i * 0.28
            box("Ziegelreihe", (0, y, T / 2 + 0.02), (W, 0.05, 0.05), M["roof"], parent=slab)
        for xs in (-1, 1):
            box("Ortgang", (xs * (W / 2 - 0.03), 0, -0.02), (0.06, L + 0.02, T + 0.16), M["white"],
                parent=slab)
        box("Traufbrett", (0, -sgn * -L / 2 * 0 + (L / 2 - 0.02) * (1), -0.02), (W, 0.05, T + 0.16),
            M["white"], parent=slab)
        # Dachrinne + Fallrohre
        gy = sgn * (run - 0.05)
        gz = RIDGE - run * math.tan(PITCH) - 0.16
        cyl("Dachrinne", (0, gy, gz), 0.075, W - 0.2, M["zinc"], (0, math.radians(90), 0), seg=16)
        for sx in (-1, 1):
            px = sx * (HW - 0.25)
            py = sgn * (HD + 0.14)
            cyl("Fallrohr", (px, py, (gz + Z0) / 2), 0.05, gz - Z0, M["zinc"], seg=12)
            cyl("Rohrbogen", (px, sgn * (HD + 0.14 + (run - 0.05 - HD - 0.14) / 2), gz - 0.05), 0.045,
                run - 0.05 - HD - 0.14, M["zinc"], (math.radians(90), 0, 0), seg=12)
            for zz in (1.5, 3.0, 4.5):
                cyl("Rohrschelle", (px, py, zz), 0.062, 0.05, M["metal_dark"], seg=12)
    # First
    box("Firstziegel", (0, 0, RIDGE + 0.05), (W - 0.1, 0.34, 0.34), M["roof"], (math.radians(45), 0, 0), bevel=0.01)
    for xs in (-1, 1):
        box("Firstkappe", (xs * (W / 2 - 0.03), 0, RIDGE + 0.05), (0.08, 0.5, 0.5), M["roof"],
            (math.radians(45), 0, 0))

    # Kamin
    cx, cy = 3.3, 1.3
    ch = box("Kamin", (cx, cy, 8.3), (1.0, 1.0, 4.6), M["brick"])
    box("Kaminkopf", (cx, cy, 10.62), (1.3, 1.3, 0.14), M["concrete"], bevel=0.02)
    box("Kaminkopf 2", (cx, cy, 10.45), (1.15, 1.15, 0.2), M["brick"])
    for dx in (-0.2, 0.2):
        cyl("Schornsteinrohr", (cx + dx, cy, 10.85), 0.14, 0.4, M["metal_dark"], seg=16)
        cyl("Rohrkappe", (cx + dx, cy, 11.07), 0.19, 0.04, M["metal_dark"], seg=16)
    box("Kaminblech", (cx, cy, 8.55), (1.24, 1.24, 0.06), M["zinc"])

    # Gaube
    gx, gy0, gy1 = 0.0, -3.5, -1.3
    gw = 2.0
    zb = 6.7
    top = 8.6
    body = box("Gaube", (gx, (gy0 + gy1) / 2, (zb + top) / 2), (gw, gy1 - gy0, top - zb), M["plaster"])
    front_y = gy0
    cut(body, opening((gx, front_y), 0, 0.9, 1.0, 7.75))
    window("Gaubenfenster", (gx, front_y), 0, 7.75, 0.9, 1.0, False, False)
    # Gaubendach (Satteldach entlang Y)
    gp = math.radians(32)
    hw = gw / 2 + 0.25
    rise = hw * math.tan(gp)
    ln = (gy1 - gy0) + 0.9
    for sx in (-1, 1):
        slen = hw / math.cos(gp)
        c = Vector((sx * hw / 2, (gy0 + gy1) / 2 - 0.15, top + rise - (hw / 2) * math.tan(gp)))
        n = Vector((sx * math.sin(gp), 0, math.cos(gp)))
        box("Gaubendach", tuple(c + n * 0.05), (slen, ln, 0.1), M["roof"], (0, sx * gp, 0))
    box("Gaubenfirst", (0, (gy0 + gy1) / 2 - 0.15, top + rise + 0.03), (0.16, ln, 0.16), M["roof"],
        (0, math.radians(45), 0))
    # Giebeldreieck vorne
    tri = obj("Gaubengiebel", mesh_prism([(-gw / 2 - 0.1, 0), (gw / 2 + 0.1, 0), (0, rise)], 0.12),
              (gx, gy0 + 0.05, top), (0, 0, math.radians(90)), M["plaster"])
    # Fallblech an der Gaube
    box("Gaubenbrett", (0, gy0 - 0.1, top - 0.05), (gw + 0.2, 0.06, 0.1), M["white"])


# --------------------------------------------------------------------------
# Vordach, Garage, Terrasse
# --------------------------------------------------------------------------
def build_porch():
    box("Podest", (0, -5.2, 0.28), (4.4, 2.4, 0.45), M["stone"], bevel=0.02)
    box("Stufe 1", (0, -6.75, 0.125), (2.8, 0.7, 0.25), M["stone"], bevel=0.02)
    box("Stufe 2", (0, -6.4, 0.375), (2.6, 0.7, 0.25), M["stone"], bevel=0.02)
    for sx in (-1, 1):
        box("Podestplatte", (sx * 1.0, -5.2, 0.51), (1.9, 2.2, 0.03), M["paving"])
        x = sx * 1.9
        box("Saeulenfuss", (x, -6.1, 0.6), (0.36, 0.36, 0.2), M["white"], bevel=0.01)
        box("Saeule", (x, -6.1, 1.85), (0.2, 0.2, 2.3), M["white"], bevel=0.01)
        box("Saeulenkopf", (x, -6.1, 3.08), (0.36, 0.36, 0.14), M["white"], bevel=0.01)
        # Gelaender
        box("Gelaender Handlauf", (sx * 2.15, -5.2, 1.3), (0.06, 2.3, 0.06), M["white"])
        for i in range(8):
            box("Stab", (sx * 2.15, -6.2 + i * 0.3, 0.95), (0.03, 0.03, 0.7), M["white"])
    box("Vordachbalken", (0, -6.1, 3.28), (4.3, 0.24, 0.22), M["white"], bevel=0.01)
    box("Vordach", (0, -5.35, 3.42), (4.9, 3.0, 0.12), M["roof"], (math.radians(6), 0, 0), bevel=0.01)
    box("Vordachrand", (0, -6.82, 3.30), (4.9, 0.05, 0.16), M["white"], (math.radians(6), 0, 0))
    wall_lamp((1.25, -HD - 0.0, 2.35), 0.0)
    wall_lamp((-1.25, -HD - 0.0, 2.35), 0.0)


def build_garage():
    gx0, gx1 = HW, HW + 5.0
    gy0, gy1 = -HD, 2.0
    gh = 3.6
    cx, cy = (gx0 + gx1) / 2, (gy0 + gy1) / 2
    sx, sy = gx1 - gx0, gy1 - gy0
    g = box("Garage", (cx, cy, (Z0 + gh) / 2), (sx, sy, gh - Z0), M["brick"])
    cut(g, box("innen", (cx, cy, (Z0 - 0.05 + gh + 0.2) / 2), (sx - 2 * WT, sy - 2 * WT, gh + 0.2 - Z0 + 0.05), None))
    cutters = []
    # Garagentor
    cutters.append(opening((cx, gy0), 0.0, 4.0, 2.4, Z0 + 1.2))
    # Seitenfenster
    cutters.append(opening((gx1, -1.0), math.pi / 2, 1.0, 1.0, 2.2))
    cut(g, cutters)
    box("Sockel Garage", (cx, cy, Z0 / 2), (sx + 0.3, sy + 0.3, Z0), M["concrete"], bevel=0.02)
    window("Garagenfenster", (gx1, -1.0), math.pi / 2, 2.2, 1.0, 1.0, False, False)
    # Sektionaltor
    root = empty("Garagentor", (cx, gy0, Z0))
    for i in range(6):
        z = 0.2 + i * 0.4
        box("Torsektion", (0, 0.12, z), (3.96, 0.06, 0.38), M["garage"], parent=root, bevel=0.01)
        box("Torrille", (0, 0.085, z + 0.19), (3.96, 0.02, 0.02), M["metal_dark"], parent=root)
    for i in range(4):
        box("Torfenster", (-1.35 + i * 0.9, 0.085, 2.0), (0.7, 0.02, 0.16), M["glass"], parent=root)
    box("Torgriff", (1.5, 0.05, 1.0), (0.03, 0.04, 0.3), M["metal_dark"], parent=root)
    for xs in (-1, 1):
        box("Torzarge", (xs * 2.03, 0.08, 1.2), (0.1, 0.2, 2.4), M["white"], parent=root)
    box("Torsturz", (0, 0.08, 2.45), (4.16, 0.2, 0.1), M["white"], parent=root)
    # Flachdach mit Attika
    box("Garagendach", (cx, cy, gh + 0.1), (sx + 0.6, sy + 0.6, 0.2), M["concrete"], (math.radians(1.5), 0, 0),
        bevel=0.02)
    box("Attika v", (cx, gy0 - 0.3, gh + 0.32), (sx + 0.6, 0.1, 0.25), M["white"])
    box("Attika r", (gx1 + 0.3, cy, gh + 0.32), (0.1, sy + 0.6, 0.25), M["white"])
    box("Attika h", (cx, gy1 + 0.3, gh + 0.32), (sx + 0.6, 0.1, 0.25), M["white"])
    cyl("Garagenrinne", (gx1 + 0.3, cy, gh - 0.02), 0.06, sy + 0.5, M["zinc"], (math.radians(90), 0, 0), seg=12)
    cyl("Garagenfallrohr", (gx1 + 0.3, gy0 + 0.3, (gh + Z0) / 2), 0.045, gh - Z0, M["zinc"], seg=12)
    wall_lamp((cx + 2.45, gy0, 2.7), 0.0)
    # Einfahrt
    box("Einfahrt", (cx, -9.0, 0.03), (5.2, 10.0, 0.06), M["paving"])
    box("Einfahrt Rand", (gx1 + 0.35, -9.0, 0.04), (0.2, 10.0, 0.08), M["concrete"])


def build_terrace():
    box("Terrasse", (0, 6.2, 0.06), (7.0, 4.4, 0.12), M["paving"])
    box("Terrassenrand", (0, 8.45, 0.08), (7.2, 0.12, 0.16), M["concrete"])
    # Gartenmoebel
    box("Tisch", (0, 6.5, 0.8), (1.4, 0.9, 0.06), M["wood_dark"], bevel=0.01)
    for sx in (-0.6, 0.6):
        for sy in (-0.35, 0.35):
            box("Tischbein", (sx, 6.5 + sy, 0.4), (0.06, 0.06, 0.78), M["metal_dark"])
    for sx in (-0.5, 0.5):
        for sy in (5.55, 7.45):
            box("Stuhl Sitz", (sx, sy, 0.48), (0.45, 0.45, 0.05), M["wood_dark"])
            box("Stuhl Lehne", (sx, sy + (0.2 if sy < 6.5 else -0.2), 0.8), (0.45, 0.05, 0.6), M["wood_dark"])
            for dx in (-0.18, 0.18):
                for dy in (-0.18, 0.18):
                    box("Stuhlbein", (sx + dx, sy + dy, 0.24), (0.04, 0.04, 0.46), M["metal_dark"])
    cyl("Schirmstange", (0, 6.5, 1.3), 0.025, 2.4, M["metal_dark"], seg=8)
    cyl("Sonnenschirm", (0, 6.5, 2.45), 1.3, 0.35, M["fabric_b"], seg=24, r2=0.05)


# --------------------------------------------------------------------------
# Innenraum
# --------------------------------------------------------------------------
def build_interior():
    z = Z0 + 0.06
    # Wohnzimmer (links vorne)
    box("Teppich", (-2.6, -1.2, z + 0.01), (2.8, 2.0, 0.02), M["rug"])
    box("Sofa", (-3.4, 0.9, z + 0.25), (2.2, 0.9, 0.5), M["fabric_g"], bevel=0.05)
    box("Sofa Lehne", (-3.4, 1.28, z + 0.65), (2.2, 0.15, 0.5), M["fabric_g"], bevel=0.05)
    box("Sessel", (-1.4, -1.6, z + 0.25), (0.8, 0.8, 0.5), M["fabric_b"], bevel=0.05)
    box("Couchtisch", (-2.6, -0.6, z + 0.2), (1.1, 0.6, 0.05), M["wood_dark"])
    for sx in (-0.5, 0.5):
        for sy in (-0.25, 0.25):
            box("Tischbein", (-2.6 + sx, -0.6 + sy, z + 0.1), (0.04, 0.04, 0.2), M["metal_dark"])
    box("Regal", (-4.5, -0.6, z + 1.0), (0.35, 2.0, 2.0), M["wood_dark"])
    # Kueche (rechts hinten)
    box("Kuechenzeile", (3.0, 3.4, z + 0.45), (3.2, 0.6, 0.9), M["white"])
    box("Arbeitsplatte", (3.0, 3.4, z + 0.92), (3.25, 0.65, 0.05), M["stone"])
    box("Oberschrank", (3.0, 3.55, z + 1.9), (3.2, 0.35, 0.8), M["white"])
    box("Esstisch", (2.9, 0.4, z + 0.72), (1.6, 0.9, 0.05), M["wood_dark"])
    for sx in (-0.7, 0.7):
        for sy in (-0.35, 0.35):
            box("Tischbein", (2.9 + sx, 0.4 + sy, z + 0.35), (0.06, 0.06, 0.7), M["wood_dark"])
    # Schlafzimmer OG
    zo = 3.88
    box("Bett", (-3.2, 1.4, zo + 0.25), (1.6, 2.0, 0.5), M["white"], bevel=0.04)
    box("Bettdecke", (-3.2, 1.2, zo + 0.55), (1.55, 1.4, 0.12), M["fabric_b"], bevel=0.05)
    box("Kopfteil", (-3.2, 2.45, zo + 0.7), (1.7, 0.1, 1.0), M["wood_dark"])
    box("Kleiderschrank", (-4.3, -1.7, zo + 1.1), (0.6, 1.8, 2.2), M["wood_dark"])
    box("Schreibtisch", (2.8, -1.5, zo + 0.72), (1.4, 0.7, 0.05), M["wood_dark"])
    box("Schreibtisch Bein", (2.15, -1.5, zo + 0.35), (0.05, 0.6, 0.7), M["wood_dark"])
    box("Schreibtisch Bein", (3.45, -1.5, zo + 0.35), (0.05, 0.6, 0.7), M["wood_dark"])
    # warmes Licht innen
    for (x, y, zz) in ((-2.5, 0, 3.2), (2.5, 1.0, 3.2), (-2.5, 0.5, 6.0), (2.5, -0.5, 6.0)):
        bpy.ops.object.light_add(type='POINT', location=(x, y, zz))
        l = bpy.context.active_object
        l.name = "Innenlicht"
        l.data.energy = 150
        l.data.color = (1.0, 0.82, 0.6)
        l.data.shadow_soft_size = 0.4


# --------------------------------------------------------------------------
# Garten & Umgebung
# --------------------------------------------------------------------------
def tree(name, x, y, h=6.0, crown=2.6, mat_leaf=None):
    mat_leaf = mat_leaf or M["leaf"]
    root = empty(name, (x, y, 0))
    cyl("Stamm", (0, 0, h * 0.3), 0.28, h * 0.6, M["bark"], parent=root, seg=12, r2=0.18)
    for i in range(3):
        a = math.radians(120 * i + random.uniform(-20, 20))
        cyl("Ast", (math.cos(a) * 0.5, math.sin(a) * 0.5, h * 0.62), 0.07, 1.4, M["bark"],
            (math.radians(35) * math.sin(a), -math.radians(35) * math.cos(a), 0), root, seg=8)
    sphere("Krone", (0, 0, h * 0.75 + crown * 0.3), crown, mat_leaf, root, sub=3, lumpy=0.18, squash=0.85)
    for i in range(6):
        a = math.radians(60 * i + random.uniform(-15, 15))
        r = crown * 0.65
        sphere("Krone Klumpen", (math.cos(a) * r, math.sin(a) * r, h * 0.7 + random.uniform(0, crown * 0.6)),
               crown * random.uniform(0.5, 0.7), random.choice([M["leaf"], M["leaf2"]]), root, sub=3,
               lumpy=0.2, squash=0.85)
    return root


def bush(x, y, r=0.5, m=None):
    m = m or random.choice([M["leaf"], M["leaf2"]])
    sphere("Busch", (x, y, r * 0.65), r, m, sub=3, lumpy=0.15, squash=0.8)


def build_garden():
    # Boden
    box("Rasen", (0, 0, -0.02), (600, 600, 0.04), M["grass"])
    # Strasse + Gehweg
    box("Strasse", (0, -19.0, 0.0), (600, 8.0, 0.06), M["asphalt"])
    box("Gehweg", (0, -13.9, 0.05), (600, 2.4, 0.1), M["concrete"])
    box("Bordstein", (0, -15.2, 0.06), (600, 0.2, 0.14), M["stone"])
    box("Bordstein 2", (0, -12.65, 0.06), (600, 0.15, 0.13), M["stone"])
    for i in range(-9, 10):
        box("Mittellinie", (i * 4.5, -19.0, 0.065), (2.2, 0.15, 0.01), M["line"])
    # Weg zur Haustuer
    for i in range(6):
        box("Trittplatte", (random.uniform(-0.05, 0.05), -7.6 - i * 0.85, 0.045), (1.5, 0.7, 0.07),
            M["stonepath"], (0, 0, random.uniform(-0.03, 0.03)), bevel=0.02)
    box("Weganschluss", (0, -12.4, 0.045), (1.6, 0.5, 0.07), M["stonepath"])

    # Zaun vorne (mit Tor an Weg und Einfahrt)
    post_m = mesh_box(0.14, 0.14, 1.25)
    pick_m = mesh_box(0.09, 0.03, 0.95)
    rail_cache = {}

    def fence_run(x0, x1, y, axis='x'):
        length = x1 - x0
        n = max(1, int(length / 0.2))
        for r_z in (0.35, 0.85):
            mid = (x0 + x1) / 2
            if axis == 'x':
                box("Zaunriegel", (mid, y, r_z), (length, 0.05, 0.07), M["wood_fence"])
            else:
                box("Zaunriegel", (y, mid, r_z), (0.05, length, 0.07), M["wood_fence"])
        for i in range(n + 1):
            p = x0 + i * length / n
            m = obj("Latte", pick_m, (p, y, 0.5) if axis == 'x' else (y, p, 0.5), (0, 0, 0 if axis == 'x' else math.pi / 2),
                    M["wood_fence"])
        nposts = max(2, int(length / 2.5) + 1)
        for i in range(nposts):
            p = x0 + i * length / (nposts - 1)
            obj("Pfosten", post_m, (p, y, 0.62) if axis == 'x' else (y, p, 0.62), (0, 0, 0), M["wood_fence"])
            box("Pfostenkappe", (p, y, 1.27) if axis == 'x' else (y, p, 1.27), (0.2, 0.2, 0.05), M["white"])

    fy = -12.0
    fence_run(-14.0, -0.9, fy)
    fence_run(0.9, 2.4, fy)
    fence_run(12.8, 17.0, fy)
    fence_run(-12.0 + 0.0, 12.0, 14.5, 'x') if False else None
    fence_run(fy, 14.5, -14.0, 'y')
    fence_run(fy, 14.5, 17.0, 'y')
    fence_run(-14.0, 17.0, 14.5, 'x')
    # Gartentor (offen)
    for sx, rz in ((-1, math.radians(-70)), (1, math.radians(70))):
        g = empty("Gartentor", (sx * 0.85, fy, 0), (0, 0, rz if sx == -1 else -rz + math.pi))
        for i in range(6):
            obj("Torlatte", pick_m, (0.1 + i * 0.13 if sx == 1 else 0.1 + i * 0.13, 0, 0.5), (0, 0, 0),
                M["wood_fence"], g)
        box("Torriegel", (0.42, 0, 0.6), (0.8, 0.05, 0.07), M["wood_fence"], parent=g)

    # Baeume
    tree("Baum 1", -12.0, 4.0, 6.5, 2.8)
    tree("Baum 2", 20.0, -6.0, 5.5, 2.4, M["leaf2"])
    tree("Baum 3", -9.0, 9.0, 7.5, 3.2)
    tree("Baum 4", 13.5, 9.0, 6.0, 2.6, M["leaf2"])
    tree("Baum 5", 3.0, 11.5, 5.0, 2.2)
    # Kleine Straßenbaeume
    for x in (-32, -22, 24, 34):
        tree("Strassenbaum", x, -12.5, 5.0, 1.8, M["leaf2"])

    # Buesche entlang der Hausfront
    for x in (-4.6, -3.7, -2.3, 2.3, 3.7, 4.6):
        bush(x, -4.65, random.uniform(0.35, 0.5))
    for x in (-4.4, -3.0, -1.5, 0.0, 1.5, 3.0, 4.4):
        bush(x, 4.7, random.uniform(0.4, 0.6))
    for y in (-2.5, -1.0, 1.0, 2.5):
        bush(-5.6, y, 0.45)
    for x in (-13.4, -13.4, 16.4, 16.4):
        bush(x, random.uniform(-10, 13), 0.9)
    # Hecke hinten
    for x in range(-13, 17, 1):
        bush(x + 0.4, 14.0, 0.75, M["leaf"])

    # Blumenbeete
    for cx, cy, sx, sy in ((-6.5, -8.5, 4.0, 2.6), (6.5, -13.0 + 2.6, 0, 0)):
        if sx == 0:
            continue
        box("Beet", (cx, cy, 0.05), (sx, sy, 0.1), M["soil"], bevel=0.02)
        for edge in (-1, 1):
            box("Beetrand", (cx, cy + edge * sy / 2, 0.11), (sx + 0.2, 0.12, 0.2), M["stone"], bevel=0.02)
            box("Beetrand", (cx + edge * sx / 2, cy, 0.11), (0.12, sy + 0.2, 0.2), M["stone"], bevel=0.02)
        fm = [M["flower_r"], M["flower_y"], M["flower_p"], M["flower_w"]]
        for _ in range(45):
            x = cx + random.uniform(-sx / 2 + 0.2, sx / 2 - 0.2)
            y = cy + random.uniform(-sy / 2 + 0.2, sy / 2 - 0.2)
            cyl("Stiel", (x, y, 0.22), 0.01, 0.35, M["leaf"], seg=6)
            sphere("Bluete", (x, y, 0.42), random.uniform(0.06, 0.1), random.choice(fm), sub=1)
            sphere("Laub", (x, y, 0.15), 0.12, M["leaf2"], sub=1, squash=0.6)
    # Bank
    box("Bank Sitz", (-7.0, -4.6, 0.5), (1.6, 0.45, 0.06), M["wood_fence"])
    box("Bank Lehne", (-7.0, -4.4, 0.85), (1.6, 0.05, 0.4), M["wood_fence"], (math.radians(-10), 0, 0))
    for sx in (-0.7, 0.7):
        box("Bank Bein", (-7.0 + sx, -4.6, 0.25), (0.06, 0.4, 0.5), M["metal_dark"])
    # Briefkasten
    box("Briefkastenpfosten", (-1.9, -11.3, 0.6), (0.08, 0.08, 1.2), M["metal_dark"])
    box("Briefkasten", (-1.9, -11.3, 1.3), (0.4, 0.22, 0.28), M["mail"], bevel=0.03)
    box("Briefkastenfahne", (-1.69, -11.3, 1.38), (0.02, 0.03, 0.14), M["flower_y"])
    # Gartenlaternen am Weg
    for y in (-8.0, -10.5):
        for sx in (-1.3, 1.3):
            cyl("Laternenmast", (sx, y, 0.4), 0.03, 0.8, M["metal_dark"], seg=8)
            cyl("Laternenlicht", (sx, y, 0.85), 0.07, 0.15, M["lamp"], seg=12)
            cyl("Laternenkopf", (sx, y, 0.95), 0.1, 0.04, M["metal_dark"], seg=12)
    # Steine
    for _ in range(14):
        sphere("Stein", (random.uniform(-13, 16), random.uniform(-11, 13), 0.06),
               random.uniform(0.1, 0.25), M["stone"], sub=2, lumpy=0.2, squash=0.6)


# --------------------------------------------------------------------------
# Welt, Licht, Kamera, Rendering
# --------------------------------------------------------------------------
def setup_world_and_camera(fast=False):
    world = bpy.data.worlds.new("Himmel") if not scene.world else scene.world
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = 'MULTIPLE_SCATTERING'
    sky.sun_elevation = math.radians(38)
    sky.sun_rotation = math.radians(-35)
    sky.sun_size = math.radians(1.2)
    bg.inputs["Strength"].default_value = 1.0
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])

    # Kamera
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(2.5, -2.0, 3.8))
    target = bpy.context.active_object
    target.name = "Kamerazielpunkt"
    cam_d = bpy.data.cameras.new("Kamera")
    cam_d.lens = 28
    cam_d.dof.use_dof = False
    cam = bpy.data.objects.new("Kamera", cam_d)
    _link(cam)
    cam.location = (-11.0, -26.0, 6.0)
    tc = cam.constraints.new('TRACK_TO')
    tc.target = target
    tc.track_axis = 'TRACK_NEGATIVE_Z'
    tc.up_axis = 'UP_Y'
    scene.camera = cam

    # Renderer
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 24 if fast else 128
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1280 if fast else 1920
    scene.render.resolution_y = 720 if fast else 1080
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.exposure = -1.3


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    fast = "--fast" in argv
    build_house()
    build_roof()
    build_porch()
    build_garage()
    build_terrace()
    build_interior()
    build_garden()
    setup_world_and_camera(fast)

    import os
    here = os.path.dirname(bpy.data.filepath) or os.path.dirname(os.path.abspath(__file__)) \
        if "__file__" in globals() else os.getcwd()
    blend = os.path.join(here, "haus.blend")
    if bpy.app.background or "--save" in argv:
        bpy.ops.wm.save_as_mainfile(filepath=blend)
        print("Gespeichert:", blend)
    if "--render" in argv:
        scene.render.filepath = os.path.join(here, "haus_render.png")
        bpy.ops.render.render(write_still=True)
        print("Render:", scene.render.filepath)


main()
