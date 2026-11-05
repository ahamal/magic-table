#!/usr/bin/env python3
"""Magic Table MCP server -- one server, on the Raspberry Pi hub.

Run on the Pi, next to the hub (``software/hub/server.py``)::

    python3 mcp_server.py            # stdio MCP, hub at http://localhost:8000
    MAGIC_TABLE_HUB_URL=http://raspberrypi.local:8000 python3 mcp_server.py

Design (see ``agent/README.md`` and ``docs/architecture.md``):

* The MCP server is a *thin* wrapper over the hub HTTP API. It never talks
  to GRBL, to Esper's own API (``esper.local``), or to any serial port.
  Esper is driven only through the hub (``/api/esper/*``), so the hub's
  safety layer -- board bounds, Z limits, travel height, Esper no-go zone,
  camera-checked paths -- stays between the model and the hardware.
* There is deliberately NO tool for ``/api/send`` (raw G-code, unchecked;
  ``unlock`` sends exactly ``$X`` and nothing else), no homing (``$H``: this
  build has no limit switches, so homing would drive the axes into the
  frame), no tool for GRBL settings, no full recalibration, and no direct
  Esper ``/step`` / ``/servo`` / ``/screen`` tool. Esper's flipper and wheels
  go through the hub's ``/api/esper/move``, which caps the flipper speed and
  keeps the hub's idea of where Esper is right.
* Vision is tiered, exactly as the hub already implements it in
  ``software/hub/eyes.py`` (see the audit in ``MCP_README.md``):
    - ``get_scene``: free OpenCV scene, no cloud call, every ~0.5 s.
    - ``see``: Muse Spark (``muse-spark-1.3``) names kinds of things.
    - ``find``: SAM 3.1 (``sam-3.1``) segments, Muse Spark verifies the
      robot-near matches. ``effort`` defaults to ``minimal`` (validated:
      same card answers in 0.5-2 s vs ~15 s at default effort); use
      ``high`` for Esper-camera close-ups (counts, peeks), where
      ``minimal``/``low`` miscounted in testing.
    - ``get_cards``: card cache first (milliseconds, no API), Muse Spark
      only for unknown face-up cards, cached only at confidence >= 0.9.
  Do not flatten these tiers into one "look" tool: the agent must choose
  the cheapest tier that answers its question, and must park the gantry
  head before ``see``/``find`` (the Z bar hides board items otherwise --
  the hub does not warn about this).

Stdlib only: no ``mcp`` / ``fastmcp`` package is needed on the Pi, so this
runs in the hub's existing venv. Protocol is MCP over stdio (JSON-RPC 2.0,
newline-delimited). Logging goes to stderr only -- stdout is the protocol.
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HUB_URL = os.environ.get("MAGIC_TABLE_HUB_URL", "http://localhost:8000").rstrip("/")
EFFORTS = ("minimal", "low", "medium", "high")
GUIDE_NAMES = ("guide", "table", "esper", "poker")
GRIPPER_ACTIONS = ("pump_on", "pump_off", "valve_on", "valve_off", "grip", "drop", "stop")


def log(*args):
    print(*args, file=sys.stderr, flush=True)


class HubError(Exception):
    pass


class Hub:
    """Minimal hub client. ``path`` is a hub endpoint *without* the host."""

    def __init__(self, base, timeout=90):
        self.base = base.rstrip("/")
        self.timeout = timeout

    def _url(self, path, query=None):
        url = self.base + path
        if query:
            q = {k: v for k, v in query.items() if v is not None}
            if q:
                url += "?" + urllib.parse.urlencode(q)
        return url

    def get(self, path, query=None, raw=False):
        req = urllib.request.Request(self._url(path, query), method="GET")
        return self._do(req, raw=raw)

    def post(self, path, body=None, query=None):
        data = json.dumps(body or {}).encode() if body is not None else b"{}"
        req = urllib.request.Request(self._url(path, query), data=data,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        return self._do(req)

    def delete(self, path):
        req = urllib.request.Request(self._url(path), method="DELETE")
        return self._do(req)

    def _do(self, req, raw=False):
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = r.read()
        except urllib.error.HTTPError as e:
            raise HubError(f"hub {e.code}: {e.read().decode(errors='replace')[:500]}")
        except OSError as e:
            raise HubError(f"cannot reach hub at {self.base}: {e}")
        if raw:
            return data
        if not data:
            return {}
        try:
            return json.loads(data)
        except ValueError:
            return {"text": data.decode(errors="replace")}


def _num(value, name, lo, hi):
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number")
    if not (lo <= v <= hi):
        raise ValueError(f"{name} {v} is outside {lo}..{hi} (the hub enforces this too)")
    return v


def _effort(value):
    v = (value or "minimal")
    if v not in EFFORTS:
        raise ValueError(f"effort must be one of {EFFORTS}")
    return v


def _cam(value):
    v = str(value or "1")
    if v not in ("0", "1", "esper"):
        raise ValueError("cam must be 0, 1, or esper (esper gives pixels only, no board mm)")
    return v

def _opt(value):
    """A text argument, or None when the model sent a stand-in for nothing ("", "null", "none")."""
    if value is None or str(value).strip().lower() in ("", "null", "none", "undefined"):
        return None
    return value


def _text(obj):
    text = obj if isinstance(obj, str) else json.dumps(obj, indent=2, ensure_ascii=False)
    return [{"type": "text", "text": text}], False


def _err(msg):
    return [{"type": "text", "text": f"error: {msg}"}], True


def _raw_text(hub, path):
    req = urllib.request.Request(hub.base + path, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=hub.timeout) as r:
            return r.read().decode()
    except urllib.error.HTTPError as e:
        raise HubError(f"hub {e.code}: {e.read().decode(errors='replace')[:500]}")
    except OSError as e:
        raise HubError(f"cannot reach hub: {e}")


TOOLS = {}


def tool(name, description, schema):
    def wrap(fn):
        TOOLS[name] = (description, schema, fn)
        return fn
    return wrap


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}


@tool("get_guide", "Read a guide FIRST, before moving anything. 'guide' is the start-here page, then 'table' (gantry/gripper/safety/recipes), 'esper' (Esper robot), 'poker' (the game). Then read get_notes.", _schema({"name": {"type": "string", "enum": list(GUIDE_NAMES)}}))
def _t_guide(hub, a):
    name = a.get("name", "guide")
    if name not in GUIDE_NAMES:
        raise ValueError("name must be guide, table, esper, or poker")
    path = "/api/guide" if name == "guide" else f"/api/guide/{name}"
    return _text(_raw_text(hub, path))


@tool("get_notes", "This build's notes: calibration numbers, park spot, what failed before. Read after the guides, and add to them as you learn.", _schema({}))
def _t_notes(hub, a):
    return _text(_raw_text(hub, "/api/notes"))


@tool("add_note", "Add one dated note about this build.", _schema({"text": {"type": "string"}, "by": {"type": "string"}}, ["text"]))
def _t_add_note(hub, a):
    return _text(hub.post("/api/notes", {"text": a["text"], "by": a.get("by", "agent")}))


@tool("get_status", "GRBL state, work/machine position, homed flag.", _schema({}))
def _t_status(hub, a):
    return _text(hub.get("/api/status"))


@tool("get_scene", "FREE, no cloud call, ~0.5 s: head/cup, Esper, face-up cards (cached names), chip stacks, decks, board markers, in board mm. Use first, always. Caveats: touching cards merge/vanish, deck +/-3, chip counts +/-1 near x.5. Keep your own game state and use scene to check it, not replace it.", _schema({"fresh": {"type": "boolean"}}))
def _t_scene(hub, a):
    return _text(hub.get("/api/scene", {"fresh": "true" if a.get("fresh") else None}))


@tool("get_calibration", "Is the table calibrated, how well, does it need re-anchoring? Read before trusting positions after a reset.", _schema({}))
def _t_cal(hub, a):
    return _text(hub.get("/api/calibration"))


@tool("reanchor", "After a GRBL reset, once unlocked: restore work coordinates from the saved position. camera=true only when the head really moved (skipped steps, moved by hand).", _schema({"camera": {"type": "boolean"}}))
def _t_reanchor(hub, a):
    return _text(hub.post("/api/calibration/reanchor", query={"camera": "true" if a.get("camera") else None}))


@tool("see", "TIER 2 vision (Muse Spark, ~2 s): what KINDS of loose things are on the board, with counts and a fallback '<colour> object' name for find. Park the gantry head first -- the Z bar hides things and the hub does not warn you. effort defaults to minimal; use high only for Esper-camera close-ups.", _schema({"cam": {"type": "string"}, "ask": {"type": "string"}, "effort": {"type": "string", "enum": list(EFFORTS)}, "by": {"type": "string"}}))
def _t_see(hub, a):
    return _text(hub.get("/api/see", {"cam": _cam(a.get("cam", "1")), "ask": _opt(a.get("ask")), "effort": _effort(a.get("effort")), "by": _opt(a.get("by"))}))


@tool("find", "TIER 3 vision (SAM 3.1, ~3-6 s): WHERE each thing is, in board mm, with pick {x, y, clear_mm}, on_board, and (for cards/decks/chips) real place/height/count. Pass names from see, with fallbacks after '|', e.g. 'playing card|white object'. SAM has no confidence scores and is fussy about names; the hub's Muse Spark verify drops robot parts (cup as plate, wheel as knife) -- matches >60% inside the robot are dropped unless Muse keeps them, only first 12 matches are numbered. Park the head first. cam=esper gives pixels only, never board mm.", _schema({"what": {"type": "string"}, "cam": {"type": "string"}, "ask": {"type": "string"}, "effort": {"type": "string", "enum": list(EFFORTS)}, "height": {"type": "boolean"}, "diameter": {"type": "number"}, "by": {"type": "string"}}, ["what"]))
def _t_find(hub, a):
    return _text(hub.get("/api/find", {"what": a["what"], "cam": _cam(a.get("cam", "1")), "ask": _opt(a.get("ask")), "effort": _effort(a.get("effort")), "height": "true" if a.get("height") else None, "diameter": a.get("diameter"), "by": _opt(a.get("by"))}))


@tool("find_check", "After a pick, with the item lifted: did item <id> of the LAST find leave its spot? gone=true means it came up (change > 0.35). gone=false: check Z first, then re-zero.", _schema({"id": {"type": "integer"}, "by": {"type": "string"}}, ["id"]))
def _t_check(hub, a):
    return _text(hub.get("/api/find/check", {"id": int(a["id"]), "by": a.get("by")}))


@tool("get_cards", "Face-up cards, named: cache first (ms, no API, score>=0.75 margin>=0.08), Muse Spark only for unknown cards, cached only at confidence >= 0.9. Face-down cards are never named. Treat Muse confidence as a hint, not proof -- 0.8 has been wrong on Esper-camera reads.", _schema({"effort": {"type": "string", "enum": list(EFFORTS)}}))
def _t_cards(hub, a):
    return _text(hub.get("/api/cards", {"effort": _effort(a.get("effort"))}))


@tool("capture_image", "A fresh JPEG from cam 0 or 1, returned as an MCP image block. Use sparingly: pictures cost 1-2k tokens each. Prefer get_scene / see / find.", _schema({"cam": {"type": "integer"}}, ["cam"]))
def _t_capture(hub, a):
    cam = int(a["cam"])
    if cam not in (0, 1):
        raise ValueError("cam must be 0 or 1")
    jpg = hub.get("/api/capture", {"cam": cam}, raw=True)
    return [{"type": "image", "data": base64.b64encode(jpg).decode(), "mimeType": "image/jpeg"}], False

@tool("move_tip", "Put the CUP TIP (not the head) at board x, y, optionally at height z (cup height above the board, mm). Never moves diagonally: with z, it rises to the travel height (110) if lower, crosses, then goes straight down to z. direct=true crosses at the current height instead, for a nudge of a few mm. feed applies to the last (vertical) part. Hub enforces board bounds, Z -2..150, and Esper.", _schema({"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}, "feed": {"type": "number"}, "direct": {"type": "boolean"}}, ["x", "y"]))
def _t_tip(hub, a):
    xy = {"x": _num(a["x"], "x", -400, 400), "y": _num(a["y"], "y", -400, 400)}
    z = _num(a["z"], "z", -2, 150) if a.get("z") is not None else None
    feed = _num(a["feed"], "feed", 1, 12000) if a.get("feed") is not None else None
    steps = []
    if z is not None and not a.get("direct"):
        # across high, then straight down: never lower first and then cross at a slant
        travel = hub.get("/api/calibration").get("travel_z") or 110
        now = (hub.get("/api/status").get("WPos") or [0, 0, 0])[2]
        if now < max(travel, z):
            steps.append(("/api/move", {"z": max(travel, z)}))
    steps.append(("/api/tip", dict(xy)))
    if z is not None:
        steps.append(("/api/tip", {**xy, "z": z, **({"feed": feed} if feed else {})}))
    elif feed:
        steps[-1][1]["feed"] = feed
    replies = []
    for path, body in steps:
        r = hub.post(path, body)
        replies.append(r)
        if str(r.get("reply", "")).startswith("error"):
            return [{"type": "text", "text": json.dumps({"steps": replies}, indent=2)}], True
    return _text({"steps": replies})


@tool("move_head", "Move the HEAD MARKER (GRBL position), not the cup. Prefer move_tip for board work; use this for parking the head out of the cameras' way, and for straight up/down moves at a feed (z only: a card pick is z=-1.5 feed=600, the peel z=5 feed=1500). No feed = rapid.", _schema({"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}, "feed": {"type": "number"}}))
def _t_move(hub, a):
    body = {}
    for k in ("x", "y"):
        if a.get(k) is not None:
            body[k] = _num(a[k], k, -400, 400)
    if a.get("z") is not None:
        body["z"] = _num(a["z"], "z", -2, 150)
    if a.get("feed") is not None:
        body["feed"] = _num(a["feed"], "feed", 1, 12000)
    if not body:
        raise ValueError("give at least one of x, y, z")
    return _text(hub.post("/api/move", body))


@tool("jog", "Relative jog in mm. Z jogs stop at limits, X/Y at board bounds, jogs will not press into Esper.", _schema({"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}, "feed": {"type": "number"}}))
def _t_jog(hub, a):
    body = {"x": _num(a.get("x", 0), "x", -200, 200), "y": _num(a.get("y", 0), "y", -200, 200), "z": _num(a.get("z", 0), "z", -200, 200), "feed": _num(a.get("feed", 3000), "feed", 1, 12000)}
    return _text(hub.post("/api/jog", body))


@tool("gripper", "Gripper: grip (pump on, stays on), drop (vent 0.3 s), pump_on/off, valve_on/off, stop. grip with pump_s=N pumps N s then holds on vacuum ~20 s. A card needs ~1 s pump, peel at F1500, not F2000. Send a grip only inside a batch that also drops it. Holding a card up shows the cameras nothing: don't pick a card up to look at it.", _schema({"action": {"type": "string", "enum": list(GRIPPER_ACTIONS)}, "pump_s": {"type": "number"}}, ["action"]))
def _t_grip(hub, a):
    act = a["action"]
    if act not in GRIPPER_ACTIONS:
        raise ValueError(f"gripper action must be one of {GRIPPER_ACTIONS}")
    q = {"pump_s": a["pump_s"]} if a.get("pump_s") is not None else None
    return _text(hub.post(f"/api/gripper/{act}", query=q))


@tool("unlock", "Unlock GRBL after a reset or an alarm (sends $X, nothing else). Then reanchor before moving. There is no homing: this build has no limit switches.", _schema({}))
def _t_unlock(hub, a):
    return _text(hub.post("/api/send", {"line": "$X"}))


@tool("stop_gantry", "STOP: feed hold, then reset. After a STOP: unlock, then reanchor (compare camera_off_mm to choose camera=true or not) before moving again.", _schema({}))
def _t_stop(hub, a):
    hub.post("/api/realtime/hold")
    return _text(hub.post("/api/realtime/reset"))


@tool("esper_goto", "Drive Esper VIA THE HUB so its turning centre ends at (x, y) and faces heading (optional). check=true (default) makes cam 1 check the way first and refuses with in_the_way if anything is on the mat there; check=false only for a short hop you have just looked at, or to push chips on purpose. Esper drives over lying cards but not stacks.", _schema({"x": {"type": "number"}, "y": {"type": "number"}, "heading": {"type": "number"}, "check": {"type": "boolean"}}, ["x", "y"]))
def _t_mgoto(hub, a):
    body = {"x": _num(a["x"], "x", -400, 400), "y": _num(a["y"], "y", -400, 400), "check": bool(a.get("check", True))}
    if a.get("heading") is not None:
        body["heading"] = _num(a["heading"], "heading", -360, 360)
    return _text(hub.post("/api/esper/goto", body))


@tool("esper_home", "Send Esper home VIA THE HUB. Park the gantry head at the build's park spot first, or the gantry's wires can hide Esper's marker.", _schema({}))
def _t_mhome(hub, a):
    return _text(hub.post("/api/esper/home"))


@tool("get_esper_home", "Where Esper's home spot is.", _schema({}))
def _t_mhome_get(hub, a):
    return _text(hub.get("/api/esper/home"))


@tool("esper_look", "Send Esper to look at (x, y) with its own camera, from distance mm (default 150), from side degrees if given, then use see/find with cam=esper. ~20 s. Esper-camera reads need effort=high and a second opinion: a single hold/peek at confidence 0.8 has been wrong in testing.", _schema({"x": {"type": "number"}, "y": {"type": "number"}, "distance": {"type": "number"}, "side": {"type": "number"}, "check": {"type": "boolean"}}, ["x", "y"]))
def _t_mlook(hub, a):
    body = {"x": _num(a["x"], "x", -400, 400), "y": _num(a["y"], "y", -400, 400), "distance": _num(a.get("distance", 150), "distance", 50, 400), "check": bool(a.get("check", True))}
    if a.get("side") is not None:
        body["side"] = _num(a["side"], "side", -360, 360)
    return _text(hub.post("/api/esper/look", body))


@tool("esper_move", "One step of a Esper recipe (the flip, the peek: read the esper and poker guides first, never improvise one), VIA THE HUB: flipper to servo degrees (20 rest .. 150) at servo_speed (required, gentle: the peek uses 30, capped at 360 -- fast flipper moves brown Esper out), starting at once and running while Esper turns turn degrees and drives drive mm (+ forward, max 200) at wheel_speed (half-steps/s, 800 full, the peek creeps at 200). Returns when both are done; counted into where the hub thinks Esper is. No camera check of the way: drive only where you have looked.", _schema({"servo": {"type": "number"}, "servo_speed": {"type": "number"}, "turn": {"type": "number"}, "drive": {"type": "number"}, "wheel_speed": {"type": "number"}}))
def _t_mmove(hub, a):
    body = {}
    if a.get("servo") is not None:
        if a.get("servo_speed") is None:
            raise ValueError("give servo_speed with servo (gentle: 30-120)")
        body["servo"] = _num(a["servo"], "servo", 20, 150)
        body["servo_speed"] = _num(a["servo_speed"], "servo_speed", 1, 360)
    if a.get("turn") is not None:
        body["turn"] = _num(a["turn"], "turn", -360, 360)
    if a.get("drive") is not None:
        body["drive"] = _num(a["drive"], "drive", -200, 200)
    if a.get("wheel_speed") is not None:
        body["wheel_speed"] = _num(a["wheel_speed"], "wheel_speed", 50, 500)
    if not any(k in body for k in ("servo", "turn", "drive")):
        raise ValueError("give servo (+ servo_speed), turn or drive")
    return _text(hub.post("/api/esper/move", body))


@tool("esper_gestures", "List Esper's gestures by name. Esper never speaks; gestures are how it talks.", _schema({}))
def _t_mgestures(hub, a):
    return _text(hub.get("/api/esper/gestures"))


@tool("esper_gesture", "Play a Esper gesture VIA THE HUB: face, flipper and wheel moves ending where they started, plus a chat line as Esper. wait=true blocks until done. Refused while Esper is busy. If Esper does not answer, it may have browned out: cover in character, wait ~30 s, then play woke_up.", _schema({"name": {"type": "string"}, "to": {"type": "string"}, "wait": {"type": "boolean"}, "text": {"type": "string"}, "face": {"type": "string"}, "emoji": {"type": "string"}, "steps": {"type": "array", "items": {"type": "object"}}}))
def _t_mgesture(hub, a):
    body = {"wait": bool(a.get("wait", False))}
    for k in ("name", "to", "text", "face", "emoji", "steps"):
        if a.get(k) is not None:
            body[k] = a[k]
    if not body.get("name") and not body.get("text"):
        raise ValueError("give a gesture name, or text for a one-off")
    return _text(hub.post("/api/esper/gesture", body))


@tool("say", "Speak on the table's speaker (Piper, local) and add the line to the chat under by (your own name, e.g. 'Muse'). Use to announce, to ask humans when stuck, and to say what Esper is doing before you send it. by must not be 'player' or 'esper'.", _schema({"text": {"type": "string"}, "by": {"type": "string"}, "wait": {"type": "boolean"}}, ["text"]))
def _t_say(hub, a):
    by = (a.get("by") or "agent")[:32]
    if by in ("player", "esper"):
        raise ValueError("by must be your own name, not player or esper")
    return _text(hub.post("/api/say", {"text": a["text"][:1000], "by": by, "wait": bool(a.get("wait", False))}))


@tool("chat_poll", "SUBSCRIBE to the transcript (this IS the subscription -- do not build a separate WebSocket subscription for v1). The hub already turns player speech into final chat items via Muse Voice Transcribe (realtime, partials ~0.3 s on pages, final ~0.1 s after they stop, keyword-biased); partials are NOT in this list, only final messages, which is what you should act on. Poll with after=<last id you have seen>, wait up to 60 s (long-poll); the call returns as soon as something new arrives. Keep the highest id and pass it next time. Loop while waiting for players; an empty poll is not the end of the game. by=player filters to people only.", _schema({"after": {"type": "integer"}, "wait": {"type": "number"}, "by": {"type": "string"}}))
def _t_chat(hub, a):
    wait = min(max(float(a.get("wait", 0) or 0), 0), 60)
    return _text(hub.get("/api/chat", {"after": int(a.get("after", 0)), "wait": wait, "by": a.get("by")}))


@tool("esper_face", "Put a face on Esper's screen NOW and hold it (no move, no chat line) until the next face or gesture; 'eyes' is back to normal. Set it BEFORE anything slow so Esper looks alive: 'suspense' before a flip, 'curious' before a peek, 'thinking' while players decide. Faces: the reaction faces (happy, sad, shocked, love, laughing, smug, nervous, thinking, suspicious, wink, ...) plus curious, cheer, focused, suspense.", _schema({"name": {"type": "string"}}, ["name"]))
def _t_mface(hub, a):
    return _text(hub.post("/api/esper/face", {"name": str(a["name"])}))


@tool("chat_post", "Add a typed message to the chat under by, your own name (not spoken; use say for speech). by must not be 'player' (that's the people at the table) or 'esper' (Esper talks with gestures).", _schema({"text": {"type": "string"}, "by": {"type": "string"}}, ["text"]))
def _t_chat_post(hub, a):
    by = (a.get("by") or "agent")[:32]
    if by in ("player", "esper"):
        raise ValueError("by must be your own name: 'player' is the people at the table, and Esper talks with gestures")
    return _text(hub.post("/api/chat", {"text": a["text"][:2000], "by": by}))


BATCH_SKIP = ("batch", "chat_poll", "get_guide", "capture_image")   # no nesting, no long waits, no big reads


def _failed(content, is_err):
    """A step failed: the tool said so, or the hub answered with an error reply or ok: false."""
    if is_err:
        return True
    text = "".join(c.get("text", "") for c in content if c.get("type") == "text")
    return '"reply": "error' in text or '"ok": false' in text


@tool("batch", "Run several tools in ONE call, in order, stopping at the first failure: use it for every recipe step you'd otherwise send one by one (across, down, grip, peel, up; say + esper_gesture together). A batch with a grip must also carry the drop: never end a batch holding something (the vacuum lasts ~20 s, a round of thinking takes seconds). Look before the grip, not while holding. Each step is {tool, args}. Returns each step's result (shortened) and where it stopped. Not inside a batch: batch, chat_poll, get_guide, capture_image.", _schema({"steps": {"type": "array", "items": {"type": "object", "properties": {"tool": {"type": "string"}, "args": {"type": "object"}}, "required": ["tool"]}}}, ["steps"]))
def _t_batch(hub, a):
    steps = a.get("steps") or []
    if not steps:
        raise ValueError("give steps: [{tool, args}, ...]")
    done = []
    for i, step in enumerate(steps):
        name = step.get("tool")
        if name in BATCH_SKIP or name not in TOOLS:
            done.append({"step": i, "tool": name, "error": "not allowed in a batch" if name in BATCH_SKIP else "unknown tool"})
            return _text({"stopped_at": i, "steps": done}) [0], True
        try:
            content, is_err = TOOLS[name][2](hub, step.get("args") or {})
        except (ValueError, HubError) as e:
            content, is_err = _err(str(e))
        text = "".join(c.get("text", "") for c in content if c.get("type") == "text")
        done.append({"step": i, "tool": name, "result": text[:400]})
        if _failed(content, is_err):
            return _text({"stopped_at": i, "steps": done})[0], True
    return _text({"ok": True, "steps": done})


def _result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle(hub, req):
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params") or {}
    if method == "initialize":
        return _result(req_id, {"protocolVersion": params.get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {}}, "serverInfo": {"name": "magic-table", "version": "1.0.0"}})
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return _result(req_id, {})
    if method == "tools/list":
        tools = [{"name": n, "description": d, "inputSchema": s} for n, (d, s, _f) in sorted(TOOLS.items())]
        return _result(req_id, {"tools": tools})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name not in TOOLS:
            if name in ("send_gcode", "raw_gcode", "home_gantry", "esper_step", "esper_servo", "esper_screen", "calibrate", "delete_chat", "grbl_settings"):
                return _result(req_id, {"content": [{"type": "text", "text": f"error: {name} is intentionally not exposed: it would bypass the hub safety layer"}], "isError": True})
            return _error(req_id, -32602, f"unknown tool: {name}")
        _desc, _schema, fn = TOOLS[name]
        try:
            content, is_err = fn(hub, args)
        except (ValueError, HubError) as e:
            content, is_err = _err(str(e))
        except Exception as e:
            log(f"tool {name} failed: {e!r}")
            content, is_err = _err(f"{name} failed: {e}")
        return _result(req_id, {"content": content, "isError": is_err})
    if req_id is None:
        return None
    return _error(req_id, -32601, f"unknown method: {method}")


def main(argv=None):
    import argparse as _ap
    ap = _ap.ArgumentParser(description="Magic Table MCP server (stdio, via Pi hub)")
    ap.add_argument("--hub-url", default=HUB_URL)
    ap.add_argument("--list-tools", action="store_true", help="print tools/list JSON and exit (no hub needed)")
    args = ap.parse_args(argv)
    if args.list_tools:
        print(json.dumps({"tools": [{"name": n, "description": d, "inputSchema": s} for n, (d, s, _f) in sorted(TOOLS.items())]}, indent=2))
        return 0
    hub = Hub(args.hub_url)
    log(f"magic-table MCP: hub at {hub.base} (Esper only via hub; no raw G-code, no homing)")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        resp = handle(hub, req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
