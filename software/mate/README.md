# Mate (software)

Mate is a self-contained system: one ESP32 program serves its own API over Wi-Fi, its own control page and its own safety rules. It works with nothing else running. Later, the table hub on the Pi 5 becomes one more client of this API.

```
software/mate/
├── firmware/   ESP32: Wi-Fi API, raw steppers, servos, face, camera, edge reflex
├── server/     (retired — was the Pi 3 web server; the ESP32 serves the API now)
└── ui/         human control page, served by the ESP32                → uses the API
```

## Design rules

- **Raw, no abstraction.** Steps, not millimetres. Angles, not "look left". Which way is forward, how many steps make a quarter turn — that's for the agent (human or AI) to work out. The robot learns its own body.
- **Both wheels in one command.** `step {s1, s2}` moves both steppers at once and they finish together, so Mate can drive straight or curve.
- **Physics and safety stay in the body:** acceleration ramps, max speed, max steps per command, coils off when idle, the edge reflex, and stop.
- **Mate does not track its own position.** Feedback comes from outside — the overhead camera later, the human's eyes in step 1.
- **One firmware, two boards.** Pins live in a per-board config (DevKit now, ESP32-S3 CAM later); the rest of the code is shared.

## API

Base URL: `http://mate.local:<port>` (mDNS from the ESP32; port TBD). JSON in and out unless noted.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/info` | — | Spec sheet: limits (max steps, max speed/accel), servo ids and angle ranges, camera resolution, screen size (128×64), sensors present |
| GET | `/status` | — | `busy`, step counters, servo angles, `edge_mm`, power warnings (brownout resets) |
| POST | `/step` | `{s1, s2, speed?, accel?}` | `{result: "ok" \| "edge" \| "stopped", done: {s1, s2}, took_ms}` — waits until finished |
| POST | `/servo` | `{id, angle}` | `{result: "ok"}` |
| POST | `/screen` | A raw 128×64 1-bit image | `{result: "ok"}` |
| GET | `/capture` | — | JPEG from Mate's camera (`503 NO_CAMERA` on the DevKit) |
| POST | `/stop` | — | Stops immediately, releases coils. Always works, even mid-move. |
| GET | `/range` | — | `{cm}` from the TF-Luna — later |

Speech is not on Mate: the hub speaks for it.

### Results

- `ok` — finished normally.
- `edge` — the edge reflex fired: the firmware stopped, backed off a little, and reports how far each wheel actually moved. Information for the agent: the table ends there.
- `stopped` — `/stop` interrupted the move.
- Errors use HTTP status codes with `{error, detail}`, e.g. `400 LIMIT` for steps or speed above the maximum, `409 BUSY`, `503 NO_CAMERA`.

### Limits (defaults, in the firmware)

| Limit | Default | Why |
|---|---|---|
| Max steps per command | 4096 half-steps (≈ one wheel turn) | A typo can't drive Mate off the table |
| Max speed | 800 half-steps/s | 28BYJ-48 skips steps above this |
| Max acceleration | 1000 half-steps/s² | Same |

### Screen

`/screen` takes a raw 128×64 image, so the AI (or a person) can design any expression. The control page ships ready-made faces (`neutral`, `blink`, `thinking`, `happy`, `surprised`) that it sends as images.

## Open decisions

- **Port** for the API.

## Step 1 checklist

- [ ] Firmware on the ESP32: API, both steppers, servos, OLED, edge sensor
- [ ] UI: drive, servos, screen, capture, stop
- [ ] Camera on the S3 board: `/capture`, card-corner test at 10–15 cm
- [ ] Human-calibrated notes: steps per mm, steps per degree, sign conventions (record in this file)
