"""Mate chassis corner for plywood panels, plus a slot fit test.

Usage: python corner.py   (needs: pip install manifold3d numpy)
Writes corner-normal-v3.stl, corner-thick-v3.stl and slot-test.stl next to this file.
All sizes in mm.

One corner joins three panels (two walls and the base or top). The panels
slide into slots and don't touch each other, so every panel is a plain
rectangle: panel size = box outer size - 2 * seat(wall).
"""

from pathlib import Path

import numpy as np
from manifold3d import Manifold

# ---- Plywood ----
SLOT = 4.4         # slot width for 4 mm ply; this printer prints tight

# ---- Corner ----
WALL = 2.5         # plastic on the outside of a slot (normal corner)
THICK_WALL = 3.5   # same, for the thick corner
INNER = 2.0        # extra plastic on the inside face of each slot (inside wall = wall + INNER)
DEPTH = 15.0       # how far a panel goes into its slot
BRIDGE = 2.1       # plastic between a panel's edge and the next panel = the gap you see along each edge
ROUND = 4.0        # radius on the three outer edges and the outer point
EDGE = 1.0         # radius on every other outside edge


def seat(wall):
    """How far in from the box's outer face a panel edge sits."""
    return wall + SLOT + BRIDGE


def rounded_box(size, r):
    """Box from 0 to size with all edges rounded to radius r."""
    spheres = [Manifold.sphere(r, 48).translate([r + i * (size - 2 * r), r + j * (size - 2 * r), r + k * (size - 2 * r)])
               for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    return Manifold.batch_hull(spheres)


def corner(wall=WALL):
    arm = wall + SLOT + wall + INNER       # thickness of each of the three arms
    size = seat(wall) + DEPTH              # outer size of the corner along each edge
    # A cube with the inside of the box removed leaves three arms (x, y and z walls).
    body = Manifold.cube([size] * 3) - Manifold.cube([size] * 3).translate([arm] * 3)
    # Each arm gets a slot open towards the two box edges that leave this corner.
    for axis in range(3):
        cut = [DEPTH + 1] * 3
        cut[axis] = SLOT
        at = [seat(wall)] * 3
        at[axis] = wall
        body -= Manifold.cube(cut).translate(at)
    # Soften it: a big radius on the outside corner, a small one on the other outside edges.
    body ^= rounded_box(size + 2 * ROUND, ROUND)
    body ^= rounded_box(size, EDGE)
    return body


def slot_test():
    """Five slots at 3.9 / 4.1 / 4.3 / 4.5 / 4.7; notches on the edge count them."""
    widths = [3.9, 4.1, 4.3, 4.5, 4.7]
    depth = 10.0
    pitch, width, height = 10.0, 12.0, depth + WALL
    strip = Manifold.cube([pitch * len(widths) + 2 * WALL, width, height])
    for i, w in enumerate(widths):
        x = WALL + i * pitch + (pitch - w) / 2
        strip -= Manifold.cube([w, width + 2, depth + 1]).translate([x, -1, WALL])
        for n in range(i + 1):
            left = x + w / 2 - (i + 1) * 0.7 + n * 1.4 + 0.3
            strip -= Manifold.cube([0.8, 1.2, 1.4]).translate([left, -0.01, 0.6])
    return strip


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
        f.write(b"Mate chassis".ljust(80, b" "))
        f.write(np.uint32(len(tris)).tobytes())
        f.write(record.tobytes())


if __name__ == "__main__":
    here = Path(__file__).parent
    parts = [("corner-normal-v3", corner(WALL)), ("corner-thick-v3", corner(THICK_WALL)), ("slot-test", slot_test())]
    for name, part in parts:
        write_stl(part, here / f"{name}.stl")
        lo, hi = part.bounding_box()[:3], part.bounding_box()[3:]
        size = " x ".join(f"{h - l:.1f}" for l, h in zip(lo, hi))
        print(f"{name}.stl  {size} mm  volume {part.volume() / 1000:.1f} cm3  {part.num_tri()} triangles")
    for name, wall in [("normal", WALL), ("thick", THICK_WALL)]:
        print(f"{name}: panel size = box outer size - {2 * seat(wall):.0f} mm, {len(corner(wall).decompose())} piece(s)")
