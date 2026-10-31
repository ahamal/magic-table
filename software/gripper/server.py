"""Gripper web server: pump and vent valve switches over HTTP + a live WebSocket.

Separate from the GRBL hub so either can restart on its own.
Run on the Pi:  uvicorn server:app --host 0.0.0.0 --port 8001
"""

import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from nano import COMMANDS, Nano

HERE = Path(__file__).parent
PORT = "/dev/serial/by-id/usb-1a86_USB2.0-Serial-if00-port0"
nano = Nano(os.environ.get("GRIPPER_PORT", PORT))
app = FastAPI(title="Magic Table gripper")
clients = set()
loop = None


def broadcast(state):
    """Called from the serial thread; hands the state to the asyncio loop."""
    if loop:
        for ws in list(clients):
            asyncio.run_coroutine_threadsafe(_send(ws, state), loop)


async def _send(ws, state):
    try:
        await ws.send_json(state)
    except Exception:
        clients.discard(ws)


@app.on_event("startup")
async def startup():
    global loop
    loop = asyncio.get_running_loop()
    nano.listeners.append(broadcast)
    nano.start()


@app.get("/api/state")
def state():
    return nano.state


@app.post("/api/{name}")
async def command(name: str):
    """pump_on, pump_off, valve_on, valve_off, grip, drop, stop, status."""
    if name not in COMMANDS:
        raise HTTPException(404, f"unknown: {name}")
    st = await asyncio.to_thread(nano.send, name)
    if st is None:
        raise HTTPException(503, "Nano not connected")
    return st


@app.websocket("/ws")
async def ws(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    await ws.send_json(nano.state)
    try:
        while True:
            await ws.receive_text()  # keepalive only; commands go over HTTP
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)


@app.get("/")
def index():
    return FileResponse(HERE / "static" / "index.html", headers={"Cache-Control": "no-cache"})
