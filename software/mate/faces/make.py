"""Build Mate's ready-made screen animations.

Each face becomes <name>.bin (frames for POST /screen, 1024 bytes each) and <name>.png
(a preview strip of a few frames). Run from anywhere:

    python3 software/mate/faces/make.py

Needs Pillow (pip install pillow). The frame rate to send with each face is in FACES.
"""

from pathlib import Path

from PIL import Image, ImageDraw

W, H = 128, 64
HERE = Path(__file__).parent


def frame():
    im = Image.new("1", (W, H), 0)
    return im, ImageDraw.Draw(im)


# ---------------------------------------------------------------- eyes

EW, EH, GAP = 34, 40, 18  # eye size and the gap between them


def eye_frame(dx=0, dy=0, open_=1.0):
    im, d = frame()
    h = max(3, int(EH * open_))
    cx, cy = W // 2 + dx, H // 2 + dy
    for side in (-1, 1):
        x0 = cx + side * (GAP // 2 + EW // 2) - EW // 2
        y0 = cy - h // 2
        d.rounded_rectangle([x0, y0, x0 + EW, y0 + h], radius=min(10, h // 2), fill=1)
        if open_ > 0.5:  # a dark shine cut out of each eye
            px, py = x0 + EW // 2 + dx // 2 + 6, y0 + 8
            d.ellipse([px - 4, py - 4, px + 4, py + 4], fill=0)
    return im


def eyes():
    blink = [eye_frame(open_=o) for o in (0.6, 0.2, 0.05, 0.2, 0.6)]
    f = [eye_frame()] * 6 + blink + [eye_frame()] * 4
    f += [eye_frame(dx=d) for d in (-6, -12, -16)] + [eye_frame(dx=-16)] * 5 + [eye_frame(dx=d) for d in (-10, -4)]
    f += [eye_frame()] * 3
    f += [eye_frame(dx=d) for d in (6, 12, 16)] + [eye_frame(dx=16)] * 5 + [eye_frame(dx=d) for d in (10, 4)]
    f += [eye_frame()] * 3
    f += [eye_frame(dy=-6)] * 3 + [eye_frame(dy=-3)] + [eye_frame()] * 2
    f += [eye_frame(open_=o) for o in (0.6, 0.2, 0.05, 0.2, 0.6, 1, 0.2, 0.05, 0.6)]
    return f


# ---------------------------------------------------------------- chicken

def chicken_frame(peck):
    im, d = frame()
    d.line([(0, 60), (127, 60)], fill=1)  # ground and seeds
    for x in (20, 26, 100, 108, 113):
        d.point((x, 58), fill=1)
    d.polygon([(38, 26), (28, 14), (34, 30)], fill=1)  # tail
    d.polygon([(38, 30), (24, 22), (34, 34)], fill=1)
    d.ellipse([34, 22, 78, 52], outline=1, fill=0, width=2)  # body
    d.arc([44, 30, 66, 46], 200, 340, fill=1, width=2)  # wing
    d.arc([46, 34, 64, 46], 200, 340, fill=1)
    for x in (52, 62):  # legs and feet
        d.line([(x, 51), (x, 59)], fill=1, width=2)
        d.line([(x - 3, 59), (x + 4, 59)], fill=1)
    if peck:
        d.line([(74, 38), (86, 48)], fill=1, width=3)
        hx, hy = 90, 50
    else:
        d.line([(72, 30), (78, 20)], fill=1, width=3)
        hx, hy = 80, 16
    d.ellipse([hx - 7, hy - 7, hx + 7, hy + 7], outline=1, fill=0, width=2)  # head
    for cx, cy in ((hx - 4, hy - 7), (hx, hy - 9), (hx + 4, hy - 7)):  # comb
        d.ellipse([cx - 2, cy - 3, cx + 2, cy + 2], fill=1)
    d.polygon([(hx + 6, hy - 2), (hx + 13, hy + 1), (hx + 6, hy + 3)], fill=1)  # beak
    d.ellipse([hx + 4, hy + 3, hx + 8, hy + 9], fill=1)  # wattle
    d.rectangle([hx + 1, hy - 3, hx + 3, hy - 1], fill=1)  # eye
    return im


def chicken():
    up, down = chicken_frame(False), chicken_frame(True)
    return [up, up, down, up]


# ---------------------------------------------------------------- portrait

def portrait_frame(blink=False, wave=False):
    """A cartoon of a person with glasses and a big smile, in a hoodie over a T-shirt."""
    im, d = frame()
    cx = 64
    d.pieslice([cx - 44, 46, cx + 44, 100], 180, 360, fill=1)  # hoodie shoulders
    d.pieslice([cx - 40, 50, cx + 40, 100], 180, 360, fill=0)
    d.polygon([(cx - 12, 50), (cx + 12, 50), (cx, 63)], fill=1)  # T-shirt
    d.line([(cx - 16, 49), (cx - 6, 63)], fill=1)  # hoodie edges
    d.line([(cx + 16, 49), (cx + 6, 63)], fill=1)
    d.rectangle([cx - 5, 42, cx + 5, 50], outline=1, fill=0)  # neck
    d.ellipse([cx - 19, 6, cx + 19, 46], outline=1, fill=0, width=2)  # head
    hair, hd = frame()  # hair: cap and fringe, hatched so it reads dark, not white
    hd.chord([cx - 20, 3, cx + 20, 36], 180, 360, fill=1)
    hd.polygon([(cx - 20, 19), (cx - 8, 19), (cx - 13, 25)], fill=1)
    hd.polygon([(cx - 6, 19), (cx + 8, 19), (cx + 2, 24)], fill=1)
    hd.polygon([(cx + 9, 19), (cx + 20, 19), (cx + 17, 24)], fill=1)
    for y in range(H):
        for x in range(W):
            if hair.getpixel((x, y)) and (x + y) % 3 == 0:
                im.putpixel((x, y), 1)
    d.arc([cx - 20, 3, cx + 20, 36], 180, 360, fill=1)
    d.arc([cx - 24, 24, cx - 16, 34], 90, 270, fill=1, width=2)  # ears
    d.arc([cx + 16, 24, cx + 24, 34], 270, 90, fill=1, width=2)
    for ex in (cx - 9, cx + 9):  # glasses
        d.ellipse([ex - 7, 22, ex + 7, 33], outline=1, width=2)
        if blink:
            d.line([(ex - 3, 28), (ex + 3, 28)], fill=1)
        else:
            d.ellipse([ex - 2, 26, ex + 1, 29], fill=1)
    d.line([(cx - 2, 26), (cx + 2, 26)], fill=1)
    d.chord([cx - 9, 32, cx + 9, 42], 0, 180, fill=1)  # big smile
    d.chord([cx - 6, 33, cx + 6, 38], 0, 180, fill=0)
    if wave:
        d.line([(cx + 34, 54), (cx + 44, 34)], fill=1, width=3)  # arm
        d.ellipse([cx + 40, 26, cx + 50, 36], fill=1)  # palm
        for fx, fy in ((cx + 40, 20), (cx + 44, 18), (cx + 48, 19), (cx + 52, 23)):
            d.line([(cx + 45, 30), (fx, fy)], fill=1, width=2)  # fingers
        d.line([(cx + 40, 31), (cx + 36, 27)], fill=1, width=2)  # thumb
    return im


def portrait():
    rest, blink, wave = portrait_frame(), portrait_frame(blink=True), portrait_frame(wave=True)
    return [rest] * 8 + [blink] + [rest] * 3 + [wave, rest, wave, rest] + [rest] * 4


# ---------------------------------------------------------------- build

# name: (builder, fps to send it at, frame indexes for the preview)
FACES = {
    "eyes": (eyes, 12, [0, 8, 19, 34]),
    "chicken": (chicken, 3, [0, 2]),
    "portrait": (portrait, 6, [0, 8, 12]),
}


def main():
    for name, (build, fps, picks) in FACES.items():
        frames = build()
        assert len(frames) <= 64, f"{name}: {len(frames)} frames, Mate holds 64"
        # Pillow's 1-bit tobytes() is rows top to bottom, MSB = leftmost pixel: Mate's format.
        (HERE / f"{name}.bin").write_bytes(b"".join(f.tobytes() for f in frames))
        sheet = Image.new("1", (len(picks) * (W + 8) - 8, H), 0)
        for i, p in enumerate(picks):
            sheet.paste(frames[p], (i * (W + 8), 0))
        sheet.resize((sheet.width * 2, H * 2)).convert("L").save(HERE / f"{name}.png")
        print(f"{name}: {len(frames)} frames, send at {fps} fps")


if __name__ == "__main__":
    main()
