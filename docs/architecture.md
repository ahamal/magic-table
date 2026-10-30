# Architecture

## Principles

1. **The body is game-agnostic.** Nothing below the agent knows what game is being played. No "card", "deck", "flipper" or "peek" in the body — only cameras, positions, raw actuators, sensors, and named spots/actuators with no meaning attached.
2. **Ghost and real have identical I/O.** Same calls, same response shapes, same image format. The agent can't tell which one it's driving.
3. **No abstraction in the body.** Raw stepper steps, raw servo angles, raw sensor readings. Turning "go forward 10 cm" into steps is calibration, and calibration is the agent's job.
4. **Everything clever lives in the agent.** Image understanding (labeler), rules, strategy, memory, body model, macros (deal = many picks), self-checking, token budget.
5. **The agent can be an AI or a human.** Same API. Humans use a web page; the AI uses MCP tools that wrap the same endpoints.
6. **Safety is the exception to "no abstraction".** Limits, the Mate no-go zone, the edge reflex and stop live in the body, below the agent, and can't be bypassed.

## Layers

```
  Human (browser)            AI agent (Muse Spark, via MCP)
        │                              │
        └──────── HTTP / WebSocket ────┘
                        │
┌───────────────────────▼──────────── Pi 5: table hub ─────────────┐
│  Body API (one web server for the whole table)                   │
│  Safety layer: soft limits, Z only lowers when clear,            │
│                Mate no-go zone, e-stop                           │
│  ├─ Frame driver ── USB serial ──► Uno + CNC Shield (GRBL)       │
│  ├─ Overhead camera (Camera v2)                                  │
│  ├─ VL6180X on the gantry head (I2C)                             │
│  ├─ Gripper ── USB serial ──► Nano ──► 12V pump + vent valve     │
│  └─ Mate client ── HTTP ──┐                                      │
└───────────────────────────┼──────────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────── ESP32: Mate ────────┐
│  Mate API (own web server, Wi-Fi) + human control page           │
│  ├─ Camera (OV2640, on the S3 board)                             │
│  ├─ 2× 28BYJ-48 via ULN2003 (raw steps, own core)                │
│  └─ I2C: OLED face, PCA9685 servos (pan, tilt, flipper),         │
│          VL6180X edge sensor (reflex)                            │
└──────────────────────────────────────────────────────────────────┘
```

**Rules:**
- **Only the hub calls Mate** once the table is assembled. Agents never talk to Mate directly, so the hub can keep the gantry and Mate apart. (In step 1, Mate runs alone and its own page calls it directly.)
- **The brain uses the web API even when it runs on the Pi 5** (via `localhost`). Muse Spark and SAM 3.1 run in Meta's cloud; the Pi only makes API calls.

## Body interface (table)

All positions in **gantry millimetres**. Images are JPEG.

| Call | Returns |
|---|---|
| `get_table()` | Spec sheet: size, reachable area, cameras, sensors, named spots, named actuators, Mate present, calibration (pixel → gantry mm) |
| `capture(cam)` | Image from `overhead` or `mate` |
| `move_to(x, y, z?)` | `ok` or error (`UNREACHABLE`, `BLOCKED`) |
| `pick()` / `release()` | `holding: true/false` |
| `sense_z()` | Distance from the head down to the surface below (mm) |
| `probe(max_depth)` | Lower until the touch switch triggers; exact contact height |
| `actuate(name, value?)` | Trigger a named powered mechanism (only if powered extras exist) |
| `mate.*` | Passed through to Mate's API (see `software/mate/README.md`) |
| `say(text)` | Speech |
| `wait_for(event, timeout)` | `speech`, `table_changed`, `button` |

Every action returns the same shape: `{ ok, error?, took_ms, ... }`. Errors are normal, not fatal.

## Mate interface

Mate is its own system with its own API. Raw by design: `step {s1, s2}`, `servo {id, angle}`, `screen`, `capture`, `stop`. Full spec: [`software/mate/README.md`](../software/mate/README.md).

## Ghost (simulation)

- Driven by a **scene file** (data, not code): generic shapes (box, dome, cylinder) with front and back images, stacks, actuator types (e.g. `invert`).
- **Physics-lite:** stacking, the cup picks the top object only if it lands on it, actuators act on whatever is in their area.
- **Renders camera-like images:** same resolution and viewpoint as the overhead camera, ArUco markers, real textures (photos of the actual pieces), only backs of face-down objects.
- **Simulates sensors:** `sense_z` = top surface height + ~1 mm noise; `probe` = exact height.
- Optional realistic delays and failure rates.

## Agent

- **Labeler:** SAM 3.1 + ArUco → objects with gantry coordinates. Agent-side; used only when needed.
- **Body model:** learned calibration (steps per mm, steps per degree, sign conventions, servo angles). Saved and reused; re-checked on drift.
- **Macros:** deal, peek (pick → hover over Mate → `capture("mate")`), flip.
- **Verification:** compare expected vs observed after actions (shadow checking).
- **Token budget:** model calls only on commands or end of turn, never per frame.
- **Engines (optional):** KataGo, Stockfish for deep games.

## Calibration and markers

- **Camera → gantry:** ArUco marker on the gantry head, move to a grid of positions, fit the mapping. Stored in `get_table()`. Removable afterwards.
- **Safety net:** small markers on top of the frame corners — visible to the camera, not to seated players.
- **Mate:** marker on its roof, designed as part of its look (needed for position, heading and safety).
- Markers should blend in — see `docs/decisions.md`.

## Network

- Mate's ESP32 is 2.4 GHz only. Use WPA2 (or mixed). A phone hotspot on 2.4 GHz is easiest for demos.
- Hostnames: `mate.local` (ESP32, mDNS). Pi 5: `raspberrypi.local`.
