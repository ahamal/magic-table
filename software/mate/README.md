# Mate (software)

Mate is a self-contained system: one ESP32-S3 program serves its own API over Wi-Fi, its own control page and its own camera. It works with nothing else running. Later, the table hub on the Pi 5 becomes one more client of this API.

```
software/mate/
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

Base URL: `http://mate.local` (mDNS from the ESP32, port 80). Parameters go in the query string; replies are JSON unless noted.

| Method | Path | Params | Returns |
|---|---|---|---|
| GET | `/` | — | Control page: camera, screen editor, arrow pad + arrow keys, speed/accel, raw steps, STOP, flipper slider |
| GET | `/info` | — | Firmware, IP, limits, `oled` found, screen size and limits, `camera` sensor name, `stream` URL, flip settings |
| GET | `/status` | — | `busy`, step counters `p1`/`p2`, last move `{result, d1, d2, ms}`, flipper `servo` angle, `screen` frames and fps, uptime, RSSI |
| POST | `/step` | `s1, s2, speed?, accel?` (half-steps) | `{ok}` at once; poll `/status` until `busy` is false for the result |
| POST | `/stop` | — | Stops immediately, releases coils. Always works, even mid-move. |
| POST | `/servo` | `angle` (0–180) | `{ok}` — the flipper |
| POST | `/screen` | Body: N × 1024 bytes; header `X-FPS` (1–30, default 10) | `{frames, fps}` — a picture or a looping animation on the OLED; empty body = status screen |
| GET | `/capture` | — | **JPEG**, 640×480, a fresh frame. About 0.9 s |
| POST | `/camera` | `vflip?`, `hmirror?` (0/1) | Flip the image. Both start on (180°), because the camera is mounted upside down |
| GET | `:81/stream` | — | **MJPEG** live video, about 2 fps. Open in a browser or `<img>`; for watching and debugging |
| GET | `/scan` | — | I2C addresses on the bus |

Speech is not on Mate: the hub speaks for it.

### Getting pictures

- **Snapshot (what the agent uses):** `curl -o mate.jpg http://mate.local/capture`. Each call wakes the camera, drops the stale frame, takes a new one, encodes it and puts the camera back to sleep.
- **Live video:** `http://mate.local:81/stream` in a browser, or the **Live** button on the control page. It runs on its own server, so the API on port 80 stays responsive while someone watches. Close it when done — while it runs the camera is on and Wi-Fi is slower.
- **Speed limits:** the bundled GC0308 has no JPEG encoder, so the ESP32 encodes each frame in software (~370 ms). An OV2640 on the same connector would make snapshots and video several times faster; the firmware picks hardware JPEG automatically when the sensor has it.

### Results

`/status` → `last.result`:

- `ok` — finished normally.
- `stopped` — `/stop` interrupted the move.

Errors use HTTP status codes with `{error}`: `400 limit` for steps or speed above the maximum, `409 busy`, `503 no camera`.

### Limits (in the firmware)

| Limit | Value | Why |
|---|---|---|
| Max steps per command | 4096 half-steps (one wheel turn, ~22 cm) | A typo can't drive Mate off the table |
| Max speed | 800 half-steps/s | 28BYJ-48 skips steps above this |
| Max acceleration | 1000 half-steps/s² | Same |

### Screen

`/screen` takes raw 128×64 pictures, so the AI (or a person) can show any face, text or drawing.

- **Format:** 1 bit per pixel, rows top to bottom, 16 bytes per row, the most significant bit is the leftmost pixel; 1 = lit. One frame is 1024 bytes. Send it as `Content-Type: application/octet-stream`.
- **Animations are preloaded:** send up to 64 frames back to back in one request with `X-FPS`, and Mate loops them by itself. Smooth, and nothing more goes over Wi-Fi. A new `/screen` replaces it. Streaming frames one request at a time also works (~50 ms per frame) but stutters whenever Wi-Fi does.
- **Status screen:** shown at boot, whenever Wi-Fi is down ("not connected"), and when nothing has been sent (name, `mate.local`, IP). An empty `/screen` goes back to it.
- **Control page:** click or drag on the screen preview to draw, Erase to remove, and type in the text box to render text (auto-sized, wrapped) under the drawing. It sends as you go, or with Send.

```bash
# one frame
curl -X POST -H 'Content-Type: application/octet-stream' --data-binary @face.bin http://mate.local/screen
# a 4-frame animation at 8 fps
cat f1.bin f2.bin f3.bin f4.bin | curl -X POST -H 'Content-Type: application/octet-stream' -H 'X-FPS: 8' --data-binary @- http://mate.local/screen
```

## Step 1 checklist

- [x] Firmware on the ESP32-S3: API, both steppers, flipper servo (direct PWM), OLED bitmaps + animations, camera snapshot + stream
- [x] OLED on the S3
- [ ] Wheels and the flipper servo tested wired to the S3
- [ ] UI: ready-made faces, calibration notes
- [ ] Card-corner test at 10–15 cm with the GC0308
- [ ] Human-calibrated notes: steps per mm, steps per degree, sign conventions (record in this file)
