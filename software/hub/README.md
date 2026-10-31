# Table hub (Pi 5)

The body API for the whole table. Step 2.

## Responsibilities

- **One web server** (FastAPI): the table body API (see [`docs/architecture.md`](../../docs/architecture.md#body-interface-table)) plus the human table page. WebSocket for events (`wait_for`) and the optional live view.
- **Frame driver:** GRBL over USB serial — homing, soft limits, `move_to`, probe (`G38.2`).
- **Gripper:** GRBL switches the 12V pump (`M8`/`M9`) and vent valve (`M4 S0`/`M3 S0`) through MOSFETs on the CNC Shield. The Pi never touches the 12V side.
- **Sensors:** VL6180X (`sense_z`), touch switch (`probe`).
- **Overhead camera:** `capture("overhead")`.
- **Mate client:** the only caller of Mate's API once the table is assembled; `capture("mate")` and `mate.*` pass through.
- **Safety layer:** soft limits, Z only lowers when clear, the Mate no-go zone (from Mate's marker), e-stop.
- **Calibration:** head-marker grid → pixel-to-gantry mapping, served in `get_table()`.

## Frame server (running now)

[`server.py`](server.py) + [`grbl.py`](grbl.py) + [`gripper.py`](gripper.py) + [`camera.py`](camera.py) + [`static/index.html`](static/index.html): GRBL, the gripper and the overhead camera over HTTP, and a jog page. The first piece of the hub.

- **One serial connection, kept open.** Opening the port resets the Uno, so the server owns it. Lines go one at a time and wait for `ok`/`error`; real-time bytes (status, hold, resume, reset, jog cancel) skip the queue. Status is polled 5× a second and pushed to every page over a WebSocket.
- **Jog page** at `http://raspberrypi.local:8000/`, after the Robo Diner jog page (click the XY table and the Z rail to set a target, then go), plus:
  - Live work and machine position, state and homed badges, a STOP button (feed hold, then reset).
  - Jog pad with diagonals and Z: tap for one step (0.1–100 mm), hold to keep moving until release (GRBL `$J` + jog cancel). Arrow keys and PgUp/PgDn do the same; 1–5 pick the step; Esc stops.
  - Zero buttons (`G10 L20 P1`), Home, Unlock, Pause/Resume/Reset, and a console with the GRBL command list and history.
  - Gripper: Pump and Valve switches, Grip and Drop (keys G and D).
  - If the last page closes mid-jog, the server cancels the jog.
- **Gripper commands go through GRBL's queue,** so they run after any motion already sent. GRBL doesn't report the valve pin at `S0`, so the hub tracks pump and valve itself; the valve closes itself after 10 s (the coil heats up), and after an unlock or home in case a reset left it open.
- **Camera:** picamera2 opens the Camera v2 once at startup and keeps it streaming (1640×1232, the full field of view), so a capture is the next frame, about 0.04 s.

| Endpoint | |
|---|---|
| `GET /api/status` | State, `MPos`, `WPos`, `homed` |
| `GET /api/settings` | GRBL `$$` values |
| `POST /api/send {line}` | Any G-code or `$` command; returns GRBL's reply |
| `POST /api/jog {x,y,z,feed}` | Relative jog (`$J=G91 …`) |
| `POST /api/move {x,y,z,feed?}` | Absolute move in work coordinates; no feed = rapid |
| `POST /api/home` | `$H` |
| `POST /api/realtime/{status,hold,resume,reset,jog_cancel}` | Sent immediately |
| `GET /api/gripper` | `{pump, valve}` |
| `POST /api/gripper/{pump_on,pump_off,valve_on,valve_off,grip,drop,stop}` | Runs after queued motion; returns `{pump, valve}`, plus `error` if GRBL refused (e.g. `error:9` in Alarm) |
| `GET /api/capture` | A fresh JPEG from the overhead camera; 503 if there's no camera |
| `WS /ws` | `status`, `settings`, `gripper` and `log` events |

**Run it on the Pi:**

```bash
rsync -a --exclude .venv --exclude __pycache__ software/hub/ ash@raspberrypi.local:hub/
ssh ash@raspberrypi.local
cd ~/hub && python3 -m venv --system-site-packages .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000
```

Set `GRBL_PORT` if the Uno isn't `/dev/ttyACM0`. Nothing else may hold the port, or the camera, while the server runs. `--system-site-packages` lets the venv import picamera2, which comes with Raspberry Pi OS.

**On the Pi it runs as a service** ([`hub.service`](hub.service)) and starts on boot:

```bash
sudo cp ~/hub/hub.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now hub
sudo systemctl restart hub     # after copying new code
journalctl -u hub -f           # logs
```

Stop it (`sudo systemctl stop hub`) before running anything else that opens the serial port, such as a test script.

## Config

A table config file (no game knowledge): size, reach, named spots, named actuators, camera settings, calibration.
