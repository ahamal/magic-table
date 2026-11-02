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
        if bounds:
            obj["on_board"] = bool(bounds[0] - EDGE_MM <= cx <= bounds[1] + EDGE_MM and
                                   bounds[2] - EDGE_MM <= cy <= bounds[3] + EDGE_MM)
    return obj


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


async def verify(img, matches, wanted, effort="minimal", robots=None):
    """Muse Spark looks at SAM's matches, numbered on the whole picture, and drops the ones that
    aren't a loose `wanted` (the suction cup as a plate, a wheel as a knife). Matches mostly
    inside the robot are kept only if it says they're a separate thing there (a card on Mate).
    If it can't answer, the robot rule alone decides: a check failing never fails find."""
    over = [robot_overlap(b, m, robots) for b, m in matches] if robots else [None] * len(matches)
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
    first name: "white object" must still be a plate): (matches, the name that found them)."""
    for n in names:
        m = await segment(jpeg, n)
        if m:
            m = await verify(img, m, names[0], effort, robots)
            if m:
                return m, n
    return [], None


async def find(jpeg, wanted, P=None, tz=None, bounds=None, question=None, effort="minimal", robot=None):
    """Where things are in one camera's picture (SAM). wanted: names, each with fallbacks after
    "|" ("earbuds case|white object") tried in order. Each item: what (the first name), matched
    (the name SAM found it by), its box and outline in the picture, and for a calibrated camera
    (P) its footprint on the board (x, y, w, h, angle), on_board, and pick (the cup's spot: the
    footprint centre). For an angled camera that's nearer the truth for a tall thing than the
    middle of what it sees, which is partway down its near side (20 mm off from cam 1). With a
    question, Muse Spark answers it about each item on the board, from its crop. robot: boxes
    of the head and Mate where they're tracked (see robot_masks); each item says how much of it
    is inside them and which it's near."""
    t0 = time.time()
    chains = [[n.strip() for n in w.split("|") if n.strip()] for w in wanted]
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    robots = robot_masks(P, robot, img.shape[:2]) if P is not None and robot else None
    got = await asyncio.gather(*(_first(jpeg, img, c, effort, robots) for c in chains))
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
            items.append(it)
            boxes.append(box)
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
