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


# ---------------------------------------------------------------- reactions
# Short play-once faces for Mate's gestures (the hub's /api/mate/gesture): they open from the
# plain eyes, play, and hold the last frame. All built from the same eye boxes as `eyes`.

def boxes(dx=0, dy=0):
    """The two eye boxes (x0, y0, x1, y1, side), side -1 = left eye, +1 = right."""
    cx, cy = W // 2 + dx, H // 2 + dy
    out = []
    for side in (-1, 1):
        x0 = cx + side * (GAP // 2 + EW // 2) - EW // 2
        out.append((x0, cy - EH // 2, x0 + EW, cy + EH // 2, side))
    return out


def two(draw_eye, dx=0, dy=0, extra=None):
    im, d = frame()
    for b in boxes(dx, dy):
        draw_eye(d, *b)
    if extra:
        extra(d)
    return im


def solid(d, x0, y0, x1, y1, side):
    d.rounded_rectangle([x0, y0, x1, y1], radius=10, fill=1)


def happy_eye(d, x0, y0, x1, y1, side):         # ∩: smiling eyes
    d.arc([x0, y0 + 10, x1, y0 + 10 + (x1 - x0)], 200, 340, fill=1, width=8)


def slanted(inner_down):
    def eye(d, x0, y0, x1, y1, side):
        solid(d, x0, y0, x1, y1, side)
        inner, outer = (x1, x0) if side < 0 else (x0, x1)
        low, high = (inner, outer) if inner_down else (outer, inner)
        out = 4 if low > high else -4                   # reach past the box so no edge is left
        d.polygon([(low + out, y0 - 4), (low + out, y0 + 24), (high - out, y0 - 4)], fill=0)
    return eye


def lidded(frac, look=0):
    def eye(d, x0, y0, x1, y1, side):
        solid(d, x0 + look, y0, x1 + look, y1, side)
        d.rectangle([x0 - 3 + look, y0 - 3, x1 + 3 + look, y0 + int((y1 - y0) * frac)], fill=0)
    return eye


def wide(pupil=0):
    def eye(d, x0, y0, x1, y1, side):
        cx, cy, r = (x0 + x1) // 2, (y0 + y1) // 2, 21
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=1)
        d.ellipse([cx - 5 + pupil, cy - 5, cx + 5 + pupil, cy + 5], fill=0)
    return eye


def line_eye(d, x0, y0, x1, y1, side):
    cy = (y0 + y1) // 2
    d.rounded_rectangle([x0 + 2, cy - 3, x1 - 2, cy + 3], radius=3, fill=1)


def squint_eye(look=0):
    def eye(d, x0, y0, x1, y1, side):
        cy = (y0 + y1) // 2
        d.rounded_rectangle([x0 + look, cy - 6, x1 + look, cy + 6], radius=6, fill=1)
    return eye


def laugh_eye(d, x0, y0, x1, y1, side):         # > <
    tip, back = (x1 - 4, x0 + 6) if side < 0 else (x0 + 4, x1 - 6)
    cy = (y0 + y1) // 2
    d.line([(back, cy - 13), (tip, cy), (back, cy + 13)], fill=1, width=7)


def heart(d, cx, cy, s):
    r = s // 4
    d.ellipse([cx - 2 * r, cy - r - r, cx, cy + r - r], fill=1)
    d.ellipse([cx, cy - r - r, cx + 2 * r, cy + r - r], fill=1)
    d.polygon([(cx - 2 * r + 1, cy - r + 2), (cx + 2 * r - 1, cy - r + 2), (cx, cy + 2 * r)], fill=1)


def heart_eye(s):
    def eye(d, x0, y0, x1, y1, side):
        heart(d, (x0 + x1) // 2, (y0 + y1) // 2, s)
    return eye


def zz(d, x, y, s):
    d.line([(x, y), (x + s, y), (x, y + s), (x + s, y + s)], fill=1, width=2)


def question(d, x, y):
    d.arc([x, y, x + 14, y + 14], 180, 90, fill=1, width=3)
    d.line([(x + 7, y + 14), (x + 7, y + 19)], fill=1, width=3)
    d.rectangle([x + 6, y + 23, x + 8, y + 25], fill=1)


def drop(d, x, y):
    d.polygon([(x, y), (x - 4, y + 8), (x + 4, y + 8)], fill=1)
    d.ellipse([x - 4, y + 5, x + 4, y + 13], fill=1)


def thumb(up=True):
    im, d = frame()
    d.rounded_rectangle([46, 28, 84, 58], radius=6, fill=1)        # fist
    for y in (36, 43, 50):                                           # finger creases
        d.line([(58, y), (84, y)], fill=0, width=2)
    d.rounded_rectangle([46, 6, 60, 34], radius=7, fill=1)          # thumb
    d.rectangle([34, 30, 44, 58], fill=1)                            # cuff
    return im if up else im.transpose(Image.Transpose.FLIP_TOP_BOTTOM)


def opener(target, n=3):
    """From the plain eyes into a face: a quick blink, then the face held."""
    return [eye_frame(), eye_frame(open_=0.3), eye_frame(open_=0.05)] + [target] * n


def happy():
    return opener(two(happy_eye)) + [two(happy_eye, dy=-3), two(happy_eye)] * 2


def sad():
    f = two(slanted(False), dy=4)
    return opener(f) + [two(slanted(False), dy=4, extra=lambda d, y=y: drop(d, 24, y)) for y in (36, 40, 44, 48)] + [f]


def angry():
    return opener(two(slanted(True))) + [two(slanted(True), dx=x) for x in (-1, 1, -1, 1, 0)]


def shocked():
    return [eye_frame(), two(wide()), two(wide(), dy=-3), two(wide(), dy=-1)] + [two(wide())] * 6


def smug():
    return opener(two(lidded(0.5, 6)), 2) + [two(lidded(0.55, 8))] * 4


def meh():
    return opener(two(lidded(0.5)))


def sleepy():
    return opener(two(line_eye, dy=6)) + [two(line_eye, dy=6, extra=lambda d, k=k: [zz(d, 96 + 6 * i, 14 - 6 * i, 6 + 2 * i)
                                                                               for i in range(k)]) for k in (1, 2, 3, 3)]


def love():
    return opener(two(heart_eye(30)), 1) + [two(heart_eye(s)) for s in (34, 30, 34, 30, 34)]


def thinking():
    look = lambda k: two(lidded(0.3, 6), dy=-4, extra=lambda d: [d.ellipse([100 + 8 * i, 54, 104 + 8 * i, 58], fill=1)
                                                                  for i in range(k)])
    return opener(look(0), 1) + [look(k) for k in (1, 2, 3, 0, 1, 2, 3)]


def nervous():
    f = lambda dx, y: two(solid_small, dx=dx, extra=lambda d: drop(d, 120, y))
    return [eye_frame()] + [f(dx, y) for dx, y in zip((-2, 2, -2, 2, -2, 2, -2, 2, 0), range(6, 33, 3))]


def solid_small(d, x0, y0, x1, y1, side):
    d.rounded_rectangle([x0 + 4, y0 + 6, x1 - 4, y1 - 6], radius=8, fill=1)


def wink():
    def w(d, x0, y0, x1, y1, side):
        (happy_eye if side > 0 else solid)(d, x0, y0, x1, y1, side)
    return [eye_frame(), two(w), two(w), two(w), eye_frame()]


def confused():
    def c(d, x0, y0, x1, y1, side):
        (solid if side < 0 else solid_small)(d, x0, y0, x1, y1, side)
    return opener(two(c, dx=-8, extra=lambda d: question(d, 110, 4)), 6)


def x_eye(d, x0, y0, x1, y1, side):              # x: knocked out
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    d.line([(cx - 13, cy - 13), (cx + 13, cy + 13)], fill=1, width=7)
    d.line([(cx - 13, cy + 13), (cx + 13, cy - 13)], fill=1, width=7)


def dizzy():
    """Back from a blackout: x x, a wobble, then blinking awake."""
    return [two(x_eye)] * 3 + [two(x_eye, dx=x, dy=y) for x, y in ((-3, 1), (3, -1), (-3, 1), (3, -1), (0, 0))] \
        + [two(x_eye)] * 4 + [eye_frame(open_=0.05), eye_frame(open_=0.3), eye_frame(open_=0.05), eye_frame()]


def laughing():
    return opener(two(laugh_eye), 1) + [two(laugh_eye, dy=y) for y in (-4, 0, -4, 0, -4, 0)]


def alert():
    return [eye_frame(), eye_frame(dy=-3), eye_frame(dy=-2)] + [eye_frame(dy=-2)] * 3


def determined():
    return opener(two(slanted(True), dy=2)) + [two(lidded(0.25), dy=2)]


def sneaky():
    return opener(two(squint_eye()), 1) + [two(squint_eye(x)) for x in (-6, -12, -12, -12, -6, 0, 6, 12, 12, 12, 6, 0)]


def suspicious():
    return opener(two(squint_eye(), dy=-2)) + [two(squint_eye(x), dy=-2) for x in (8, 12, 12, 12, 0, -12, -12, -12, 0)]


def blank():
    return opener(two(line_eye), 6)


def yes():
    return [eye_frame(dy=y) for y in (0, 5, 8, 5, 0, 5, 8, 5, 0)] + [two(happy_eye)] * 3


def no():
    return [eye_frame(dx=x) for x in (0, -8, -14, -8, 0, 8, 14, 8, 0, -8, -14, -8, 0)]


def eyeroll():
    path = [(0, 0), (6, -6), (0, -9), (-8, -7), (-10, -2), (-6, 2)]
    return [eye_frame(dx=x, dy=y) for x, y in path] + [two(lidded(0.45))] * 4


def humble():
    def closed(d, x0, y0, x1, y1, side):
        d.arc([x0, y0 - 6, x1, y0 - 6 + (x1 - x0)], 20, 160, fill=1, width=7)
    return opener(two(closed, dy=2), 6)


def thumbs_up():
    return [eye_frame(), eye_frame(open_=0.3)] + [thumb(True)] * 4


def thumbs_down():
    return [eye_frame(), eye_frame(open_=0.3)] + [thumb(False)] * 4


REACTIONS = [happy, sad, angry, shocked, smug, meh, sleepy, love, thinking, nervous, wink, confused, laughing,
             alert, determined, sneaky, suspicious, blank, yes, no, eyeroll, humble, thumbs_up, thumbs_down, dizzy]


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
    # the reactions: reactions/<name>.bin, played once at 10 fps; one sheet of their last frames
    (HERE / "reactions").mkdir(exist_ok=True)
    sheet = Image.new("1", (6 * (W + 8) - 8, 4 * (H + 8) - 8), 0)
    for i, build in enumerate(REACTIONS):
        frames = build()
        assert len(frames) <= 64, f"{build.__name__}: {len(frames)} frames, Mate holds 64"
        (HERE / "reactions" / f"{build.__name__}.bin").write_bytes(b"".join(f.tobytes() for f in frames))
        sheet.paste(frames[-1], ((i % 6) * (W + 8), (i // 6) * (H + 8)))
    sheet.resize((sheet.width * 2, sheet.height * 2)).convert("L").save(HERE / "reactions.png")
    print(f"{len(REACTIONS)} reactions in reactions/, send at 10 fps, X-Repeat 1")

if __name__ == "__main__":
    main()
