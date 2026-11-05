"""More of Esper's reaction faces (Nov 4, for the poker demo), drawn with make.py's eyes.

    python3 software/esper/faces/more_faces.py

Writes reactions/<name>.bin (10 fps; the hub loops them while something slow runs):
  curious   one eye wide with a raised brow, one narrowed; pupils dart; a '?' pops in
  cheer     happy arched eyes hopping, blush, sparkles popping in turn
  focused   narrowed eyes scanning left to right, a scan line sweeping (while SAM looks)
  suspense  eyes slowly widening and trembling (a card about to turn)
"""
import math
from pathlib import Path

from make import EH, EW, GAP, H, W, boxes, frame, happy_eye, two

HERE = Path(__file__).parent


def curious():
    def draw(d, look, tilt, q):
        for cx, cy, r, lid in ((40, 34 - tilt, 19, 0), (88, 34 + tilt, 15, 6)):
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=1)
            pr = 6 if r > 16 else 5
            px = cx + look * (r - pr - 3) // 3
            d.ellipse([px - pr, cy - pr + 2, px + pr, cy + pr + 2], fill=0)
            d.ellipse([px + 1, cy - 3, px + 3, cy - 1], fill=1)
            if lid:
                d.rectangle([cx - r - 2, cy - r - 2, cx + r + 2, cy - r + lid], fill=0)
        d.arc([22, 4 - tilt, 58, 22 - tilt], 200, 340, fill=1, width=3)
        if q:
            x, y, s = 112, 12, q
            d.arc([x - 4 * s, y - 5 * s, x + 4 * s, y + 3 * s], 180, 60, fill=1, width=2)
            d.line([x + 1, y + 3 * s, x, y + 5 * s], fill=1, width=2)
            d.ellipse([x - 1, y + 7 * s - 1, x + 1, y + 7 * s + 1], fill=1)
    out = []
    for i, look in enumerate([0, 0, -3, -3, -3, 0, 3, 3, 3, 3, 0, 0, -1, 1, 0, 0, 0, 0, 0, 0]):
        im, d = frame()
        draw(d, look, 3 if 10 <= i < 16 else 0, 0 if i < 12 else (1 if i < 14 else 2))
        out.append(im)
    return out


def cheer():
    def star(d, x, y, r, diag):
        if diag:
            k = int(r * .7)
            d.line([x - k, y - k, x + k, y + k], fill=1, width=2); d.line([x - k, y + k, x + k, y - k], fill=1, width=2)
        else:
            d.line([x - r, y, x + r, y], fill=1, width=2); d.line([x, y - r, x, y + r], fill=1, width=2)
        d.ellipse([x - 1, y - 1, x + 1, y + 1], fill=1)
    spots = [(9, 9), (119, 11), (11, 55), (117, 53), (64, 6)]
    out = []
    for i in range(20):
        dy = -7 if i % 4 < 2 else 1
        def extra(d, i=i, dy=dy):
            for x in (22, 94):
                for j in range(3):
                    d.line([x + j * 5, 50 + dy, x + j * 5 + 3, 46 + dy], fill=1)
            for k, (x, y) in enumerate(spots):
                ph = (i + k * 2) % 6
                if ph < 5:
                    star(d, x, y, [2, 4, 6, 4, 2][ph], ph % 2 == 1)
        out.append(two(happy_eye, dy=dy - 4, extra=extra))
    return out


def focused():
    out = []
    for i in range(20):
        im, d = frame()
        look = round(10 * math.sin(i * 2 * math.pi / 20))
        for x0, y0, x1, y1, side in boxes():
            d.rounded_rectangle([x0, y0 + 12, x1, y1 - 12], radius=6, fill=1)       # narrowed
            px = (x0 + x1) // 2 + look
            d.ellipse([px - 5, (y0 + y1) // 2 - 5, px + 5, (y0 + y1) // 2 + 5], fill=0)
            d.line([x0 - 2, y0 + 10, x1 + 2, y0 + 14 - 3 * side], fill=1, width=3)  # knit brows
        sx = 8 + (i * 6) % 112                                                       # scan line
        d.line([sx, 58, sx + 10, 58], fill=1, width=2)
        out.append(im)
    return out


def suspense():
    out = []
    for i in range(20):
        im, d = frame()
        r = 10 + min(i, 12)                     # widening
        jit = (i % 2) * 2 - 1 if i > 6 else 0  # trembling
        for x0, y0, x1, y1, side in boxes():
            cx, cy = (x0 + x1) // 2 + jit, (y0 + y1) // 2
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=1)
            d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=0)
        if i > 10:                              # a bead of sweat
            d.ellipse([112, 8 + (i - 10), 117, 15 + (i - 10)], fill=1)
        out.append(im)
    return out


if __name__ == "__main__":
    for f in (curious, cheer, focused, suspense):
        frames = f()
        (HERE / "reactions" / f"{f.__name__}.bin").write_bytes(b"".join(x.tobytes() for x in frames))
        print(f.__name__, len(frames), "frames")
