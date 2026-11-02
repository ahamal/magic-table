"""Table hub web server: GRBL, the gripper, the cameras, vision and speech-to-text over HTTP + a
live WebSocket, the jog page, the talk page and the 3D scene page.

Run on the Pi:  python serve.py   (HTTP and HTTPS both on :8000; see serve.py)
"""

import asyncio
import contextlib
import json
import math
import os
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import camera
import eyes
from grbl import REALTIME, Grbl
from mate import MateLink
from gripper import SEQUENCES, Gripper
from talk import Chat, TranscribeError
from vision import MATE_SIZE, Vision
from voice import Voice

HERE = Path(__file__).parent
grbl = Grbl(port=os.environ.get("GRBL_PORT", "/dev/ttyACM0"))
cameras = []  # one per camera the Pi found at boot
app = FastAPI(title="Magic Table hub")
clients = set()
loop = None


def broadcast(event):
    """Called from GRBL threads; hands the event to the asyncio loop."""
    if loop:
        for ws in list(clients):
            asyncio.run_coroutine_threadsafe(_send(ws, event), loop)


gripper = Gripper(grbl, broadcast)
chat = Chat(broadcast)
voice = Voice(broadcast)
mate = MateLink()
vision = None  # needs the cameras, so it starts at startup


async def _send(ws, event):
    try:
        await ws.send_json(event)
    except Exception:
        clients.discard(ws)


@app.on_event("startup")
async def startup():
    global loop
    loop = asyncio.get_running_loop()
    grbl.listeners.append(broadcast)
    grbl.start()
    cameras.extend(await asyncio.to_thread(camera.start_all))
    global vision
    vision = Vision(cameras, grbl, broadcast, mate)
    vision.run()


# ---- API ----

class Line(BaseModel):
    line: str


class Jog(BaseModel):
    x: float = 0
    y: float = 0
    z: float = 0
    feed: float = 3000


class Move(BaseModel):
    x: float | None = None
    y: float | None = None
    z: float | None = None
    feed: float | None = None  # None = rapid (G0)


def run(line, timeout=30):
    reply = grbl.send(line, timeout)
    if line.strip().upper() in ("$X", "$H") and reply == "ok":
        close_valve()
    return {"line": line, "reply": reply}


def close_valve():
    """A reset can leave SpnDir (the valve) set; close it once G-code runs again."""
    if gripper.valve:
        gripper.run("valve_off")


@app.get("/api/status")
def status():
    return {**grbl.status, "homed": grbl.homed}


@app.get("/api/settings")
def settings():
    return grbl.settings


@app.post("/api/send")
async def send(body: Line):
    """Any G-code or $ command. Waits for GRBL's ok/error."""
    return await asyncio.to_thread(run, body.line)


# Work Z is the cup's height above the board (0 = touching it). Never past the top of the Z
# travel, never more than the 1 mm squeeze a grip needs into the board. No limit switches, so
# these are the only stops.
Z_MIN, Z_MAX = -1.0, 150.0


def z_now():
    return (grbl.status.get("WPos") or [0, 0, 0])[2]


UNANCHORED = {"line": "", "reply": "error:GRBL reset, so its position is unknown: $X, then POST /api/calibration/reanchor"}


@app.post("/api/jog")
async def jog(body: Jog):
    """Relative jog ($J). Cancel early with /api/realtime/jog_cancel. Z jogs stop at the Z limits."""
    if vision and vision.needs_reanchor:
        return UNANCHORED          # the limits are in work coordinates, which a reset lost
    if body.z:
        z = z_now()
        body.z = min(body.z, Z_MAX - z) if body.z > 0 else max(body.z, Z_MIN - z)
    if vision and (body.x or body.y):
        body.x, body.y = vision.clip_jog(body.x, body.y)   # the cup stops at the board bounds
    if max(abs(body.x), abs(body.y), abs(body.z)) < 0.01:
        return {"line": "", "reply": "error:at a limit (Z or the board bounds)"}
    axes = "".join(f"{a}{v:.3f}" for a, v in (("X", body.x), ("Y", body.y), ("Z", body.z)) if abs(v) >= 0.001)
    if not axes:
        raise HTTPException(400, "nothing to jog")
    if vision and not vision.jog_ok(body.x, body.y, body.z):
        return {"line": "", "reply": "error:won't press into Mate"}
    return await asyncio.to_thread(run, f"$J=G91 G21 {axes} F{body.feed:.0f}")


@app.post("/api/move")
async def move(body: Move):
    """Absolute move in work coordinates (Z = cup height above the board, Z_MIN to Z_MAX)."""
    axes = "".join(f"{a}{v:.3f}" for a, v in (("X", body.x), ("Y", body.y), ("Z", body.z)) if v is not None)
    if not axes:
        raise HTTPException(400, "nothing to move")
    if vision and vision.needs_reanchor:
        return UNANCHORED
    if body.z is not None and not Z_MIN <= body.z <= Z_MAX:
        return {"line": "", "reply": f"error:Z {body.z:g} is outside {Z_MIN:g} to {Z_MAX:g}"}
    if vision:
        w = grbl.status.get("WPos") or [0, 0, 0]
        hx = w[0] if body.x is None else body.x
        hy = w[1] if body.y is None else body.y
        if not vision.cup_in_bounds(hx, hy):
            return {"line": "", "reply": "error:that puts the cup outside the board bounds"}
    if vision:
        lines, why = vision.plan_move(body.x, body.y, body.z)
        if why:
            return {"line": "", "reply": f"error:{why}"}
        if lines:   # around Mate: up to travel height, across, back down
            replies = [await asyncio.to_thread(run, l) for l in lines]
            return {"line": " / ".join(lines), "reply": replies[-1]["reply"]}
    cmd = f"G90 G1 {axes} F{body.feed:.0f}" if body.feed else f"G90 G0 {axes}"
    return await asyncio.to_thread(run, cmd)


class Tip(BaseModel):
    x: float
    y: float
    z: float | None = None      # cup tip height above the board, mm (work Z 0 = touching it)
    feed: float | None = None   # None = rapid


@app.post("/api/tip")
async def tip(body: Tip):
    """Put the cup tip (not the head) at board X/Y, optionally at a height. The cup sits in
    front of the Z extrusion (vision.TIP_OFFSET), so the head goes there minus that offset.
    Same Mate rule as /api/move."""
    hx, hy = vision.head_for_tip(body.x, body.y)
    return await move(Move(x=hx, y=hy, z=body.z, feed=body.feed))


@app.post("/api/home")
async def home():
    reply = await asyncio.to_thread(grbl.home)
    if reply == "ok":
        await asyncio.to_thread(close_valve)
    return {"line": "$H", "reply": reply}


@app.post("/api/realtime/{name}")
def realtime(name: str):
    """status, hold, resume, reset, jog_cancel. Sent immediately, no queue."""
    if name not in REALTIME:
        raise HTTPException(404, f"unknown: {name}")
    if vision and name in ("hold", "reset"):
        vision.stop()   # a running calibration stops here, with no further moves
    return {"sent": grbl.realtime(name)}


@app.get("/api/gripper")
def gripper_state():
    return gripper.state


@app.post("/api/gripper/{name}")
async def gripper_command(name: str, pump_s: float | None = None):
    """pump_on, pump_off, valve_on, valve_off, grip, drop, stop. Queued after any motion.
    grip?pump_s=3 runs the pump 3 s then stops it; the vacuum holds ~20 s (enough for a card)."""
    if name not in SEQUENCES:
        raise HTTPException(404, f"unknown: {name}")
    return await asyncio.to_thread(gripper.run, name, pump_s)


def get_camera(cam):
    if not 0 <= cam < len(cameras):
        raise HTTPException(404, f"no camera {cam}; there are {len(cameras)}")
    c = cameras[cam]
    if c.cam is None:
        raise HTTPException(503, f"camera {cam} didn't start: {c.error}")
    return c


@app.get("/api/cameras")
def list_cameras():
    return [c.info for c in cameras]


@app.get("/api/capture")
async def capture(cam: int = 0):
    """A fresh full-size JPEG from one camera."""
    c = get_camera(cam)
    jpg = await asyncio.to_thread(c.capture)
    if jpg is None:
        raise HTTPException(503, f"camera {cam} stopped")
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


history = eyes.History()   # every see, find and check, kept on disk


async def _picture(cam):
    """A fresh JPEG from cam 0, 1 or "mate", and that camera's model (None for Mate)."""
    if cam == "mate":
        try:
            return await asyncio.to_thread(lambda: urllib.request.urlopen(f"{mate.url}/capture", timeout=5).read()), None
        except OSError as e:
            raise HTTPException(503, f"Mate's camera didn't answer: {e}")
    c = get_camera(int(cam))
    jpg = await asyncio.to_thread(c.capture)
    if jpg is None:
        raise HTTPException(503, f"camera {cam} stopped")
    P, _ = vision._cam(int(cam))
    return jpg, P


def _eyes_done(kind, result, jpegs, by):
    rec = history.add({"kind": kind, "at": time.time(), "by": by, **result}, jpegs)
    broadcast({"type": "vision", **rec})
    return rec


async def _meta(coro):
    try:
        return await coro
    except eyes.EyesError as e:
        raise HTTPException(502, str(e))
    except HTTPException:
        raise
    except Exception as e:  # network trouble reaching Meta
        raise HTTPException(502, f"couldn't reach Meta: {e}")


@app.get("/api/see")
async def see(cam: str = "1", ask: str | None = None, effort: str = "minimal", by: str = "agent"):
    """What's on the board (Muse Spark, one fresh picture): {things: [{name, count}]}, names that
    work with /api/find. With `ask`, Muse Spark answers that question about the picture
    instead: {answer}. ~2-3 s."""
    if effort not in eyes.EFFORTS:
        raise HTTPException(400, f"effort is one of {', '.join(eyes.EFFORTS)}")
    jpg, _ = await _picture(cam)
    t0 = time.time()
    if ask:
        res = {"answer": await _meta(eyes.ask(jpg, ask, effort))}
    else:
        res = {"things": await _meta(eyes.see(jpg, effort))}
    return _eyes_done("see", {"cam": cam, "ask": ask, **res, "took_ms": round((time.time() - t0) * 1000)},
                      {cam: jpg}, by)


def _robot_boxes():
    """The head and Mate as boxes of work-coordinate corners, where they're tracked now, so find
    can tell a match that is the robot from a loose thing (eyes.robot_masks)."""
    sc, tz = vision.scene, (vision.cal or {}).get("table_z")
    if tz is None or not sc.get("head"):
        return None
    box = lambda cx, cy, hx, hy, z0, z1, a=0.0: [
        (cx + sx * hx * math.cos(a) - sy * hy * math.sin(a), cy + sx * hx * math.sin(a) + sy * hy * math.cos(a), z)
        for sx in (-1, 1) for sy in (-1, 1) for z in (z0, z1)]
    h = sc["head"]
    out = {"cup": box(h["tip_x"], h["tip_y"], 12, 12, h["tip_z"], h["z"]),
           "head": box(h["x"] + 11, h["y"], 12, 19, h["z"] - 35, h["z"] + 250)}   # Z extrusion, marker card on its left face
    m = sc.get("mate")
    if m:
        half = max(MATE_SIZE[:2]) / 2 + 8
        out["mate"] = box(m["x"], m["y"], half, half, tz, tz + MATE_SIZE[2], math.radians(m["heading"]))
    return out


@app.get("/api/find")
async def find(what: str, cam: str = "1", ask: str | None = None, effort: str = "minimal", by: str = "agent"):
    """Where things are, for picking (SAM 3.1, one fresh picture from `cam`: 1 by default, 0, or
    "mate"). what: one or more names, comma-separated (from /api/see, or your own); fallbacks
    after "|" are tried in order when a name finds nothing: what=earbuds case|white object
    (/api/see gives them). Each item: what, matched, box and outline (pixels), and from a
    calibrated camera its footprint on the board {x, y, w, h, angle}, on_board, and pick
    {x, y, clear_mm}: put the cup at x, y; clear_mm is how much room the cup (15 mm) has.
    Mate's camera gives pixels only. ask: a question Muse Spark answers about each item from
    its crop (answer). ~2-3 s."""
    phrases = [p.strip() for p in what.split(",") if p.strip()][:6]
    if not phrases:
        raise HTTPException(400, "say what to find, e.g. what=playing card")
    if effort not in eyes.EFFORTS:
        raise HTTPException(400, f"effort is one of {', '.join(eyes.EFFORTS)}")
    jpg, P = await _picture(cam)
    tz = (vision.cal or {}).get("table_z")
    if tz is None:
        P = None
    res = await _meta(eyes.find(jpg, phrases, P, tz, (vision.cal or {}).get("bounds"), ask, effort, _robot_boxes()))
    return _eyes_done("find", {"cam": cam, "what": phrases, "ask": ask, **res}, {cam: jpg}, by)


@app.get("/api/find/shapes")
async def find_shapes(n: int | None = None, effort: str = "minimal", by: str = "agent"):
    """The things of a find (`n`, the last by default) as low-poly models for the 3D scene: Muse
    Spark describes each from find's picture as a few solids; the footprint gives place, size and
    turn. items: [{id, what, board, shape: {height_mm, axis, top, parts}}]. ~1-2 s."""
    res = history.get(n) if n else history.last("find")
    if not res or res["kind"] != "find":
        raise HTTPException(404, "no such find: GET /api/find first")
    P, _ = vision._cam(int(res["cam"])) if res["cam"] in ("0", "1") else (None, None)
    jpg = history.picture(res["n"], res["cam"])
    on = [i for i in res["items"] if i.get("board") and i.get("on_board") is not False][:12]
    if P is None or jpg is None or not on:
        raise HTTPException(400, "that find has nothing on the board to model")
    t0 = time.time()
    img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
    tz = vision.cal["table_z"]
    got = await asyncio.gather(*(_meta(eyes.shape(eyes.straight(img, i, P, tz), i["what"], effort)) for i in on),
                               return_exceptions=True)
    items = [{"id": i["id"], "what": i["what"], "board": i["board"],
              **({"error": str(getattr(g, "detail", g))} if isinstance(g, Exception) else {"shape": g})}
             for i, g in zip(on, got)]
    return _eyes_done("shape", {"find": res["n"], "cam": res["cam"], "items": items,
                                "took_ms": round((time.time() - t0) * 1000)}, {}, by)


@app.get("/api/find/check")
async def find_check(id: int, by: str = "agent"):
    """Did item `id` of the last find leave its spot? A fresh picture from the same camera,
    compared with find's inside the item's outline: {gone, changed}. Use it with the thing
    lifted: gone false means the pick didn't take. No API call, ~0.5 s."""
    res = history.last("find")
    if not res:
        raise HTTPException(404, "no find to compare with: GET /api/find first")
    it = next((i for i in res["items"] if i["id"] == id), None)
    if it is None:
        raise HTTPException(404, f"no item {id} in the last find")
    cam = res["cam"]
    now, _ = await _picture(cam)
    dec = lambda j: cv2.imdecode(np.frombuffer(j, np.uint8), cv2.IMREAD_GRAYSCALE)
    c = eyes.changed(dec(history.picture(res["n"], cam)), dec(now), it["outline"])
    return _eyes_done("check", {"id": id, "find": res["n"], "what": it["what"], "cam": cam,
                                "gone": c is not None and c > eyes.GONE, "changed": c}, {}, by)


@app.get("/api/vision/history")
def vision_history(limit: int = 50):
    """The latest see, find and check actions, newest first (kept on the Pi: the last 100).
    Each has n (its number), kind, at, by, its results, and pictures (cameras with a picture:
    GET /api/vision/image?n=&cam=)."""
    return history.recent(max(1, min(limit, 100)))


@app.get("/api/vision/last")
def vision_last():
    """The last see, find or check (null before the first)."""
    return history.last()


@app.get("/api/vision/image")
def vision_image(n: int | None = None, cam: str = "1"):
    """The picture action n used (the last see or find when n is left out)."""
    rec = history.get(n) if n is not None else next((r for r in reversed(history.items) if cam in r.get("pictures", [])), None)
    jpg = rec and history.picture(rec["n"], cam)
    if not jpg:
        raise HTTPException(404, f"no picture from cam {cam}" + (f" for action {n}" if n is not None else ""))
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400" if n is not None else "no-store"})


@app.get("/api/stream")
async def stream(cam: int = 0, fps: float = 10):
    """Live MJPEG view of one camera, 820 px wide. Open it in a browser tab or an <img>."""
    c = get_camera(cam)

    async def frames():
        while True:
            jpg = await asyncio.to_thread(c.frame)
            if jpg is None:
                return
            yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg) + jpg + b"\r\n"
            await asyncio.sleep(1 / max(fps, 0.5))

    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


class Calibrate(BaseModel):
    room: float | None = None   # how far the cup is above the board at the start (mm); left out: the
                                # current Z, once the board has been touched off (Z is then the cup's height)
    span: float = 60    # grid half-width, mm, around where the head is now (a 120 mm square)
    steps: int = 3      # steps x steps stops per height
    levels: int = 3     # heights, from the start down to 15 mm above the board
    feed: float = 2000  # mm/min for going down a level; moves within a level are rapid


@app.post("/api/calibrate")
async def calibrate(body: Calibrate):
    """Move the head marker over a grid at several heights and fit every camera. Takes ~2-3 min.
    Start with Z at its top (that becomes the travel height) over the middle of the board, Mate
    out from under the square; it goes down from there, never closer than 15 mm to the board."""
    room = body.room
    if room is None:
        if (vision.cal or {}).get("table_source") != "touch":
            return {"ok": False, "error": "say how far the cup is above the board (room): the board hasn't been touched off"}
        room = (grbl.status.get("WPos") or [0, 0, 0])[2]
    return await asyncio.to_thread(vision.calibrate, room, body.span, body.steps, body.levels, body.feed)


@app.post("/api/calibrate/stop")
def calibrate_stop():
    """Stop a running calibration: the move under way finishes (a second or two), then no
    more. GRBL keeps its position, so there's nothing to re-anchor (unlike STOP, which resets)."""
    vision.stop()
    return {"ok": True, "running": vision.busy}


@app.get("/api/calibration")
def calibration():
    """Is it calibrated, how well, and does it still agree with the gantry."""
    return vision.summary()


@app.post("/api/calibration/table")
async def calibration_table():
    """The cup is touching the board right now: Z becomes 0 there. Also the fix when Z has
    skipped steps (a lift that stalled)."""
    return await asyncio.to_thread(vision.set_table)


class Travel(BaseModel):
    z: float | None = None   # cup height (work Z) that's safe over Mate; None = the current Z


@app.post("/api/calibration/travel")
def calibration_travel(body: Travel = Travel()):
    """Set the travel height: the cup height that's safe over Mate (110 mm clears it)."""
    return vision.set_travel(body.z)


@app.post("/api/calibration/bounds")
async def calibration_bounds():
    """Measure the board markers and save the cup's allowed X/Y: inside their inner edges."""
    return await asyncio.to_thread(vision.set_bounds)


@app.post("/api/calibration/reanchor")
async def reanchor(camera: bool = False):
    """After a GRBL reset: put the work coordinates back to the saved position (exact if nothing
    moved). ?camera=true takes X/Y from the camera instead, for when the head really moved."""
    return await asyncio.to_thread(vision.reanchor, camera)


@app.get("/api/scene")
async def scene(fresh: bool = False):
    """Where everything is, in gantry coordinates: head, Mate, cards, board markers, cameras."""
    return await asyncio.to_thread(vision.update) if fresh else vision.scene


# ---- Mate: driving with the camera ----

def mate_pose(n=3):
    """Mate's marker pose (x, y, heading), averaged over a few fresh looks; None if unseen."""
    seen = []
    for _ in range(n):
        m = vision.update().get("mate")
        if m:
            seen.append((m["x"], m["y"], m["heading"]))
        time.sleep(0.15)
    if not seen:
        return None
    h0 = seen[0][2]
    hs = [h0 + ((h - h0 + 180) % 360 - 180) for _, _, h in seen]
    return (sum(p[0] for p in seen) / len(seen), sum(p[1] for p in seen) / len(seen), sum(hs) / len(hs))


def mate_home():
    """Mate's home: saved in the calibration, or by default the middle of the left margin,
    halfway between the left board markers, facing into the board (+X)."""
    if vision.cal and vision.cal.get("mate_home"):
        return vision.cal["mate_home"]
    board = vision.update().get("board") or {}
    pts = [(b["x"], b["y"]) for b in board.values()]
    if len(pts) < 2:
        return None
    mid = sum(x for x, _ in pts) / len(pts)
    left = [(x, y) for x, y in pts if x < mid]
    if len(left) < 2:
        return None
    return [round(sum(x for x, _ in left) / len(left), 1), round(sum(y for _, y in left) / len(left), 1), 0.0]


class MateGoto(BaseModel):
    x: float
    y: float
    heading: float | None = None   # degrees, anticlockwise from +X; None = any


def mate_goto(x, y, heading):
    if not vision.cal:
        return {"ok": False, "error": "not calibrated"}
    b = vision.cal.get("bounds")
    if b and not (b[0] - 80 <= x <= b[1] + 80 and b[2] - 80 <= y <= b[3] + 80):
        return {"ok": False, "error": "that's off the board"}
    if vision.needs_reanchor:                           # can't tell how high the head is
        return {"ok": False, "error": UNANCHORED["reply"].removeprefix("error:")}
    travel = vision.cal.get("travel_z")
    if travel is not None and z_now() < travel - 0.5:   # nothing low for Mate to run into
        if grbl.send(f"G90 G0 Z{travel:.3f}") != "ok" or grbl.send("G4 P0", 60) != "ok":
            return {"ok": False, "error": "couldn't raise the head first"}
    return mate.goto(mate_pose, x, y, heading)


@app.post("/api/mate/goto")
async def mate_goto_api(body: MateGoto):
    """Drive Mate so its turning centre ends on (x, y), then turn to `heading`. Turns, drives,
    looks with the camera and corrects until within ~5 mm and ~3 deg. Raises the gantry head to
    travel height first."""
    return await asyncio.to_thread(mate_goto, body.x, body.y, body.heading)


@app.get("/api/mate/home")
def mate_home_get():
    return {"home": mate_home()}


@app.post("/api/mate/home")
async def mate_home_go():
    """Send Mate home (see GET /api/mate/home)."""
    h = mate_home()
    if not h:
        return {"ok": False, "error": "no home yet: the camera needs the left board markers"}
    return await asyncio.to_thread(mate_goto, *h)


class MateHome(BaseModel):
    x: float | None = None          # all None = where Mate is now
    y: float | None = None
    heading: float | None = None


@app.post("/api/mate/home/set")
async def mate_home_set(body: MateHome):
    """Save Mate's home: a spot and heading, or (no body) where Mate is now."""
    if body.x is None or body.y is None:
        p = await asyncio.to_thread(mate_pose)
        if p is None:
            return {"ok": False, "error": "the camera can't see Mate"}
        cx, cy = mate.centre(p)
        home = [round(cx, 1), round(cy, 1), round(p[2], 1)]
    else:
        home = [body.x, body.y, body.heading if body.heading is not None else 0.0]
    vision.cal["mate_home"] = home
    vision.save()
    return {"ok": True, "home": home}


FACES = HERE / "faces"     # software/mate/faces, deployed next to the hub (eyes.bin, reactions/)


def gestures():
    return {k: v for k, v in json.loads((GUIDES / "gestures.json").read_text()).items() if not k.startswith("_")}


@app.get("/api/mate/gestures")
def mate_gestures():
    """Mate's gestures by name: what each says in the chat and which face it shows."""
    return {k: {"emoji": g.get("emoji", ""), "text": g["text"], "face": g.get("face")} for k, g in gestures().items()}


class Gesture(BaseModel):
    name: str | None = None          # one of GET /api/mate/gestures
    to: str | None = None            # who it's aimed at (a player's name), for the chat line
    wait: bool = False               # True: return once it's done
    # or a one-off gesture of your own instead of a name (same fields as agent/gestures.json):
    emoji: str = ""
    text: str | None = None
    face: str | None = None
    steps: list[dict] = []


@app.post("/api/mate/gesture")
async def mate_gesture(body: Gesture):
    """Mate reacts: a face, flipper and wheel moves, ending where it started (a few cm at most).
    The gesture goes in the chat as Mate's: Mate never speaks, this is how it talks. Returns at
    once unless wait=true; Mate refuses while it's busy (a goto or another gesture)."""
    if body.name:
        g = gestures().get(body.name)
        if g is None:
            raise HTTPException(404, f"no gesture {body.name!r}; see GET /api/mate/gestures")
    elif body.text:
        g = {"emoji": body.emoji, "text": body.text, "face": body.face, "steps": body.steps}
    else:
        raise HTTPException(400, "give a gesture name, or text (+ face, steps) for a one-off")
    if g.get("face") and not (FACES / "reactions" / f"{g['face']}.bin").exists():
        raise HTTPException(400, f"no face {g['face']!r}; have {sorted(p.stem for p in (FACES / 'reactions').glob('*.bin'))}")
    if mate.busy:
        return {"ok": False, "error": "Mate is busy"}
    said = (g["to"].format(to=body.to) if "to" in g else f"{g['text']} at {body.to}") if body.to else g["text"]
    item = chat.add(f"{g.get('emoji', '')} {said}".strip(), "mate", "gesture", gesture=body.name or "custom",
                    **({"to": body.to} if body.to else {}))
    run = asyncio.to_thread(mate.gesture, g, FACES)
    if body.wait:
        return {**await run, "chat": item}
    asyncio.create_task(run)
    return {"ok": True, "chat": item}


class Say(BaseModel):
    text: str
    by: str = "agent"    # who's speaking: the agent's own name ("Muse", "Claude")
    wait: bool = False   # True: return once it has been spoken


@app.post("/api/say")
async def say(body: Say):
    """Speak out loud on the table's speaker, and the line goes in the chat under `by`. Use it to
    talk to the people at the table, and to ask them when something is impossible or unclear;
    their answers come back in the chat (GET /api/chat?after=<id>&wait=30)."""
    if body.by in ("player", "mate"):
        raise HTTPException(400, "players type or talk on the talk page; Mate never speaks (use /api/mate/gesture)")
    chat.add(body.text, body.by[:32], "speaker")
    err = await asyncio.to_thread(voice.say, body.text, body.wait)
    return {"ok": err is None, "error": err}


@app.get("/api/voice")
def voice_get():
    """The table's voice: which Piper voice and pace, and the voices installed."""
    return {**voice.choice, "voices": voice.voices(), "speakers": list(voice.speakers(voice.choice["voice"])),
            "engine": "piper" if voice.voices() else "espeak-ng"}


class VoiceChoice(BaseModel):
    voice: str | None = None        # one of GET /api/voice -> voices
    pace: float | None = None       # 1 = normal, 0.8 = a bit faster, 1.2 slower
    speaker: str | None = None      # in a multi-speaker voice: a name (e.g. "prudence") or number


@app.post("/api/voice")
def voice_set(body: VoiceChoice):
    err = voice.choose(body.voice, body.pace, body.speaker)
    return {"ok": err is None, "error": err, **voice.choice}


@app.post("/api/transcribe")
async def transcribe(request: Request):
    """Body: one utterance as a 16 or 24 kHz mono 16-bit WAV. Returns the transcript item,
    or {"text": ""} if nothing was said."""
    wav = await request.body()
    if len(wav) < 1000:
        raise HTTPException(400, "no audio")
    try:
        item = await asyncio.to_thread(chat.transcribe, wav)
    except TranscribeError as e:
        raise HTTPException(502, str(e))
    except Exception as e:  # network trouble reaching Meta
        raise HTTPException(502, f"couldn't reach Meta: {e}")
    return item or {"text": ""}


@app.get("/api/chat")
async def get_chat(after: int = 0, wait: float = 0, by: str | None = None):
    """The table's chat, oldest first: what people said (voice) or typed, what the agent said
    out loud (via "speaker", by = its name), and Mate's gestures (by "mate", via "gesture").
    after=<id>: only newer messages. wait=N: if there are none yet, wait up to N seconds
    (max 60) for one, so an agent can loop on this to follow the conversation. by=player: only
    people's messages."""
    deadline = time.monotonic() + min(max(wait, 0), 60)
    while True:
        items = [i for i in chat.since(after) if by is None or i["by"] == by]
        if items or time.monotonic() >= deadline:
            return items
        await asyncio.sleep(0.2)


class ChatPost(BaseModel):
    text: str
    by: str = "player"      # "player" from the talk page; an agent may post as itself


@app.post("/api/chat")
def post_chat(body: ChatPost):
    """Add a typed message to the chat (not spoken; for spoken lines use /api/say)."""
    if body.by == "mate":
        raise HTTPException(400, "Mate talks with gestures: /api/mate/gesture")
    item = chat.add(body.text[:2000], body.by[:32], "typed")
    if not item:
        raise HTTPException(400, "empty message")
    return item


@app.delete("/api/chat")
def clear_chat():
    chat.clear()
    return {"cleared": True}


@app.get("/api/transcripts")
def get_transcripts(since: int = 0):
    """Old name: the chat (see /api/chat)."""
    return chat.since(since)


@app.websocket("/ws/listen")
async def listen(ws: WebSocket):
    """Live speech to text for one utterance. The page sends 16 kHz mono PCM16 as binary frames
    while the person talks, then the text "end". It gets {"type": "partial", text} as words are
    recognised, then {"type": "final", item} (item is the chat message, or null if nothing was
    said) or {"type": "error", error}. Every page also gets `chat_partial` events."""
    await ws.accept()
    deadline = time.monotonic() + 90             # one utterance; Meta allows far more

    async def audio():
        while time.monotonic() < deadline:
            m = await ws.receive()
            if m["type"] == "websocket.disconnect":
                return
            if m.get("bytes"):
                yield m["bytes"]
            elif m.get("text") == "end":
                return

    async def partial(text):
        await ws.send_json({"type": "partial", "text": text})
        broadcast({"type": "chat_partial", "text": text})

    try:
        item = await chat.stream(audio(), partial)
        await ws.send_json({"type": "final", "item": item})
    except TranscribeError as e:
        await ws.send_json({"type": "error", "error": str(e)})
    except WebSocketDisconnect:
        pass
    finally:
        broadcast({"type": "chat_partial", "text": None})
        with contextlib.suppress(Exception):
            await ws.close()


@app.websocket("/ws")
async def ws(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    await ws.send_json({"type": "settings", "settings": grbl.settings})
    await ws.send_json({"type": "status", **grbl.status, "homed": grbl.homed})
    await ws.send_json({"type": "gripper", **gripper.state})
    try:
        while True:
            await ws.receive_text()  # keepalive only; commands go over HTTP
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)
        # a page that goes away mid-jog must not leave the gantry running
        if not clients and grbl.status.get("state") == "Jog":
            grbl.realtime("jog_cancel")


@app.get("/")
def home_page():
    """The home page: every page and tool on the table, in one list."""
    return FileResponse(HERE / "static" / "home.html", headers={"Cache-Control": "no-cache"})


@app.get("/jog")
def jog_page():
    return FileResponse(HERE / "static" / "jog.html", headers={"Cache-Control": "no-cache"})


GUIDES = HERE / "agent"   # the repo's agent/ folder, deployed next to the hub


@app.get("/api/guide", response_class=PlainTextResponse)
def guide():
    """Start here: what the table and Mate can do and how to behave (agent/README.md). The agent
    reads this first, then /api/guide/table, /api/guide/mate and /api/notes."""
    return (GUIDES / "README.md").read_text()


@app.get("/api/guide/{name}", response_class=PlainTextResponse)
def guide_page_text(name: str):
    path = GUIDES / f"{name}.md"
    if not name.isidentifier() or not path.exists():
        raise HTTPException(404, f"no guide {name}; try table or mate")
    return path.read_text()


@app.get("/guide")
def guide_page():
    return FileResponse(HERE / "static" / "guide.html", headers={"Cache-Control": "no-cache"})


NOTES = HERE / "notes.md"   # this build's notes; lives on the Pi only (not deployed, not in git)


class Note(BaseModel):
    text: str
    by: str = "agent"


@app.get("/api/notes", response_class=PlainTextResponse)
def notes():
    """What agents and people have learned about this particular build. Read after the guide."""
    return NOTES.read_text() if NOTES.exists() else "# Notes on this build\n\n(none yet)\n"


@app.post("/api/notes")
def add_note(body: Note):
    """Add one dated note: something learned about this build that the next agent should know."""
    if not NOTES.exists():
        NOTES.write_text("# Notes on this build\n\nWhat agents and people learned about this particular table. "
                         "Newest at the bottom. Add with POST /api/notes {text, by}.\n\n")
    line = " ".join(body.text.split())
    with NOTES.open("a") as f:
        f.write(f"- {time.strftime('%Y-%m-%d %H:%M')} ({body.by}): {line}\n")
    return {"ok": True}


@app.get("/vision")
def vision_page():
    return FileResponse(HERE / "static" / "vision.html", headers={"Cache-Control": "no-cache"})


@app.get("/eyes")
def eyes_page():
    return RedirectResponse("/vision")   # the old name


@app.get("/scene")
def scene_page():
    return FileResponse(HERE / "static" / "scene.html", headers={"Cache-Control": "no-cache"})


@app.get("/talk")
def talk():
    return FileResponse(HERE / "static" / "talk.html", headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
