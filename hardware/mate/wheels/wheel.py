"""Mate drive wheel for the 28BYJ-48 shaft, plus a bore fit test.

Usage: python wheel.py   (needs: pip install manifold3d numpy)
Writes wheel-70.stl and fit-test.stl next to this file. All sizes in mm.
"""

from pathlib import Path

import numpy as np
from manifold3d import CrossSection, Manifold, OpType

# ---- 28BYJ-48 shaft: 5 mm round, 3 mm across the flats ----
SHAFT_D = 5.0
SHAFT_FLATS = 3.0
CLEARANCE = 0.5  # added to both; this printer prints holes tight (fit test: 0.5 best)

# ---- Wheel ----
WHEEL_D = 70.0     # 35 mm radius: ~4.3 cm/s at 800 half-steps/s
WIDTH = 8.0
RIM = 4.0          # radial thickness of the rim
WEB = 3.0          # thickness of the disc between hub and rim
HUB_D = 13.0
GROOVE_W = 2.5     # tire groove for an O-ring or rubber bands
GROOVE_DEPTH = 1.2
HOLES = 6          # lightening holes in the web
HOLE_D = 12.0
CHAMFER = 0.5      # bore entry chamfer, also hides elephant's foot

SEG = 128


def bore(clearance, height):
    """Double-D shaft hole, centred on the origin, from z=0 up."""
    r = (SHAFT_D + clearance) / 2
    flats = SHAFT_FLATS + clearance
    profile = CrossSection.circle(r, SEG) ^ CrossSection.square([flats, 2 * r + 2], center=True)
    hole = profile.extrude(height + 2).translate([0, 0, -1])
    entry = Manifold.cylinder(CHAMFER + 0.01, r + CHAMFER, r, SEG).translate([0, 0, -0.01])
    return hole + entry


def wheel():
    r = WHEEL_D / 2
    rim = Manifold.cylinder(WIDTH, r, r, SEG) - Manifold.cylinder(WIDTH + 2, r - RIM, r - RIM, SEG).translate([0, 0, -1])
    web = Manifold.cylinder(WEB, r - RIM + 0.5, r - RIM + 0.5, SEG)
    hub = Manifold.cylinder(WIDTH, HUB_D / 2, HUB_D / 2, SEG)
    body = Manifold.batch_boolean([rim, web, hub], OpType.Add)

    groove = (Manifold.cylinder(GROOVE_W, r + 1, r + 1, SEG)
              - Manifold.cylinder(GROOVE_W + 2, r - GROOVE_DEPTH, r - GROOVE_DEPTH, SEG).translate([0, 0, -1]))
    body -= groove.translate([0, 0, (WIDTH - GROOVE_W) / 2])

    ring_r = (HUB_D / 2 + (r - RIM)) / 2
    for i in range(HOLES):
        a = 2 * np.pi * i / HOLES
        hole = Manifold.cylinder(WEB + 2, HOLE_D / 2, HOLE_D / 2, 64)
        body -= hole.translate([ring_r * np.cos(a), ring_r * np.sin(a), -1])

    return body - bore(CLEARANCE, WIDTH)


def fit_test():
    """Three bores at +0.4 / +0.5 / +0.6; notches on the edge count them."""
    clearances = [0.4, 0.5, 0.6]
    pitch, depth = 14.0, 6.0
    length = pitch * len(clearances)
    plate = Manifold.cube([length, 12, depth]).translate([-pitch / 2, -6, 0])
    for i, c in enumerate(clearances):
        x = i * pitch
        plate -= bore(c, depth).translate([x, 0, 0])
        for n in range(i + 1):
            notch = Manifold.cube([1.2, 1.6, depth + 2]).translate([x - 2.6 + n * 2.2, 5, -1])
            plate -= notch
    return plate


def write_stl(manifold, path):
    mesh = manifold.to_mesh()
    verts = np.asarray(mesh.vert_properties)[:, :3].astype(np.float32)
    tris = np.asarray(mesh.tri_verts)
    v = verts[tris]
    normals = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    normals /= np.linalg.norm(normals, axis=1, keepdims=True) + 1e-12
    record = np.zeros(len(tris), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    record["n"] = normals
    record["v"] = v
    with open(path, "wb") as f:
        f.write(b"Mate wheel".ljust(80, b" "))
        f.write(np.uint32(len(tris)).tobytes())
        f.write(record.tobytes())


if __name__ == "__main__":
    here = Path(__file__).parent
    for name, part in [("wheel-70", wheel()), ("fit-test", fit_test())]:
        write_stl(part, here / f"{name}.stl")
        lo, hi = part.bounding_box()[:3], part.bounding_box()[3:]
        size = " x ".join(f"{h - l:.1f}" for l, h in zip(lo, hi))
        print(f"{name}.stl  {size} mm  volume {part.volume() / 1000:.1f} cm3  {part.num_tri()} triangles")
