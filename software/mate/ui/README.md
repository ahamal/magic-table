# Mate control page

The human agent's interface to Mate. Built into the firmware ([`../firmware/firmware.ino`](../firmware/firmware.ino), `PAGE`) and served at `http://mate.local/`; uses only the public API, exactly what an AI would use.

## Controls

- **Wheels:** speed and accel sliders, an arrow pad (↑ ↓ ← → plus a stop square) with a steps-per-press box, the arrow keys on the keyboard (Space or Esc stops), and raw s1/s2 inputs with Go. The wheels face opposite ways: same sign on both turns Mate (both + = anticlockwise), opposite signs drive it (s1 −, s2 + = forward). The pad's mapping is `DIRS` in the page script.
- **Flipper servo:** a slider (raw angle).
- **Screen:** a 128×64 preview to draw on with clicks, plus a text box whose text renders into the preview; sent to Mate as a bitmap as you go. Later: ready-made faces.
- **Camera:** snapshot (`/capture`), live video (`:81/stream`) and download.
- **Status:** busy, step counters, last move result, request latency.
- **STOP:** large, always visible.
- **Notes:** a place to record calibration findings (steps per mm, per degree, signs).

## Stack

Plain HTML + JavaScript, no build step. The live view is for watching and debugging — the agent's interface is `capture`.
