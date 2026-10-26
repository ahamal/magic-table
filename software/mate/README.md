# Mate (software)

Mate is a self-contained system: it runs on its own Pi 3 with its own API, its own control page and its own safety rules. It works with nothing else running. Later, the table hub on the Pi 5 becomes one more client of this API.

```
software/mate/
├── firmware/   Arduino: raw steppers, servos, edge reflex      → serial protocol
├── server/     Pi 3 web server: Mate API                       → HTTP
└── ui/         human control page, served by the server        → uses the API
```

## Design rules

- **Raw, no abstraction.** Steps, not millimetres. Angles, not "look left". Which way is forward, how many steps make a quarter turn — that's for the agent (human or AI) to work out. The robot learns its own body.
- **Both wheels in one command.** `step {s1, s2}` moves both steppers at once and they finish together, so Mate can drive straight or curve.
- **Physics and safety stay in the body:** acceleration ramps, max speed, max steps per command, coils off when idle, the edge reflex, and stop.
- **Mate does not track its own position.** Feedback comes from outside — the overhead camera later, the human's eyes in step 1.

## API

Base URL: `http://mate.local:<port>` (port TBD). JSON in and out unless noted.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/info` | — | Spec sheet: limits (max steps, max speed/accel), servo ids and angle ranges, camera resolution, screen size, sensors present |
| GET | `/status` | — | `busy`, step counters, servo angles, `edge_mm`, power warnings (`vcgencmd get_throttled`) |
| POST | `/step` | `{s1, s2, speed?, accel?}` | `{result: "ok" \| "edge" \| "stopped", done: {s1, s2}, took_ms}` — waits until finished |
| POST | `/servo` | `{id, angle}` | `{result: "ok"}` |
| POST | `/screen` | *TBD:* `{face}` or an image | `{result: "ok"}` |
| POST | `/say` | `{text}` | `{result: "ok"}` — if a speaker is fitted |
| GET | `/capture` | — | JPEG from Mate's camera |
| POST | `/stop` | — | Stops immediately, releases coils. Always works, even mid-move. |
| GET | `/range` | — | `{cm}` from the TF-Luna — later |

### Results

- `ok` — finished normally.
- `edge` — the edge reflex fired: the firmware stopped, backed off a little, and reports how far each wheel actually moved. Information for the agent: the table ends there.
- `stopped` — `/stop` interrupted the move.
- Errors use HTTP status codes with `{error, detail}`, e.g. `400 LIMIT` for steps or speed above the maximum, `409 BUSY`, `503 NO_ARDUINO`.

### Limits (defaults, in the firmware)

| Limit | Default | Why |
|---|---|---|
| Max steps per command | 4096 half-steps (≈ one wheel turn) | A typo can't drive Mate off the table |
| Max speed | 800 half-steps/s | 28BYJ-48 skips steps above this |
| Max acceleration | 1000 half-steps/s² | Same |

## Open decisions

- **Screen:** named faces (simple for step 1) or raw images (the AI draws its own expressions)?
- **Speaker:** now or later?
- **Port** for the server.

## Step 1 checklist

- [ ] Firmware: serial protocol working with both steppers, servos, edge sensor
- [ ] Server: all endpoints except `/range`
- [ ] UI: drive, servos, screen, capture, stop
- [ ] Human-calibrated notes: steps per mm, steps per degree, sign conventions (record in this file)
