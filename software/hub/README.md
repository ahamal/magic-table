# Table hub (Pi 5)

The body API for the whole table. Step 2.

## Responsibilities

- **One web server** (FastAPI): the table body API (see [`docs/architecture.md`](../../docs/architecture.md#body-interface-table)) plus the human table page. WebSocket for events (`wait_for`) and the optional live view.
- **Frame driver:** GRBL over USB serial — homing, soft limits, `move_to`, probe (`G38.2`).
- **Gripper:** GRBL switches the 12V pump (`M8`/`M9`) and vent valve (`M4 S0`/`M3 S0`) through MOSFETs on the CNC Shield. The Pi never touches the 12V side.
- **Sensors:** VL6180X (`sense_z`), touch switch (`probe`).
- **Cameras:** the Pi 5's two CSI cameras (`capture`, `stream`); later named views like `capture("overhead")`.
- **Mate client:** the only caller of Mate's API once the table is assembled; `capture("mate")` and `mate.*` pass through.
- **Safety layer:** soft limits, Z only lowers when clear, the Mate no-go zone (from Mate's marker), e-stop.
- **Calibration:** head-marker grid → pixel-to-gantry mapping, served in `get_table()`.

## Frame server (running now)

[`server.py`](server.py) + [`grbl.py`](grbl.py) + [`gripper.py`](gripper.py) + [`camera.py`](camera.py) + [`static/index.html`](static/index.html): GRBL, the gripper and the cameras over HTTP, and a jog page. The first piece of the hub.

- **One serial connection, kept open.** Opening the port resets the Uno, so the server owns it. Lines go one at a time and wait for `ok`/`error`; real-time bytes (status, hold, resume, reset, jog cancel) skip the queue. Status is polled 5× a second and pushed to every page over a WebSocket.
- **Jog page** at `http://raspberrypi.local:8000/`, after the Robo Diner jog page (click the XY table and the Z rail to set a target, then go), plus:
  - Live work and machine position, state and homed badges, a STOP button (feed hold, then reset).
  - Jog pad with diagonals and Z: tap for one step (0.1–100 mm), hold to keep moving until release (GRBL `$J` + jog cancel). Arrow keys and PgUp/PgDn do the same; 1–5 pick the step; Esc stops.
  - Zero buttons (`G10 L20 P1`), Home, Unlock, Pause/Resume/Reset, and a console with the GRBL command list and history.
  - Gripper: Pump and Valve switches, Grip and Drop (keys G and D).
  - Live views of every camera under the map, each with a link to a full-size photo. **Cameras** hides them; streams also pause while the tab is in the background.
  - If the last page closes mid-jog, the server cancels the jog.
- **Gripper commands go through GRBL's queue,** so they run after any motion already sent. GRBL doesn't report the valve pin at `S0`, so the hub tracks pump and valve itself; the valve closes itself after 10 s (the coil heats up), and after an unlock or home in case a reset left it open.
- **Cameras:** picamera2 opens every camera the Pi found at boot (now cam 0 = ov5647, cam 1 = imx219 / Camera v2) and keeps them streaming at 1640×1232, the full field of view, so a capture is the next frame, about 0.04 s. Cameras are only detected at boot: plug them in with the Pi off.

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
| `POST /api/transcribe` | Body: one utterance as a 16/24 kHz mono 16-bit WAV. Returns `{id, at, text, audio_ms, took_ms}`, or `{text: ""}` if nothing was said |
| `GET /api/transcripts?since=0` | Everything said on the talk page, oldest first |
| `DELETE /api/transcripts` | Clear them |
| `GET /api/cameras` | `[{cam, model, ok, error}]` |
| `GET /api/capture?cam=0` | A fresh full-size JPEG from one camera; 404 if there's no such camera |
| `GET /api/stream?cam=0&fps=10` | Live MJPEG view, 820 px wide (~7 fps, ~40 KB a frame); open it in a browser tab or an `<img>` |
| `WS /ws` | `status`, `settings`, `gripper`, `transcript`, `transcripts_cleared` and `log` events |

**Run it on the Pi:**

```bash
rsync -a --exclude .venv --exclude __pycache__ --exclude certs --exclude .env --exclude transcripts.jsonl \
  software/hub/ ash@raspberrypi.local:hub/
ssh ash@raspberrypi.local
cd ~/hub && python3 -m venv --system-site-packages .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python serve.py      # HTTP :8000 and HTTPS :8443
```

**First time only, on the Pi:**

```bash
# Meta Model API key, for speech-to-text. Private to the Pi; never commit it.
umask 077; echo "MODEL_API_KEY=<your key>" > ~/hub/.env
# self-signed certificate for :8443 (phones only allow the mic on HTTPS)
mkdir -p ~/hub/certs && cd ~/hub/certs && openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
  -keyout hub.key -out hub.crt -subj "/CN=raspberrypi.local" \
  -addext "subjectAltName=DNS:raspberrypi.local,IP:192.168.1.99"
```

Set `GRBL_PORT` if the Uno isn't `/dev/ttyACM0`. Nothing else may hold the port, or the camera, while the server runs. `--system-site-packages` lets the venv import picamera2, which comes with Raspberry Pi OS.

**On the Pi it runs as a service** ([`hub.service`](hub.service)) and starts on boot:

```bash
sudo cp ~/hub/hub.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now hub
sudo systemctl restart hub     # after copying new code
journalctl -u hub -f           # logs
```

Stop it (`sudo systemctl stop hub`) before running anything else that opens the serial port, such as a test script.

## Vision and the 3D page

[`vision.py`](vision.py): where things are, from the cameras, with OpenCV only (no cloud AI). The gantry is the reference: calibration moves the head marker (ArUco ID 10) over a grid at three heights and fits each camera's 3D projection in gantry coordinates (X/Y mm, Z GRBL units, Z+ up). Twice a second it then finds the head (and checks it against GRBL, in mm), Mate (ID 20: position, heading, height), cards on the dark board (center, angle, face up/down) and the board markers (IDs 0–3; if they move in the picture the camera moved, and it's corrected). Marker sizes and offsets are constants at the top.

**Page:** `http://raspberrypi.local:8000/scene`, a live three.js view: board, head and cup, Mate, cards, cameras; buttons for Calibrate, Board is here, Re-anchor, Travel height = here.

**Order of use:**
1. Z at its **top** over the middle of the board, Mate not under the 120 mm square around it, GRBL unlocked.
2. **Calibrate** asks how far the cup is above the board (mm), then goes down from there in three passes, never closer than 15 mm. Any reset, pause, alarm or STOP aborts it with no further moves. The start height becomes the **travel height**.
3. Lower the cup until it just touches the board, press **Board is here** (board height from the gantry, not from marker size).
4. After any GRBL reset (or hub restart), unlock, then **Re-anchor**: Z goes back to the last saved value, X/Y from where the camera sees the head. Don't use Work zero on the jog page; it shifts every position.

**Mate rule:** below travel height, `/api/move` goes up to travel height before crossing Mate and refuses to end over it; `/api/jog` across Mate is refused. (`/api/send` is raw G-code and isn't checked.)

| Endpoint | |
|---|---|
| `POST /api/calibrate {room, span=60, steps=3, levels=3, feed=1500}` | `room` = mm between cup and board at the start (required) |
| `GET /api/calibration` | calibrated, per-camera fit, `table_z`, `travel_z`, `needs_reanchor`, head check |
| `POST /api/calibration/table` | the cup is touching the board now |
| `POST /api/calibration/travel` | the current Z is the travel height |
| `POST /api/calibration/reanchor` | after a reset |
| `GET /api/scene?fresh=false` | head, Mate, cards, board, cameras; also the `scene` WebSocket event |

## Talk page

`https://raspberrypi.local:8443/talk` (or `https://192.168.1.99:8443/talk` on phones that don't resolve `.local`): instructions by voice, from any phone or laptop on the Wi-Fi.

- **Tap the button, talk, tap again.** The page records, turns the audio into a 16 kHz mono WAV and posts it to the hub; the hub sends it to Meta's **Muse Voice Transcribe** (`api.meta.ai/v1/asr/transcribe`, push-to-talk mode, biased toward table words like "Mate", "raise", "flop") and shows the text. About 1–1.5 s for a sentence.
- **Every page sees every transcript** live, so several phones and the agent share one list. They're kept in `~/hub/transcripts.jsonl` (not in git) until cleared.
- **The certificate is self-signed:** each device shows a warning once; accept it ("visit this website" / "proceed"). The plain-HTTP page shows transcripts but can't use the mic, and links to the HTTPS one.
- The agent reads instructions with `GET /api/transcripts?since=<last id>` or the `transcript` WebSocket events.

## Config

A table config file (no game knowledge): size, reach, named spots, named actuators, camera settings, calibration.
