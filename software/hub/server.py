"""Table hub web server: GRBL, the gripper and the cameras over HTTP + a live WebSocket, and the jog page.

Run on the Pi:  uvicorn server:app --host 0.0.0.0 --port 8000
"""

import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import camera
from grbl import REALTIME, Grbl
from gripper import SEQUENCES, Gripper

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


@app.post("/api/jog")
async def jog(body: Jog):
    """Relative jog ($J). Cancel early with /api/realtime/jog_cancel."""
    axes = "".join(f"{a}{v:.3f}" for a, v in (("X", body.x), ("Y", body.y), ("Z", body.z)) if v)
    if not axes:
        raise HTTPException(400, "nothing to jog")
    return await asyncio.to_thread(run, f"$J=G91 G21 {axes} F{body.feed:.0f}")


@app.post("/api/move")
async def move(body: Move):
    """Absolute move in work coordinates."""
    axes = "".join(f"{a}{v:.3f}" for a, v in (("X", body.x), ("Y", body.y), ("Z", body.z)) if v is not None)
    if not axes:
        raise HTTPException(400, "nothing to move")
    cmd = f"G90 G1 {axes} F{body.feed:.0f}" if body.feed else f"G90 G0 {axes}"
    return await asyncio.to_thread(run, cmd)


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
    return {"sent": grbl.realtime(name)}


@app.get("/api/gripper")
def gripper_state():
    return gripper.state


@app.post("/api/gripper/{name}")
async def gripper_command(name: str):
    """pump_on, pump_off, valve_on, valve_off, grip, drop, stop. Queued after any motion."""
    if name not in SEQUENCES:
        raise HTTPException(404, f"unknown: {name}")
    return await asyncio.to_thread(gripper.run, name)


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
def index():
    return FileResponse(HERE / "static" / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
