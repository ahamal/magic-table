"""Head marker plate: a flat plate that bolts along a 20x20 extrusion and holds
the printed ArUco head marker.

Usage: python marker_mount.py   (needs: pip install manifold3d numpy)
Writes marker-mount.stl next to this file. All sizes in mm.

The plate lies flat along the extrusion, so the extrusion backs it over its whole
length; two M5 bolts into T-nuts keep it from turning. The marker sits between
the bolts, centred by four corner guides.
"""

from pathlib import Path

import numpy as np
from manifold3d import Manifold

# ---- Marker (printed on paper, white border included) ----
MARKER = 33.0       # outer size of the printed square (25 mm black + 4 mm border)
MARKER_GAP = 0.6    # paper slides between the guides

# ---- Plate ----
WIDTH = 38.0        # across the extrusion (20 mm face, overhangs both sides)
END = 13.0          # bolt tab at each end
THICK = 4.0
GUIDE = 6.0         # length of each arm of a corner guide
GUIDE_W = 1.2
GUIDE_H = 0.8       # a little above the paper

# ---- Bolts ----
BOLT_D = 5.5        # M5 clearance
CLEARANCE = 0.5     # this printer prints holes tight (wheel fit test: 0.5 best)


def plate():
    pocket = MARKER + MARKER_GAP
    length = 2 * END + WIDTH
    body = Manifold.cube([WIDTH, length, THICK])

    # four L-shaped corner guides around the marker area
    x0, y0 = (WIDTH - pocket) / 2, END + (WIDTH - pocket) / 2
    for cx, sx in ((x0, 1), (x0 + pocket, -1)):
        for cy, sy in ((y0, 1), (y0 + pocket, -1)):
            ax = Manifold.cube([GUIDE + GUIDE_W, GUIDE_W, GUIDE_H])  # includes the corner square
            ay = Manifold.cube([GUIDE_W, GUIDE, GUIDE_H])
            ax = ax.translate([cx - GUIDE_W if sx > 0 else cx - GUIDE, cy - GUIDE_W if sy > 0 else cy, THICK])
            ay = ay.translate([cx - GUIDE_W if sx > 0 else cx, cy if sy > 0 else cy - GUIDE, THICK])
            body += ax + ay

    r = (BOLT_D + CLEARANCE) / 2
    for y in (END / 2, length - END / 2):
        body -= Manifold.cylinder(THICK + 4, r, r, 64).translate([WIDTH / 2, y, -1])
    return body


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
        f.write(b"Head marker plate".ljust(80, b" "))
        f.write(np.uint32(len(tris)).tobytes())
        f.write(record.tobytes())


if __name__ == "__main__":
    part = plate()
    path = Path(__file__).parent / "marker-mount.stl"
    write_stl(part, path)
    lo, hi = part.bounding_box()[:3], part.bounding_box()[3:]
    size = " x ".join(f"{h - l:.1f}" for l, h in zip(lo, hi))
    print(f"{path.name}  {size} mm  volume {part.volume() / 1000:.1f} cm3  {part.num_tri()} triangles")
