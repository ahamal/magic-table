"""The table's eyes: what's on the board (Muse Spark), where it is for picking (SAM 3.1).

see(): Muse Spark looks at one picture and names the kinds of things on the board, each with a
backup name ("white object"): SAM is fussy about names (the AirPods case was only ever found
from above as "white object").

find(): SAM proposes matches in one camera's picture (cam 1 by default; 0, or Mate's).
Muse Spark checks numbered outlines in the whole scene against the original requested object,
rejecting robot parts and ambiguous matches before returning any pick targets. For
each thing: its outline and, for a calibrated camera, its footprint on the board in mm (the
outline mapped onto the board: x, y, w, h, angle), whether it's on the board, and where the cup
goes: the footprint centre, not the middle of what the camera sees (from cam 1's 48 degrees
that's partway down a tall thing's near side, and put the cup 20 mm off). No height: one
camera can't tell (two cameras could: carving gave an AirPods case 21.0 mm vs 21, Nov 2).

check: after a pick, compare a fresh picture with find's, inside the item's outline, to see
whether it really left its spot (same camera; no API call).

ask: a question for Muse Spark about each thing found (its crop, so the answer is tied to a
place on the board) or about a whole picture. SAM says where things are, not which card or
what colour. "minimal" thinking is ~1 s a crop and reads cards as well as the default effort
(up to 15 s).

Both go to Meta's Model API (Responses API; SAM's segmentation text is decoded by Meta's
meta_sam_parser). Key: MODEL_API_KEY, as for speech-to-text. Cameras recalibrated over the
whole board for this (a 100 mm grid was 20 mm off at its edges).
"""

import asyncio
import base64
import json
import os
import time
from pathlib import Path

import cv2
import numpy as np

try:
    from meta_sam_parser import decode_mask_to_raster, image_segmentation_format, parse_responses_stream
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

from vision import project, to_xy

URL = "https://api.meta.ai/v1"
MODEL = "sam-3.1"
MUSE = "muse-spark-1.3"
EFFORTS = ("minimal", "low", "medium", "high")
CROP_PAD = 12    # px around a thing's box in the crop sent with a question
EDGE_MM = 20     # how far past the cup bounds something still counts as on the board
ROUND_FILL = 0.86     # a footprint filling less of its rectangle than this is round (a circle: 0.79)
ROUND_ASPECT = 0.75   # ...if it's about as wide as long (cam 1 stretches a chip ~10% along its view)


class EyesError(Exception):
    pass


async def _events(stream):
    """The SDK's events as the plain dicts the parser takes. The API ends a text lane with
    `response.content_part.done` but not `response.output_text.done`, which the parser waits
    for, so make one (as Meta's cookbook does)."""
    done = set()
    async for event in stream:
        data = event.model_dump() if hasattr(event, "model_dump") else dict(event)
        lane = (data.get("item_id"), data.get("output_index"), data.get("content_index"))
        if data.get("type") == "response.output_text.done":
            if lane not in done:
                done.add(lane)
                yield data
            continue
        yield data
        part = data.get("part")
        if (data.get("type") == "response.content_part.done" and lane not in done and isinstance(part, dict)
                and part.get("type") == "output_text" and isinstance(part.get("text"), str)):
            done.add(lane)
            yield {"type": "response.output_text.done", "item_id": data.get("item_id"),
                   "output_index": data.get("output_index"), "content_index": data.get("content_index"),
                   "text": part["text"]}


def _client():
    if AsyncOpenAI is None:
        raise EyesError("the hub needs openai and meta_sam_parser (pip install -r requirements.txt)")
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        raise EyesError("MODEL_API_KEY isn't set on the hub (see the hub README)")
    return AsyncOpenAI(base_url=URL, api_key=key)


def _data_url(jpeg):
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")


async def ask(jpeg, question, effort="minimal"):
    """Ask Muse Spark one question about one picture. Returns its answer as text."""
    async with _client() as api:
        r = await api.responses.create(model=MUSE, reasoning={"effort": effort}, input=[{
            "role": "user", "content": [{"type": "input_text", "text": question},
                                        {"type": "input_image", "image_url": _data_url(jpeg)}]}])
    return r.output_text.strip()


def crop(img, box, pad=CROP_PAD):
    """One thing cut out of the picture (with a margin), as a JPEG."""
    l, t, r, b = box
    c = img[max(0, t - pad):b + pad, max(0, l - pad):r + pad]
    return cv2.imencode(".jpg", c, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()


async def segment(jpeg, phrase):
    """One phrase on one JPEG -> [(box (l, t, r, b), mask as a 0/1 array the size of the box)]."""
    async with _client() as api:
        stream = await api.responses.create(model=MODEL, stream=True, input=[{
            "type": "message", "role": "user",
            "content": [{"type": "input_text", "text": phrase}, {"type": "input_image", "image_url": _data_url(jpeg)}]}])
        events = _events(stream)
        try:
            result = await parse_responses_stream(events, image_segmentation_format()).final_result()
        finally:
            await events.aclose()
            await stream.close()
    if result.outcome.status != "completed":
        raise EyesError(f"SAM didn't finish: {getattr(result.outcome, 'reason', result.outcome.status)}")
    boxes = {r.object_id: r for r in result.records if r.kind == "box"}
    out = []
    for r in result.records:
        b = boxes.get(r.object_id)
        if r.kind != "mask" or b is None:
            continue
        m = np.frombuffer(bytes(decode_mask_to_raster(r.mask)), np.uint8).reshape(r.mask.height, r.mask.width)
        out.append(((b.left, b.top, b.right, b.bottom), m))
    return out


def describe(box, mask, P=None, z=None, bounds=None):
    """One match: its box, outline (pixels, simplified) and, with a camera model, where it is
    on the board plane Z = z."""
    l, t = box[0], box[1]
    cs, _ = cv2.findContours((mask > 0).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return None
    c = max(cs, key=cv2.contourArea)
    outline = cv2.approxPolyDP(c, 1.5, True).reshape(-1, 2) + (l, t)
    obj = {"box": [int(v) for v in box], "outline": outline.tolist(), "pixels": int((mask > 0).sum())}
    if P is not None and z is not None:
        q = to_xy(P, (c.reshape(-1, 2) + (l, t)).astype(float), z).astype(np.float32)
        (cx, cy), (w, h), ang = cv2.minAreaRect(q)
        if w < h:
            ang += 90                                  # the angle of the long side
        obj["board"] = {"x": round(float(cx), 1), "y": round(float(cy), 1), "w": round(float(min(w, h)), 1),
                        "h": round(float(max(w, h)), 1), "angle": round(float(ang % 180), 1)}
        if w * h and cv2.contourArea(q) / (w * h) < ROUND_FILL and min(w, h) / max(w, h) > ROUND_ASPECT:
            obj["board"]["round"] = True               # a chip, a coin, a cup: w is its diameter
        if bounds:
            obj["on_board"] = bool(bounds[0] - EDGE_MM <= cx <= bounds[1] + EDGE_MM and
                                   bounds[2] - EDGE_MM <= cy <= bounds[3] + EDGE_MM)
    return obj


# Height from the side. Cam 1 says where a thing is and its footprint; cam 0, low and from the
# side, sees how tall it stands. A row v of a calibrated camera is a plane through it,
# (P[1] - v P[2]) . [X, Y, Z, 1] = 0, so a point sliding along a line lands on that row at one
# t, in closed form. Two solves per thing: slide the footprint along cam 0's line of sight until
# its near edge, on the board, sits on the bottom row of cam 0's outline (that absorbs cam 1's
# few-mm error in where it is), then raise the far edge, slid the same, until it's on the top row.
SIDE_SLIDE = 12.0    # mm: sliding more than this means cam 0 sees something else, or it's hidden
SIDE_MATCH = 30      # px: a cam 0 outline's bottom must be this close to where the footprint lands
SIDE_EDGE = 2        # px: an outline this close to the picture's edge is cut off


def cam_centre(P):
    """Where a calibrated camera is (gantry X, Y, Z)."""
    return -np.linalg.solve(P[:, :3], P[:, 3])


def row_solve(P, v, base, step):
    """t at which base + t * step lands on picture row v."""
    a = P[1] - v * P[2]
    return float(-(a @ np.r_[base, 1.0]) / (a[:3] @ step))


def _sight(P0, c):
    """Cam 0's line of sight to c, flat on the board (a unit x, y vector)."""
    d = c - cam_centre(P0)[:2]
    return d / np.linalg.norm(d)


def side_height(P0, mask, poly, tz, P1=None):
    """How tall a thing stands, from cam 0's outline of it (picture-sized 0/1 array) and its
    footprint on the board (poly: x, y points, cam 1's outline mapped onto the board): (height
    mm, slide mm along cam 0's line of sight), or None if the outline is cut off by the
    picture's edge. Cam 1 sees a thing's side too, which stretches the footprint away from it
    by height x cot(cam 1's angle); with P1 that is taken off the far edge."""
    ys, xs = np.nonzero(mask)
    if len(ys) < 30 or ys.min() < SIDE_EDGE or ys.max() > mask.shape[0] - 1 - SIDE_EDGE \
            or xs.min() < SIDE_EDGE or xs.max() > mask.shape[1] - 1 - SIDE_EDGE:
        return None
    poly = np.asarray(poly, float)
    c = poly.mean(axis=0)
    d = _sight(P0, c)
    reach = (poly - c) @ d
    stretch = 0.0
    if P1 is not None:
        C1 = cam_centre(P1)
        d1 = c - C1[:2]
        stretch = max(0.0, d @ d1 / np.linalg.norm(d1)) * np.linalg.norm(d1) / (C1[2] - tz)
    near = c + reach.min() * d
    top = 0.0
    for _ in range(3):                                  # the stretch depends on the height
        far = c + (reach.max() - stretch * max(top, 0.0)) * d
        slide = row_solve(P0, ys.max() + .5, np.r_[near, tz], np.r_[d, 0.0])
        top = row_solve(P0, ys.min() - .5, np.r_[far + slide * d, tz], np.array([0.0, 0.0, 1.0]))
    return top, slide


# Height from one camera, for round things of a known size (a chip stack, a can). Mapped flat
# onto the board, an angled camera's outline of a tall thing is stretched away from the camera
# (it sees the side, and the top lands too far) and its centre is pulled with it. An upright
# cylinder's outline is the hull of its bottom and top circles, so with the diameter known, the
# x, y and height whose outline best covers what the camera sees are where it stands and how tall.
UPRIGHT_FIT = 0.85   # IoU: a worse best fit means it isn't one clean cylinder (touching stacks, cut off)


def cylinder_outline(P, x, y, r, h, tz, n=48):
    """The hull of an upright cylinder's bottom and top circles, in picture pixels."""
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    ring = np.c_[x + r * np.cos(a), y + r * np.sin(a)]
    pts = np.r_[np.c_[ring, np.full(n, tz)], np.c_[ring, np.full(n, tz + h)]]
    q = (P @ np.c_[pts, np.ones(len(pts))].T).T
    return cv2.convexHull((q[:, :2] / q[:, 2:]).astype(np.float32)).reshape(-1, 2)


def box_outline(P, x, y, w, l, angle, h, tz):
    """The hull of an upright box's 8 corners (footprint w x l, its long side at angle deg), in pixels."""
    a = np.radians(angle)
    u, v = np.array([np.cos(a), np.sin(a)]) * l / 2, np.array([-np.sin(a), np.cos(a)]) * w / 2
    xy = np.array([(x, y) + su * u + sv * v for su in (1, -1) for sv in (1, -1)])
    pts = np.r_[np.c_[xy, np.full(4, tz)], np.c_[xy, np.full(4, tz + h)]]
    q = (P @ np.c_[pts, np.ones(len(pts))].T).T
    return cv2.convexHull((q[:, :2] / q[:, 2:]).astype(np.float32)).reshape(-1, 2)


def _fit(outline, solid, starts, steps):
    """Pattern search for the solid whose outline best matches `outline` (pixels). solid(p): its
    hull in pixels for parameters p (the last is its height); starts: where to begin; steps: the
    first step of each parameter, halved when stuck down to a fortieth. (best p, IoU)."""
    outline = np.asarray(outline, np.float32)
    l, t = np.floor(outline.min(axis=0)) - 40
    w, h = (np.ceil(outline.max(axis=0)) - (l, t) + 40).astype(int)
    S = 4                                              # subpixel bits for fillPoly
    seen = np.zeros((h, w), np.uint8)
    cv2.fillPoly(seen, [np.round((outline - (l, t)) * (1 << S)).astype(np.int32)], 1, cv2.LINE_8, S)
    n_seen = seen.sum()

    def iou(p):
        if p[-1] < 0:
            return 0.0
        m = np.zeros_like(seen)
        cv2.fillPoly(m, [np.round((solid(p) - (l, t)) * (1 << S)).astype(np.int32)], 1, cv2.LINE_8, S)
        both = int((m & seen).sum())
        return both / (n_seen + m.sum() - both)

    steps = np.asarray(steps, float)
    n = len(steps)
    # each parameter alone, and every pair together: place and height trade off along the
    # camera's line of sight, a diagonal that one-at-a-time steps get stuck on
    ways = [np.eye(n)[k] for k in range(n)] + [np.eye(n)[i] + sj * np.eye(n)[j]
                                                for i in range(n) for j in range(i + 1, n) for sj in (1, -1)]
    ways = [w * steps for w in ways]

    def search(p):
        p, f = np.asarray(p, float), 1.0
        s = iou(p)
        while f > 1 / 40:                              # try each way, halve when stuck
            moved = False
            for w in ways:
                for d in (f * w, -f * w):
                    sq = iou(p + d)
                    if sq > s:
                        p, s, moved = p + d, sq, True
            if not moved:
                f /= 2
        return p, s

    return max((search(p0) for p0 in starts), key=lambda r: r[1])   # a few starting heights: no local trap


def upright(P, outline, tz, diameter, at):
    """The upright cylinder of this diameter (mm) whose outline best matches `outline` (pixels):
    (x, y, height mm, IoU). at: where to start (the flat footprint's centre)."""
    p, s = _fit(outline, lambda p: cylinder_outline(P, p[0], p[1], diameter / 2, p[2], tz),
                [(at[0], at[1], h0) for h0 in (0.0, diameter / 4, diameter / 2, diameter)], (4, 4, 4))
    return float(p[0]), float(p[1]), float(p[2]), s


def upright_box(P, outline, tz, w, l, at, angle):
    """The upright box with this footprint (mm) whose outline best matches `outline`:
    (x, y, angle of its long side, height mm, IoU). at, angle: where to start (the flat footprint)."""
    p, s = _fit(outline, lambda p: box_outline(P, p[0], p[1], w, l, p[2], p[3], tz),
                [(at[0], at[1], angle, h0) for h0 in (0.0, w / 4, w / 2)], (4, 4, 4, 4))
    return float(p[0]), float(p[1]), float(p[2]) % 180, float(p[3]), s


# Things whose size is known (mm), by a word in their name, first match wins. A thing found by one
# of these names gets its real place and height from cam 1 alone: the solid of this size whose
# outline matches what SAM sees. unit: how much one adds to a stack's fitted height (a chip is 3.3 mm,
# plus the gap between chips); short: how much lower the fit comes out, fixed. It depends on the
# calibration (cam 1's sense of height): re-measure with a known stack or two after each one.
# Nov 3 afternoon: 3.47 n - 1.04 (stacks of 1, 4, 5, 6). Nov 3 night, after the head marker swap and
# recalibrating: 3.13 n - 1.74, a straight line through 1s (1.2-2.8 mm), 2s (3.4-4.9), 7s (19.5,
# 20.5), a 9 (26.2) and a 10 (30.1): every one within 0.5 of its count (2.98 from the short ones alone
# read big stacks 5% high). Later, on counts the user confirmed: white stacks 3.20 n - 1.83 (1s, 2s, 7s,
# an 8), red 3.45 n - 1.83 (a 9; this afternoon's red-heavy 3.47 agrees): a red chip's shaded side
# stays red and counts in full, a white one's partly drops out as grey. red: that unit. sam: the same for SAM's outlines (unit, short), which come out a little
# bigger than the colour patch the rule was fitted on (Nov 3: +0.5 mm on singles, +1.2 on 3s).
KNOWN = (("deck", {"box": (63, 88)}),
         ("chip", {"diameter": 40, "unit": 3.20, "short": 1.83, "red": 3.45, "sam": (3.38, 1.38)}),
         ("card", {"flat": (63, 88), "height": 0.3}))


def count(h, k=dict(KNOWN)["chip"]):
    """How many in a stack this tall (mm)."""
    return max(1, round(count_raw(h, k)))


def count_raw(h, k=dict(KNOWN)["chip"]):
    """The count before rounding (7.0 is sure; 7.4 or 7.5 could be 8)."""
    return round((h + k.get("short", 0)) / k["unit"], 1)


CHIP_MM = 3.3              # a chip, as the cup feels it: it touches a stack of n's top at about 3.3 n - 1.5
PICK_IN, PLACE_ABOVE = 1.8, 0.6   # press this far below the top to lift; let go this far above it (agent/poker.md)
SURE = 0.3                 # count_raw this near a whole number is that number; further, plan for the taller stack


def cup_heights(raw):
    """Where the cup goes for a stack whose count reads `raw`: pick_z to lift its top chip, place_z to
    let go of one onto it. A borderline count (sure: false) is planned as the taller stack: the cup
    then stops short of a lower one (the pick misses, try one chip lower) rather than pressing into
    a taller one."""
    n = max(1, round(raw))
    sure = abs(raw - n) <= SURE
    if not sure:
        n = max(1, int(np.ceil(raw)))
    top = CHIP_MM * n
    return {"sure": sure, "pick_z": round(top - PICK_IN, 1), "place_z": round(top + CHIP_MM + PLACE_ABOVE, 1)}


def known(name):
    n = name.lower()
    return next((dict(v, name=k) for k, v in KNOWN if k in n), None)


def place(it, P, tz, diameter=None):
    """Corrects a found item's board place for its height, from its outline: a known thing (KNOWN)
    or anything with a given diameter. board becomes where it really stands; the flat footprint
    stays in flat; height_mm, and for a stack count, count_raw and the cup's pick_z and place_z. A fit under UPRIGHT_FIT leaves it flat
    (fit says how good it was)."""
    b, k = it["board"], known(it["what"])
    if diameter:
        k = {"diameter": diameter, "name": None}
    if not k:
        return
    it["known"] = k["name"]
    if "flat" in k:                                    # thin: the flat footprint is already right
        it["height_mm"] = k["height"]
        return
    if "diameter" in k:
        d = k["diameter"]
        x, y, h, fit = upright(P, it["outline"], tz, d, (b["x"], b["y"]))
        new = {"x": x, "y": y, "w": d, "h": d, "angle": 0.0, "round": True}
    else:
        w, l = k["box"]
        x, y, ang, h, fit = upright_box(P, it["outline"], tz, w, l, (b["x"], b["y"]), b["angle"])
        new = {"x": x, "y": y, "w": w, "h": l, "angle": ang}
    it["fit"] = round(fit, 2)
    if fit < UPRIGHT_FIT:
        return
    it["flat"] = b
    it["board"] = {**b, **{k2: round(v, 1) if isinstance(v, float) else v for k2, v in new.items()}}
    it["height_mm"] = round(h, 1)
    if k.get("unit"):
        if k.get("sam"):                               # place() fits SAM's outlines
            k = {**k, "unit": k["sam"][0], "short": k["sam"][1]}
        it["count"] = count(h, k)
        it["count_raw"] = count_raw(h, k)
        it.update(cup_heights(it["count_raw"]))
    it["pick"] = {"x": it["board"]["x"], "y": it["board"]["y"], "clear_mm": round(min(new["w"], new["h"]) / 2, 1)}


def side_match(P0, polys, side, tz):
    """Pair cam 1's items (their footprints, None for one off the board) with cam 0's outlines
    (picture-sized arrays): each outline's bottom middle against where the item's near edge
    lands in cam 0, closest first. {item index: outline}."""
    pairs = []
    for i, poly in enumerate(polys):
        if poly is None:
            continue
        poly = np.asarray(poly, float)
        c = poly.mean(axis=0)
        d = _sight(P0, c)
        u, v = project(P0, np.r_[c + ((poly - c) @ d).min() * d, tz])
        for j, m in enumerate(side):
            ys, xs = np.nonzero(m)
            if not len(ys):
                continue
            dist = float(np.hypot(xs[ys >= ys.max() - 3].mean() - u, ys.max() - v))
            if dist < SIDE_MATCH:
                pairs.append((dist, i, j))
    got, used = {}, set()
    for _, i, j in sorted(pairs):
        if i not in got and j not in used:
            got[i] = side[j]
            used.add(j)
    return got


async def _side(jpeg, names):
    """SAM on cam 0 with each name in turn until something matches (no check: matching to cam
    1's items by place does that)."""
    for n in names:
        m = await segment(jpeg, n)
        if m:
            return m
    return []


SEE = ("Overhead photo of a game table: a black board with white square markers at its corners. "
       "List the kinds of loose objects lying on the board (not the board, its markers, the machine's "
       "frame, cables, suction cup, gripper, wheels, or any part of the wooden robot), with how many of each. For each give: name, a short "
       "everyday noun phrase (\"playing card\", \"deck of cards\", \"poker chip\", \"phone\"); "
       "look, its main colour and the word object (\"white object\", \"red object\"); count. "
       "Reply with JSON only: [{\"name\": \"playing card\", \"look\": \"white object\", \"count\": 3}]")


async def see(jpeg, effort="minimal"):
    """What kinds of things are on the board: [{name, look, count, find}]. `find` is what to pass
    to find(): the name, then the look as a fallback (SAM is fussy about names, and finds plain
    "<colour> object" more reliably, especially from above)."""
    text = await ask(jpeg, SEE, effort)
    try:
        items = json.loads(text[text.index("["):text.rindex("]") + 1])
        out = []
        for i in items:
            name, look = str(i.get("name", "")).strip().lower(), str(i.get("look", "")).strip().lower()
            if name:
                out.append({"name": name, "look": look, "count": int(i.get("count", 1)),
                            "find": f"{name}|{look}" if look and look != name else name})
        return out
    except (ValueError, KeyError, TypeError):
        raise EyesError(f"Muse Spark didn't answer with a list: {text[:200]}")


ROBOT_MOSTLY = .6   # a match this much inside the robot is the robot, unless Muse sees a loose thing there
ROBOT_NEAR = 15     # px: a match this close to the robot is noted (robot.near), still pickable
CHECK_PX = 1280     # the checked picture is shrunk to this width (Muse reads it faster)


def raster_match(box, mask, shape):
    """A SAM match's box-local mask placed in a picture-sized 0/1 array."""
    out = np.zeros(shape, np.uint8)
    l, t, r, b = map(int, box)
    if r <= l or b <= t:
        return out
    local = (mask > 0).astype(np.uint8)
    if local.shape != (b - t, r - l):
        local = cv2.resize(local, (r - l, b - t), interpolation=cv2.INTER_NEAREST)
    x0, y0, x1, y1 = max(0, l), max(0, t), min(shape[1], r), min(shape[0], b)
    if x1 > x0 and y1 > y0:
        out[y0:y1, x0:x1] = local[y0 - t:y1 - t, x0 - l:x1 - l]
    return out


def robot_masks(P, boxes, shape):
    """Where the robot is in the picture, from where it's tracked (no API call): each named
    box (work-coordinate corners, from server.py: the head's cup and Z extrusion, Mate's body)
    projected through the camera and filled. {name: 0/1 array}."""
    masks = {}
    for name, corners in boxes.items():
        m = masks.setdefault(name, np.zeros(shape, np.uint8))
        pix = np.array([project(P, c) for c in corners], np.float32)
        cv2.fillConvexPoly(m, cv2.convexHull(pix).astype(np.int32), 1)
    return masks


def robot_overlap(box, mask, robots):
    """How much of a match lies inside the robot (inside), and which parts it's near."""
    shape = next(iter(robots.values())).shape
    cand = raster_match(box, mask, shape).astype(bool)
    n = int(cand.sum())
    if not n:
        return {"inside": 0.0, "near": []}
    union = np.zeros(shape, bool)
    near = []
    for name, r in robots.items():
        union |= r > 0
        k = 2 * ROBOT_NEAR + 1
        if np.any(cand & (cv2.dilate(r, np.ones((k, k), np.uint8)) > 0)):
            near.append(name)
    return {"inside": round(float((cand & union).sum()) / n, 3), "near": near}


async def verify(img, matches, wanted, effort="minimal", robots=None, everything=True):
    """Muse Spark looks at SAM's matches, numbered on the whole picture, and drops the ones that
    aren't a loose `wanted` (the suction cup as a plate, a wheel as a knife). Matches mostly
    inside the robot are kept only if it says they're a separate thing there (a card on Mate).
    If it can't answer, the robot rule alone decides: a check failing never fails find.
    everything=False: only matches touching or near the robot are in doubt; the rest are kept
    without asking (Muse takes ~25 s over a picture of a dozen cards; SAM's own name is right
    away from the robot)."""
    over = [robot_overlap(b, m, robots) for b, m in matches] if robots else [None] * len(matches)
    if not everything and robots:
        doubt = [n for n, o in enumerate(over) if o["inside"] > 0 or o["near"]]
        if not doubt:
            return matches
        sure = [m for n, m in enumerate(matches) if n not in doubt]
        return sure + await verify(img, [matches[n] for n in doubt], wanted, effort, robots)
    k = min(1.0, CHECK_PX / img.shape[1])
    marked = cv2.resize(img, None, fx=k, fy=k) if k < 1 else img.copy()
    for r in (robots or {}).values():
        cs, _ = cv2.findContours(r, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(marked, [(c * k).astype(np.int32) for c in cs], -1, (255, 0, 255), 2)
    for n, (box, mask) in enumerate(matches[:12]):
        cs, _ = cv2.findContours((mask > 0).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(marked, [((c + box[:2]) * k).astype(np.int32) for c in cs], -1, (0, 255, 255), 2)
        pos = (int(box[0] * k), max(18, int(box[1] * k) - 4))
        cv2.putText(marked, str(n), pos, cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 0, 0), 4)
        cv2.putText(marked, str(n), pos, cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 255, 255), 2)
    question = (f"Yellow numbered outlines are guesses at: {wanted}. Which ones really are a loose "
                f"{wanted}? Not the machine: the gantry, the suction cup, cables, the board or its "
                "markers, or the wooden robot (outlined in magenta) and its wheels or flipper. A round "
                "suction cup is not a plate; a wheel edge is not a knife. A loose thing lying on the "
                "robot counts. Reply with JSON only: {\"keep\": [0, 2]} (empty if none).")
    keep = None
    try:
        text = await ask(cv2.imencode(".jpg", marked, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tobytes(), question, effort)
        keep = {n for n in json.loads(text[text.index("{"):text.rindex("}") + 1])["keep"] if type(n) is int}
    except Exception:
        pass   # no answer: the robot rule alone
    # Muse's word where it gave one (only the first 12 are numbered); otherwise the robot rule
    return [m for n, (m, o) in enumerate(zip(matches, over))
            if (n in keep if keep is not None and n < 12 else o is None or o["inside"] < ROBOT_MOSTLY)]


async def _first(jpeg, img, names, effort="minimal", robots=None):
    """SAM with each name in turn until a match survives the check (always checked against the
    first name: "white object" must still be a plate): (matches, the name that found them).
    Matches by the first name are only checked near the robot; by a fallback, all of them."""
    for n in names:
        m = await segment(jpeg, n)
        if m:
            m = await verify(img, m, names[0], effort, robots, everything=n != names[0])
            if m:
                return m, n
    return [], None


async def find(jpeg, wanted, P=None, tz=None, bounds=None, question=None, effort="minimal", robot=None,
               side=None, diameter=None):
    """Where things are in one camera's picture (SAM). wanted: names, each with fallbacks after
    "|" ("earbuds case|white object") tried in order. Each item: what (the first name), matched
    (the name SAM found it by), its box and outline in the picture, and for a calibrated camera
    (P) its footprint on the board (x, y, w, h, angle), on_board, and pick (the cup's spot: the
    footprint centre). For an angled camera that's nearer the truth for a tall thing than the
    middle of what it sees, which is partway down its near side (20 mm off from cam 1). With a
    question, Muse Spark answers it about each item on the board, from its crop. robot: boxes
    of the head and Mate where they're tracked (see robot_masks); each item says how much of it
    is inside them and which it's near. side: (cam 0's JPEG, its P), taken at the same time:
    each item it sees also gets height_mm (side_height; None where cam 0 can't see it whole).
    Known things (KNOWN: cards, decks, chips) and, with diameter (mm), any upright cylinder get
    their real place and height from the outline alone (place): board is where they stand."""
    t0 = time.time()
    chains = [[n.strip() for n in w.split("|") if n.strip()] for w in wanted]
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    robots = robot_masks(P, robot, img.shape[:2]) if P is not None and robot else None
    looks = [_first(jpeg, img, c, effort, robots) for c in chains]
    if side and P is not None:
        looks += [_side(side[0], c) for c in chains]
    got = await asyncio.gather(*looks)
    side_ms, got = got[len(chains):], got[:len(chains)]
    items, boxes = [], []
    for chain, (ms, name) in zip(chains, got):
        for box, m in ms:
            if any(_overlap(box, b) > 0.6 for b in boxes):
                continue   # already found under an earlier name
            it = describe(box, m, P, tz, bounds)
            if not it:
                continue
            it = {"id": len(items), "what": chain[0], "matched": name, **it}
            if robots:
                it["robot"] = robot_overlap(box, m, robots)
            b = it.get("board")
            if b:
                it["pick"] = {"x": b["x"], "y": b["y"], "clear_mm": round(min(b["w"], b["h"]) / 2, 1)}
                place(it, P, tz, diameter)
            items.append(it)
            boxes.append(box)
    if side_ms:
        shape0 = cv2.imdecode(np.frombuffer(side[0], np.uint8), cv2.IMREAD_GRAYSCALE).shape
        outlines0 = [raster_match(b, m, shape0) for ms in side_ms for b, m in ms]
        polys = [to_xy(P, np.array(it["outline"], float), tz) if it.get("board") else None for it in items]
        for i, m in side_match(side[1], polys, outlines0, tz).items():
            h = side_height(side[1], m, polys[i], tz, P)
            items[i]["height_mm"] = round(h[0], 1) if h and abs(h[1]) <= SIDE_SLIDE else None
            items[i]["side"] = {"slide_mm": round(h[1], 1)} if h else {"cut_off": True}
        for it in items:
            if it.get("board"):
                it.setdefault("height_mm", None)
    seen_ms = round((time.time() - t0) * 1000)
    if question:
        asked = [i for i in items if i.get("on_board") is not False][:24]
        answers = await asyncio.gather(*(ask(crop(img, i["box"]), question, effort) for i in asked),
                                       return_exceptions=True)
        for i, a in zip(asked, answers):
            i["answer"] = f"(no answer: {a})" if isinstance(a, Exception) else a
    outlines = {name: [c.reshape(-1, 2).tolist() for c in cv2.findContours(r, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]]
                for name, r in (robots or {}).items()}
    return {"items": items, "robot_masks": outlines,
            "size": [img.shape[1], img.shape[0]], "seen_ms": seen_ms,
            "took_ms": round((time.time() - t0) * 1000)}


SHAPE = ("This picture shows one {what}, turned so its length runs left to right (if it has one). "
         "Model it for a low-poly 3D view as 4 to 12 simple solids: the main body, then the details that "
         "make it recognisable (a rim, a handle, a blade and its collar, buttons, a lid, a label band). "
         "axis: \"along\" if it lies flat (parts go left to right; a cylinder then lies on its side, like "
         "a pen), \"up\" if it stands up or is round and flat (parts go bottom to top: a plate, a coin or a "
         "chip is \"up\", a short cylinder per layer). Each part: shape (box, cylinder, cone, sphere, wedge "
         "or ring; a cone and a wedge narrow towards \"to\"; a ring is a flat rim or band around the "
         "axis); from and to (0 to 1 along the axis); size (its width across, 0 to 1 of the object's "
         "width); side (how far off the middle across, -0.5 to 0.5; 0 is centred); for \"along\": tall "
         "(its height, 0 to 1 of height_mm) and lift (how high its bottom is, 0 to 1); color (hex). Parts "
         "may overlap. height_mm: its real height above the table. top: text printed on its top worth "
         "drawing (a playing card's rank and suit, like \"K\u2660\"), else \"\". Reply with JSON only: "
         "{{\"height_mm\": 12, \"axis\": \"along\", \"top\": \"\", \"parts\": [{{\"shape\": \"cylinder\", "
         "\"from\": 0, \"to\": 0.7, \"size\": 0.6, \"side\": 0, \"tall\": 1, \"lift\": 0, "
         "\"color\": \"#d9a400\"}}]}}")
SHAPES = ("box", "cylinder", "cone", "sphere", "wedge", "ring")
PARTS = 12


def straight(img, it, P, z, pad=CROP_PAD):
    """An item's crop turned so the long side of its footprint runs left to right, its start (the
    footprint's -x end in the 3D scene) on the left."""
    b = it["board"]
    a = np.radians(b["angle"])
    d = np.array([np.cos(a), np.sin(a)]) * b["h"] / 2
    p0, p1 = (project(P, (*(np.array([b["x"], b["y"]]) + s * d), z)) for s in (-1, 1))
    l, t, r, bt = it["box"]
    c = ((l + r) / 2, (t + bt) / 2)
    turn = cv2.getRotationMatrix2D(c, float(np.degrees(np.arctan2(*(p1 - p0)[::-1]))), 1)
    side = int(max(r - l, bt - t) * 1.2) + 2 * pad
    turn[:, 2] += (side / 2 - c[0], side / 2 - c[1])
    out = cv2.warpAffine(img, turn, (side, side), borderValue=(0, 0, 0))
    return cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()


async def shape(jpeg, what, effort="minimal"):
    """A thing as up to PARTS solids for the 3D scene (Muse Spark, from its straightened crop):
    {height_mm, axis, top, parts: [{shape, from, to, size, side, tall, lift, color}]}."""
    text = await ask(jpeg, SHAPE.format(what=what), effort)
    try:
        s = json.loads(text[text.index("{"):text.rindex("}") + 1])
        num = lambda v, lo, hi, d: min(hi, max(lo, float(v))) if isinstance(v, (int, float)) else d
        parts = [{"shape": p["shape"], "from": num(p.get("from"), 0, 1, 0), "to": num(p.get("to"), 0, 1, 1),
                  "size": num(p.get("size"), 0.02, 1, 1), "side": num(p.get("side"), -0.5, 0.5, 0),
                  "tall": num(p.get("tall"), 0.02, 1, None), "lift": num(p.get("lift"), 0, 1, 0),
                  "color": str(p.get("color", "#999999"))[:7]}
                 for p in s.get("parts", []) if p.get("shape") in SHAPES][:PARTS]
        return {"height_mm": num(s.get("height_mm"), 0.3, 200, 10), "axis": "up" if s.get("axis") == "up" else "along",
                "top": str(s.get("top") or "")[:6], "parts": parts}
    except (ValueError, KeyError, TypeError, AttributeError):
        raise EyesError(f"Muse Spark didn't answer with a shape: {text[:200]}")


GONE = 0.35      # share of an item's outline that must change for it to count as gone


def changed(before, now, outline):
    """How much of an item's outline (pixels, from find) looks different in `now` than in
    `before` (grey pictures from the same camera): the share of its pixels that changed a lot.
    Lifted off its spot, most of it does; a pick that didn't take, hardly any. Works for any
    camera, Mate's too, as long as the camera hasn't moved. No API call."""
    m = np.zeros(before.shape, np.uint8)
    cv2.fillPoly(m, [np.array(outline, np.int32)], 1)
    m = cv2.erode(m, np.ones((5, 5), np.uint8))       # the edge shifts a pixel or two anyway
    if not m.any():
        return None
    d = np.abs(now.astype(np.int16) - before.astype(np.int16))[m > 0]
    return round(float(np.mean(d > 40)), 2)


def _overlap(a, b):
    """Intersection over the smaller box."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    return w * h / min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))


HISTORY = Path(__file__).parent / "vision"   # every see, find and check, with its pictures (not in git)
KEEP = 100                                   # actions kept; older ones and their pictures are deleted


class History:
    """Every see, find and check, on disk, so the vision page and agents see the same list after
    a reload, from another device, or after the hub restarts. history.jsonl holds one action a
    line (numbered: n); <n>-<cam>.jpg its pictures."""

    def __init__(self, folder=HISTORY, keep=KEEP):
        self.dir, self.keep = folder, keep
        self.dir.mkdir(exist_ok=True)
        self.file = folder / "history.jsonl"
        self.items = []
        for line in self.file.read_text().splitlines() if self.file.exists() else []:
            try:
                self.items.append(json.loads(line))
            except ValueError:
                pass

    def add(self, rec, jpegs=None):
        n = self.items[-1]["n"] + 1 if self.items else 1
        rec = {"n": n, **rec, "pictures": sorted(jpegs or {})}
        for cam, jpg in (jpegs or {}).items():
            (self.dir / f"{n}-{cam}.jpg").write_bytes(jpg)
        self.items.append(rec)
        with self.file.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        if len(self.items) > self.keep + 20:      # prune now and then, not on every action
            old, self.items = self.items[:-self.keep], self.items[-self.keep:]
            for r in old:
                for cam in r.get("pictures", []):
                    (self.dir / f"{r['n']}-{cam}.jpg").unlink(missing_ok=True)
            self.file.write_text("".join(json.dumps(r) + "\n" for r in self.items))
        return rec

    def get(self, n):
        return next((r for r in reversed(self.items) if r["n"] == n), None)

    def last(self, kind=None):
        return next((r for r in reversed(self.items) if kind is None or r["kind"] == kind), None)

    def recent(self, limit=50):
        return self.items[::-1][:limit]

    def picture(self, n, cam):
        p = self.dir / f"{n}-{cam}.jpg"
        return p.read_bytes() if p.exists() else None
