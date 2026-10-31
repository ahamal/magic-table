# Mate (software)

Mate is a self-contained system: one ESP32-S3 program serves its own API over Wi-Fi, its own control page and its own camera. It works with nothing else running. Later, the table hub on the Pi 5 becomes one more client of this API.

```
software/mate/
├── faces/      ready-made screen animations (eyes, chicken) and the script that draws them
├── firmware/   ESP32-S3: Wi-Fi API, raw steppers, flipper servo, face, camera, control page
├── server/     (retired — was the Pi 3 web server; the ESP32 serves the API now)
├── tests/      bring-up test from the classic ESP32 DevKit
└── ui/         notes on the control page (the page itself is built into the firmware)
```

## Design rules

- **Raw, no abstraction.** Steps, not millimetres. Angles, not "look left". Which way is forward, how many steps make a quarter turn — that's for the agent (human or AI) to work out. The robot learns its own body.
- **Both wheels in one command.** `step {s1, s2}` moves both steppers at once and they finish together, so Mate can drive straight or curve.
- **Physics and safety stay in the body:** acceleration ramps, max speed, max steps per command, coils off when idle, and stop.
- **Mate does not track its own position.** Feedback comes from outside — the overhead camera later, the human's eyes in step 1.
- **No edge sensor.** Keeping Mate on the table is the hub's job (no-go zone from the overhead camera), plus the per-command step limit.

## API

Everything Mate can do goes through this HTTP API. The control page uses it, and so will the hub and the AI brain. Every reply below was captured from the robot.

### Conventions

- **Base URL:** `http://mate.local` (port 80). Use the IP from `/info` if mDNS is slow. The live video is on port 81.
- **Parameters** go in the query string, e.g. `POST /step?s1=400&s2=-400`. POST requests have no body, except `/screen`.
- **Numbers are whole numbers.** A value that isn't a number is read as `0`, not rejected, so check what you send.
- **Replies** are JSON, except `/capture` (JPEG), `/stream` (MJPEG) and `/` (HTML).
- **Errors** are an HTTP status code plus `{"error": "<message>"}`:

  | Status | `error` | When |
  |---|---|---|
  | 400 | `need s1 and s2` | `/step` without both wheels |
  | 400 | `limit` | `/step` steps, speed or accel out of range |
  | 400 | `range` | `/servo` angle missing or outside 0–180 |
  | 400 | `speed 0–600` | `/servo` speed out of range |
  | 400 | `body must be 0–64 frames of 1024 bytes` | `/screen` body the wrong size |
  | 400 | `X-FPS 1–30` | `/screen` frame rate out of range |
  | 400 | `X-Repeat 0–1000` | `/screen` repeat count out of range |
  | 409 | `busy` | `/step` while a move is still running |
  | 500 | `capture failed` | the camera gave no frame; try again |
  | 503 | `no camera` | `/capture` or `/camera` with no camera found |
  | 404 | *(plain text `Not found: /path`)* | unknown path, or the wrong method (e.g. `GET /step`) |

### Endpoints at a glance

| Method | Path | What it does |
|---|---|---|
| GET | `/info` | What Mate is: limits, screen size, camera, stream URL |
| GET | `/status` | What Mate is doing: moving or not, last move, servo, screen, health |
| POST | `/step` | Move both wheels (starts the move and returns at once) |
| POST | `/stop` | Stop the wheels now |
| POST | `/servo` | Set the flipper angle |
| POST | `/screen` | Show a picture or a looping animation on the face |
| GET | `/capture` | Take a photo (JPEG) |
| POST | `/camera` | Read or set the image flip |
| GET | `:81/stream` | Live video (MJPEG), for people watching |
| GET | `/scan` | List I2C devices (debugging) |
| GET | `/` | The control page, for people |

### `GET /info`

Static facts about the robot. Read it once at start-up.

```json
{"fw":"mate-s3","ip":"192.168.1.201","max_steps":4096,"max_speed":800,"max_accel":1000,"max_servo_speed":600,"servo_park":20,"oled":true,
 "screen":{"width":128,"height":64,"frame_bytes":1024,"max_frames":64,"max_fps":30,"max_repeat":1000},
 "camera":"GC0308","stream":"http://192.168.1.201:81/stream","vflip":1,"hmirror":1}
```

| Field | Meaning |
|---|---|
| `max_steps` | Most half-steps per wheel in one `/step` (4096 = one wheel turn) |
| `max_speed` | Highest `speed` for `/step`, half-steps/s |
| `max_accel` | Highest `accel` for `/step`, half-steps/s² |
| `max_servo_speed` | Highest `speed` for `/servo`, degrees/s |
| `servo_park` | The flipper's resting angle, where it goes at every boot |
| `oled` | `true` if the face screen was found |
| `screen` | Face size and `/screen` limits |
| `camera` | Sensor name, or `none` |
| `stream`, `vflip`, `hmirror` | Only present when there is a camera |

### `GET /status`

The live state. Poll it after `/step` (every 100–200 ms) to know when a move ends.

```json
{"busy":false,"p1":0,"p2":0,"last":{"result":"none","d1":0,"d2":0,"ms":0},"servo":-1,"servo_now":-1,"servo_moving":false,
 "screen":{"frames":56,"fps":12,"repeat":0,"done":false},"uptime_ms":12666,"reset_reason":"power_on","boots":1,"rssi":-38}
```

| Field | Meaning |
|---|---|
| `busy` | `true` while a wheel move is running |
| `p1`, `p2` | Step counters for wheel 1 and 2 since boot (not a position on the table) |
| `last.result` | The last move: `ok` (finished), `stopped` (cut short by `/stop`), or `none` (no move since boot) |
| `last.d1`, `last.d2` | Half-steps each wheel actually moved in that move |
| `last.ms` | How long it took |
| `servo` | Flipper target angle (the last one sent), or `-1` if never set since boot |
| `servo_now` | Where the flipper is being driven right now; differs from `servo` during a timed sweep |
| `servo_moving` | `true` while a timed sweep (`/servo` with `speed`) is still on its way |
| `screen.frames`, `screen.fps`, `screen.repeat` | What the face is showing: `0` frames = the status screen; `repeat` as sent (`0` = forever) |
| `screen.done` | `true` once an animation has played its `X-Repeat` times and is holding its last frame. Always `true` for a still picture or the status screen; never for a forever loop |
| `uptime_ms` | Time since the last restart |
| `reset_reason` | Why it last restarted: `power_on`, `brownout`, `crash`, `watchdog`, `software`, `usb`, `other` |
| `boots` | Restarts since power was connected. If this goes up, Mate restarted: check `reset_reason` |
| `rssi` | Wi-Fi signal in dBm (−30 great, −70 weak) |

### `POST /step?s1=&s2=[&speed=][&accel=]`

Moves both wheels at once. Both wheels start and finish together, so different values make Mate curve.

| Param | Required | Range | Default | Meaning |
|---|---|---|---|---|
| `s1` | yes | −4096…4096 | — | Half-steps for wheel 1 (4096 = one wheel turn) |
| `s2` | yes | −4096…4096 | — | Half-steps for wheel 2 |
| `speed` | no | 1…800 | 500 | Top speed in half-steps/s, for the wheel going further; the other wheel is scaled to finish at the same time |
| `accel` | no | 1…1000 | 400 | Ramp up and down, half-steps/s² |

- **Returns at once:** `{"ok":true}`. The move runs on its own; poll `/status` until `busy` is `false`, then read `last`.
- **One move at a time:** a second `/step` while moving gets `409 busy`. Send `/stop` first to change course.
- `s1=0&s2=0` finishes immediately with `ok`.
- The motor coils switch off after every move, so the wheels can be turned by hand while idle.

```bash
curl -X POST "http://mate.local/step?s1=-1024&s2=1024&speed=600&accel=800"   # → {"ok":true}
```

### `POST /stop`

Stops the wheels immediately and switches the coils off. Works at any time, even mid-move or when idle. Returns `{"ok":true}`; the interrupted move shows `last.result = "stopped"` with how far each wheel actually got.

### `POST /servo?angle=[&speed=]`

Moves the flipper (MG996R).

| Param | Required | Range | Default | Meaning |
|---|---|---|---|---|
| `angle` | yes | 0…180 | — | Target angle in degrees |
| `speed` | no | 0…600 | 0 | Sweep speed in degrees/s. `0` or left out = jump: the servo goes there as fast as it can (~0.2 s per 60°) |

- **Returns at once:** `{"ok":true}`. With a `speed`, Mate sweeps the flipper there in small steps on its own; `/status` shows `servo_moving: true` until it arrives (e.g. 30° at `speed=30` takes ~1 s).
- **A new `/servo` replaces the current one**, even mid-sweep: it continues from where the flipper is now.
- **Resting pose and memory:** at every boot the flipper starts at its last saved angle (so it doesn't jump), then sweeps to its resting angle, **20°** (`servo_park`), at 40°/s. Mate saves the angle to flash once the flipper has been still for 2 s with the wheels stopped. If nothing was saved yet, or the arm was turned by hand while off, the first move at boot is a jump to 20°.
- It then holds that angle. There is no feedback of the real position, only where Mate is driving it.

```bash
curl -X POST "http://mate.local/servo?angle=120&speed=60"   # sweep to 120° at 60°/s → {"ok":true}
```

 **Avoid the very ends** (0 and 180) if the flipper hits something there: holding against a stop draws ~2.5 A.

### `POST /screen`

Shows a picture or a looping animation on the face (the OLED).

- **Body:** 0–64 frames back to back, each **1024 bytes**: 128×64 pixels, 1 bit per pixel, rows top to bottom, 16 bytes per row, most significant bit = leftmost pixel, `1` = lit.
- **Headers:** `Content-Type: application/octet-stream`, plus optional:
  - `X-FPS: 1–30` (default 10): playback speed.
  - `X-Repeat: 0–1000` (default 0): how many times to play the animation. `0` loops forever; `1` plays once; then it **stays on the last frame**.

  These are headers, not `?fps=`, because Mate's web server ignores query args on requests with a binary body.
- **Returns** `{"frames":N,"fps":F,"repeat":R}`.
- **1 frame** = a still picture. **2–64 frames** = Mate plays them by itself at `X-FPS`, `X-Repeat` times, until replaced. **Empty body** = back to the status screen.
- **Knowing when it's finished:** `/status` → `screen.done` turns `true` when a counted animation ends. Play-once reactions (a blink, a surprised face) then hold their last frame until you send the next thing.
- **The status screen** is what Mate shows by itself: at boot, whenever nothing has been sent ("Mate", `mate.local`, its IP and camera), and whenever Wi-Fi is down ("not connected" and the network name).
- Not kept across restarts. If Wi-Fi drops, the status screen ("not connected") shows until it's back, then the animation resumes.

```bash
# loop forever
curl -X POST -H 'Content-Type: application/octet-stream' -H 'X-FPS: 12' \
  --data-binary @software/mate/faces/eyes.bin http://mate.local/screen   # → {"frames":56,"fps":12,"repeat":0}
# play once, then hold the last frame
curl -X POST -H 'Content-Type: application/octet-stream' -H 'X-FPS: 4' -H 'X-Repeat: 1' \
  --data-binary @software/mate/faces/chicken.bin http://mate.local/screen # → {"frames":4,"fps":4,"repeat":1}
```

Ready-made faces (eyes, chicken, a portrait) are in [`faces/`](faces/); `faces/make.py` shows how to draw frames with Pillow (`Image.new("1", (128, 64)).tobytes()` is already in Mate's format).

### `GET /capture`

Returns a fresh photo: `image/jpeg`, 640×480, about 25–35 KB, in about 1 s. Each call wakes the camera, throws away the stale frame, takes a new one, and puts the camera back to sleep (a running camera slows Mate's Wi-Fi). The image is already turned the right way up.

### `POST /camera[?vflip=0|1][&hmirror=0|1]`

Reads or sets the image flip. With no params it just returns the current setting: `{"vflip":1,"hmirror":1}`. Both start at `1` (a 180° turn, because the camera is mounted upside down) after every restart.

### `GET :81/stream`

Live MJPEG video (`http://mate.local:81/stream`), about 2 fps, for people to watch in a browser. The camera stays on while anyone watches, which slows Wi-Fi, so the AI should use `/capture` instead.

### `GET /scan`

The I2C addresses that answer, e.g. `{"i2c":["0x3c"]}` (`0x3c` is the face screen). For debugging wiring.

### Driving: what's known about the body

Calibration is the agent's job, but these were checked on the bench (Oct 31):

| Command | What Mate does |
|---|---|
| `s1` −, `s2` + (e.g. `-1024, 1024`) | Drives **forward** |
| `s1` +, `s2` − | Drives backward |
| `s1` +, `s2` + | Turns **left** (anticlockwise, seen from above) |
| `s1` −, `s2` − | Turns right |

- One wheel turn is 4096 half-steps. The wheels are 70 mm across, so one turn rolls about **220 mm** (≈ 0.054 mm per half-step) if nothing slips. Not yet measured on the table.
- Top speed: 800 half-steps/s ≈ **4.3 cm/s**.
- Mate doesn't know where it is. Use the overhead camera (later) or `/capture` to see where it went.
- **No edge sensor:** nothing on Mate stops it at the table edge. The 4096-step limit per move (~22 cm) is the only guard.

### A typical agent loop

1. `GET /info` once.
2. `POST /step?...` → `{"ok":true}`.
3. Poll `GET /status` every ~150 ms until `busy` is `false`. Read `last.result` and `last.d1`/`last.d2`.
4. `GET /capture` to see the result.
5. Check `boots` now and then: if it went up, Mate restarted, the face screen is reset, and the step counters are back at 0.

### Getting pictures: notes

- The bundled GC0308 camera has no JPEG encoder, so the ESP32 encodes each frame in software (~370 ms). An OV2640 on the same connector would make snapshots several times faster; the firmware switches to hardware JPEG automatically.
- The stream runs on its own server (port 81), so the API on port 80 stays responsive while someone watches.

### Control page

`http://mate.local/` is for people: camera (snapshot, live, download), a screen editor (draw with clicks, type text, send), a **Faces** grid of 19 ready-made animations with a loop/once switch, an arrow pad with keyboard arrows (Space or Esc stops), speed and accel sliders, raw `s1`/`s2`, STOP, and a flipper slider with a speed slider (full = jump). It uses only the API above.

## Step 1 checklist

- [x] Firmware on the ESP32-S3: API, both steppers, flipper servo (direct PWM, timed sweeps, 20° resting pose), OLED bitmaps + animations, camera snapshot + stream
- [x] OLED on the S3
- [x] Wheels and the flipper servo wired to the S3 and driven over Wi-Fi, on USB and on the power bank
- [x] Control page: camera, screen editor, 19 faces, arrow-pad driving, speed/accel and servo sliders
- [x] API reference for the AI brain (above)
- [x] Sign conventions: forward = s1 −, s2 +; left turn = +, + (see [Driving](#driving-whats-known-about-the-body))
- [ ] Calibration on the table: half-steps per mm, per degree of turn
- [ ] Card-corner test at 10–15 cm with the GC0308
- [ ] Mount the flipper arm and check the 20° resting pose
