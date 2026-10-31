# Mate control page

The human agent's interface to Mate. Built into the firmware ([`../firmware/firmware.ino`](../firmware/firmware.ino), `PAGE`) and served at `http://mate.local/`; uses only the public API, exactly what an AI would use.

## Controls

- **Wheels:** two raw inputs (s1, s2 half-steps) plus speed and accel, and a few quick buttons (e.g. `+400/+400`, `+400/−400`) — the human works out what they do.
- **Flipper servo:** a slider (raw angle).
- **Screen:** a 128×64 preview to draw on with clicks, plus a text box whose text renders into the preview; sent to Mate as a bitmap as you go. Later: ready-made faces.
- **Camera:** snapshot (`/capture`), live video (`:81/stream`) and download.
- **Status:** busy, step counters, last move result, request latency.
- **STOP:** large, always visible.
- **Notes:** a place to record calibration findings (steps per mm, per degree, signs).

## Stack

Plain HTML + JavaScript, no build step. The live view is for watching and debugging — the agent's interface is `capture`.
