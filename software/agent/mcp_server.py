#!/usr/bin/env python3
"""Magic Table MCP server -- one server, on the Raspberry Pi hub.

Run on the Pi, next to the hub (``software/hub/server.py``)::

    python3 mcp_server.py            # stdio MCP, hub at http://localhost:8000
    MAGIC_TABLE_HUB_URL=http://raspberrypi.local:8000 python3 mcp_server.py

Design (see ``agent/README.md`` and ``docs/architecture.md``):

* The MCP server is a *thin* wrapper over the hub HTTP API. It never talks
  to GRBL, to Mate's own API (``mate.local``), or to any serial port.
  Mate is driven only through the hub (``/api/mate/*``), so the hub's
  safety layer -- board bounds, Z limits, travel height, Mate no-go zone,
  camera-checked paths -- stays between the model and the hardware.
* There is deliberately NO tool for ``/api/send`` (raw G-code, unchecked),
  no tool for GRBL settings, no full recalibration, and no direct Mate
  ``/step`` / ``/servo`` / ``/screen`` tool. Those would bypass the hub.
* Vision is tiered, exactly as the hub already implements it in
  ``software/hub/eyes.py`` (see the audit in ``MCP_README.md``):
    - ``get_scene``: free OpenCV scene, no cloud call, every ~0.5 s.
    - ``see``: Muse Spark (``muse-spark-1.3``) names kinds of things.
    - ``find``: SAM 3.1 (``sam-3.1``) segments, Muse Spark verifies the
      robot-near matches. ``effort`` defaults to ``minimal`` (validated:
      same card answers in 0.5-2 s vs ~15 s at default effort); use
      ``high`` for Mate-camera close-ups (counts, peeks), where
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
GUIDE_NAMES = ("guide", "table", "mate", "poker")
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
    if v not in ("0", "1", "mate"):
        raise ValueError("cam must be 0, 1, or mate (mate gives pixels only, no board mm)")
    return v

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


@tool("get_guide", "Read a guide FIRST, before moving anything. 'guide' is the start-here page, then 'table' (gantry/gripper/safety/recipes), 'mate' (Mate robot), 'poker' (the game). Then read get_notes.", _schema({"name": {"type": "string", "enum": list(GUIDE_NAMES)}}))
def _t_guide(hub, a):
    name = a.get("name", "guide")
    if name not in GUIDE_NAMES:
        raise ValueError("name must be guide, table, mate, or poker")
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


@tool("get_scene", "FREE, no cloud call, ~0.5 s: head/cup, Mate, face-up cards (cached names), chip stacks, decks, board markers, in board mm. Use first, always. Caveats: touching cards merge/vanish, deck +/-3, chip counts +/-1 near x.5. Keep your own game state and use scene to check it, not replace it.", _schema({"fresh": {"type": "boolean"}}))
def _t_scene(hub, a):
    return _text(hub.get("/api/scene", {"fresh": "true" if a.get("fresh") else None}))


@tool("get_calibration", "Is the table calibrated, how well, does it need re-anchoring? Read before trusting positions after a reset.", _schema({}))
def _t_cal(hub, a):
    return _text(hub.get("/api/calibration"))


@tool("reanchor", "After a GRBL reset: restore work coordinates from the saved position. camera=true only when the head really moved.", _schema({"camera": {"type": "boolean"}}))
def _t_reanchor(hub, a):
    return _text(hub.post("/api/calibration/reanchor", query={"camera": "true" if a.get("camera") else None}))


@tool("see", "TIER 2 vision (Muse Spark, ~2 s): what KINDS of loose things are on the board, with counts and a fallback '<colour> object' name for find. Park the gantry head first -- the Z bar hides things and the hub does not warn you. effort defaults to minimal; use high only for Mate-camera close-ups.", _schema({"cam": {"type": "string"}, "ask": {"type": "string"}, "effort": {"type": "string", "enum": list(EFFORTS)}}))
def _t_see(hub, a):
    return _text(hub.get("/api/see", {"cam": _cam(a.get("cam", "1")), "ask": a.get("ask"), "effort": _effort(a.get("effort"))}))


@tool("find", "TIER 3 vision (SAM 3.1, ~3-6 s): WHERE each thing is, in board mm, with pick {x, y, clear_mm}, on_board, and (for cards/decks/chips) real place/height/count. Pass names from see, with fallbacks after '|', e.g. 'playing card|white object'. SAM has no confidence scores and is fussy about names; the hub's Muse Spark verify drops robot parts (cup as plate, wheel as knife) -- matches >60% inside the robot are dropped unless Muse keeps them, only first 12 matches are numbered. Park the head first. cam=mate gives pixels only, never board mm.", _schema({"what": {"type": "string"}, "cam": {"type": "string"}, "ask": {"type": "string"}, "effort": {"type": "string", "enum": list(EFFORTS)}, "height": {"type": "boolean"}, "diameter": {"type": "number"}}, ["what"]))
def _t_find(hub, a):
    return _text(hub.get("/api/find", {"what": a["what"], "cam": _cam(a.get("cam", "1")), "ask": a.get("ask"), "effort": _effort(a.get("effort")), "height": "true" if a.get("height") else None, "diameter": a.get("diameter")}))


@tool("find_check", "After a pick, with the item lifted: did item <id> of the LAST find leave its spot? gone=true means it came up (change > 0.35). gone=false: check Z first, then re-zero.", _schema({"id": {"type": "integer"}}, ["id"]))
def _t_check(hub, a):
    return _text(hub.get("/api/find/check", {"id": int(a["id"])}))


@tool("get_cards", "Face-up cards, named: cache first (ms, no API, score>=0.75 margin>=0.08), Muse Spark only for unknown cards, cached only at confidence >= 0.9. Face-down cards are never named. Treat Muse confidence as a hint, not proof -- 0.8 has been wrong on Mate-camera reads.", _schema({"effort": {"type": "string", "enum": list(EFFORTS)}}))
def _t_cards(hub, a):
    return _text(hub.get("/api/cards", {"effort": _effort(a.get("effort"))}))


@tool("capture_image", "A fresh JPEG from cam 0 or 1, returned as an MCP image block. Use sparingly: pictures cost 1-2k tokens each. Prefer get_scene / see / find.", _schema({"cam": {"type": "integer"}}, ["cam"]))
def _t_capture(hub, a):
    cam = int(a["cam"])
    if cam not in (0, 1):
        raise ValueError("cam must be 0 or 1")
    jpg = hub.get("/api/capture", {"cam": cam}, raw=True)
    return [{"type": "image", "data": base64.b64encode(jpg).decode(), "mimeType": "image/jpeg"}], False

@tool("move_tip", "Put the CUP TIP (not the head) at board x, y, optionally at height z (cup height above the board, mm). Use for picks/places. Hub enforces board bounds, Z -1..150, travel height 110 over Mate. Go across at height, then straight down.", _schema({"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}, "feed": {"type": "number"}}, ["x", "y"]))
def _t_tip(hub, a):
    body = {"x": _num(a["x"], "x", -400, 400), "y": _num(a["y"], "y", -400, 400)}
    if a.get("z") is not None:
        body["z"] = _num(a["z"], "z", -1, 150)
    if a.get("feed") is not None:
        body["feed"] = _num(a["feed"], "feed", 1, 12000)
    return _text(hub.post("/api/tip", body))


@tool("move_head", "Move the HEAD MARKER (GRBL position), not the cup. Prefer move_tip for board work; use this for parking the head out of the cameras' way.", _schema({"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}, "feed": {"type": "number"}}))
def _t_move(hub, a):
    body = {}
    for k in ("x", "y"):
        if a.get(k) is not None:
            body[k] = _num(a[k], k, -400, 400)
    if a.get("z") is not None:
        body["z"] = _num(a["z"], "z", -1, 150)
    if a.get("feed") is not None:
        body["feed"] = _num(a["feed"], "feed", 1, 12000)
    if not body:
        raise ValueError("give at least one of x, y, z")
    return _text(hub.post("/api/move", body))


@tool("jog", "Relative jog in mm. Z jogs stop at limits, X/Y at board bounds, jogs will not press into Mate.", _schema({"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}, "feed": {"type": "number"}}))
def _t_jog(hub, a):
    body = {"x": _num(a.get("x", 0), "x", -200, 200), "y": _num(a.get("y", 0), "y", -200, 200), "z": _num(a.get("z", 0), "z", -200, 200), "feed": _num(a.get("feed", 3000), "feed", 1, 12000)}
    return _text(hub.post("/api/jog", body))


@tool("gripper", "Gripper: grip (pump on, stays on), drop (vent 0.3 s), pump_on/off, valve_on/off, stop. grip with pump_s=N pumps N s then holds on vacuum ~20 s. A card needs ~1 s pump, peel at F1500, not F2000.", _schema({"action": {"type": "string", "enum": list(GRIPPER_ACTIONS)}, "pump_s": {"type": "number"}}, ["action"]))
def _t_grip(hub, a):
    act = a["action"]
    if act not in GRIPPER_ACTIONS:
        raise ValueError(f"gripper action must be one of {GRIPPER_ACTIONS}")
    q = {"pump_s": a["pump_s"]} if a.get("pump_s") is not None else None
    return _text(hub.post(f"/api/gripper/{act}", query=q))


@tool("home_gantry", "GRBL homing ($H). Use after a reset / at start, then reanchor. This homes the gantry, it is not Mate's home.", _schema({}))
def _t_home(hub, a):
    return _text(hub.post("/api/home"))


@tool("stop_gantry", "STOP: feed hold, then reset. After a STOP, reanchor before moving again.", _schema({}))
def _t_stop(hub, a):
    hub.post("/api/realtime/hold")
    return _text(hub.post("/api/realtime/reset"))


@tool("mate_goto", "Drive Mate VIA THE HUB so its turning centre ends at (x, y) and faces heading (optional). check=true (default) makes cam 1 check the way first and refuses with in_the_way if anything is on the mat there; check=false only for a short hop you have just looked at, or to push chips on purpose. Mate drives over lying cards but not stacks.", _schema({"x": {"type": "number"}, "y": {"type": "number"}, "heading": {"type": "number"}, "check": {"type": "boolean"}}, ["x", "y"]))
def _t_mgoto(hub, a):
    body = {"x": _num(a["x"], "x", -400, 400), "y": _num(a["y"], "y", -400, 400), "check": bool(a.get("check", True))}
    if a.get("heading") is not None:
        body["heading"] = _num(a["heading"], "heading", -360, 360)
    return _text(hub.post("/api/mate/goto", body))


@tool("mate_home", "Send Mate home VIA THE HUB. Park the gantry head at the build's park spot first, or the gantry's wires can hide Mate's marker.", _schema({}))
def _t_mhome(hub, a):
    return _text(hub.post("/api/mate/home"))


@tool("get_mate_home", "Where Mate's home spot is.", _schema({}))
def _t_mhome_get(hub, a):
    return _text(hub.get("/api/mate/home"))


@tool("mate_look", "Send Mate to look at (x, y) with its own camera, from distance mm (default 150), from side degrees if given, then use see/find with cam=mate. ~20 s. Mate-camera reads need effort=high and a second opinion: a single hold/peek at confidence 0.8 has been wrong in testing.", _schema({"x": {"type": "number"}, "y": {"type": "number"}, "distance": {"type": "number"}, "side": {"type": "number"}, "check": {"type": "boolean"}}, ["x", "y"]))
def _t_mlook(hub, a):
    body = {"x": _num(a["x"], "x", -400, 400), "y": _num(a["y"], "y", -400, 400), "distance": _num(a.get("distance", 150), "distance", 50, 400), "check": bool(a.get("check", True))}
    if a.get("side") is not None:
        body["side"] = _num(a["side"], "side", -360, 360)
    return _text(hub.post("/api/mate/look", body))


@tool("mate_gestures", "List Mate's gestures by name. Mate never speaks; gestures are how it talks.", _schema({}))
def _t_mgestures(hub, a):
    return _text(hub.get("/api/mate/gestures"))


@tool("mate_gesture", "Play a Mate gesture VIA THE HUB: face, flipper and wheel moves ending where they started, plus a chat line as Mate. wait=true blocks until done. Refused while Mate is busy. If Mate does not answer, it may have browned out: cover in character, wait ~30 s, then play woke_up.", _schema({"name": {"type": "string"}, "to": {"type": "string"}, "wait": {"type": "boolean"}, "text": {"type": "string"}, "face": {"type": "string"}, "emoji": {"type": "string"}, "steps": {"type": "array", "items": {"type": "object"}}}))
def _t_mgesture(hub, a):
    body = {"wait": bool(a.get("wait", False))}
    for k in ("name", "to", "text", "face", "emoji", "steps"):
        if a.get(k) is not None:
            body[k] = a[k]
    if not body.get("name") and not body.get("text"):
        raise ValueError("give a gesture name, or text for a one-off")
    return _text(hub.post("/api/mate/gesture", body))


@tool("say", "Speak on the table's speaker (Piper, local) and add the line to the chat under by (your own name, e.g. 'Muse'). Use to announce, to ask humans when stuck, and to say what Mate is doing before you send it. by must not be 'player' or 'mate'.", _schema({"text": {"type": "string"}, "by": {"type": "string"}, "wait": {"type": "boolean"}}, ["text"]))
def _t_say(hub, a):
    by = (a.get("by") or "agent")[:32]
    if by in ("player", "mate"):
        raise ValueError("by must be your own name, not player or mate")
    return _text(hub.post("/api/say", {"text": a["text"][:1000], "by": by, "wait": bool(a.get("wait", False))}))


@tool("chat_poll", "SUBSCRIBE to the transcript (this IS the subscription -- do not build a separate WebSocket subscription for v1). The hub already turns player speech into final chat items via Muse Voice Transcribe (realtime, partials ~0.3 s on pages, final ~0.1 s after they stop, keyword-biased); partials are NOT in this list, only final messages, which is what you should act on. Poll with after=<last id you have seen>, wait up to 60 s (long-poll); the call returns as soon as something new arrives. Keep the highest id and pass it next time. Loop while waiting for players; an empty poll is not the end of the game. by=player filters to people only.", _schema({"after": {"type": "integer"}, "wait": {"type": "number"}, "by": {"type": "string"}}))
def _t_chat(hub, a):
    wait = min(max(float(a.get("wait", 0) or 0), 0), 60)
    return _text(hub.get("/api/chat", {"after": int(a.get("after", 0)), "wait": wait, "by": a.get("by")}))


@tool("chat_post", "Add a typed message to the chat (not spoken; use say for speech). by must not be 'mate' -- Mate talks with gestures.", _schema({"text": {"type": "string"}, "by": {"type": "string"}}, ["text"]))
def _t_chat_post(hub, a):
    by = (a.get("by") or "player")[:32]
    if by == "mate":
        raise ValueError("Mate talks with gestures, not chat_post")
    return _text(hub.post("/api/chat", {"text": a["text"][:2000], "by": by}))


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
            if name in ("send_gcode", "raw_gcode", "mate_step", "mate_servo", "mate_screen", "calibrate", "delete_chat", "grbl_settings"):
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
    log(f"magic-table MCP: hub at {hub.base} (Mate only via hub; no raw G-code tool)")
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
