# Mate (software)

Mate is a self-contained system: one ESP32-S3 program serves its own API over Wi-Fi, its own control page and its own camera. It works with nothing else running. Later, the table hub on the Pi 5 becomes one more client of this API.

```
software/mate/
├── firmware/   ESP32-S3: Wi-Fi API, raw steppers, servos, face, camera, control page
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
| GET | `/` | — | Control page: camera, wheels, STOP, OLED text, servo sliders |
| GET | `/info` | — | Firmware, IP, limits, servo count, `oled` found, `camera` sensor name, `stream` URL, flip settings |
| GET | `/status` | — | `busy`, step counters `p1`/`p2`, last move `{result, d1, d2, ms}`, servo angles, uptime, RSSI |
| POST | `/step` | `s1, s2, speed?, accel?` (half-steps) | `{ok}` at once; poll `/status` until `busy` is false for the result |
| POST | `/stop` | — | Stops immediately, releases coils. Always works, even mid-move. |
| POST | `/servo` | `id` (0 pan, 1 tilt, 2 flipper), `angle` (0–180) | `{ok}` |
| POST | `/screen` | `text` | `{ok}` — text on the OLED |
| GET | `/capture` | — | **JPEG**, 640×480, a fresh frame. About 0.9 s |
| POST | `/camera` | `vflip?`, `hmirror?` (0/1) | Flip the image to match how the camera is mounted |
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

`/screen` takes text for now. The plan is a raw 128×64 image, so the AI (or a person) can design any expression, with ready-made faces (`neutral`, `blink`, `thinking`, `happy`, `surprised`) on the control page.

## Step 1 checklist

- [x] Firmware on the ESP32-S3: API, both steppers, servos (direct PWM), OLED, camera snapshot + stream
- [ ] Wire the S3 into Mate (new pins) and test wheels, servos and OLED on it
- [ ] UI: image faces, calibration notes
- [ ] Card-corner test at 10–15 cm with the GC0308
- [ ] Human-calibrated notes: steps per mm, steps per degree, sign conventions (record in this file)
