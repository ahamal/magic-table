# Mate control page

The human agent's interface to Mate. Built into the firmware ([`../firmware/firmware.ino`](../firmware/firmware.ino), `PAGE`) and served at `http://mate.local/`; uses only the public API, exactly what an AI would use.

## Controls

- **Wheels:** speed and accel sliders, an arrow pad (↑ ↓ ← → plus a stop square) with a steps-per-press box, the arrow keys on the keyboard (Space or Esc stops), and raw s1/s2 inputs with Go. The wheels face opposite ways: same sign on both turns Mate (both + = anticlockwise), opposite signs drive it (s1 −, s2 + = forward). The pad's mapping is `DIRS` in the page script.
- **Faces:** 19 animations drawn in the page itself and sent as frames: eyes, chicken, happy, wink, love, sleepy, surprised, angry, dizzy, talking, heartbeat, bounce, rain, stars, code, spinner, fireworks, countdown, and marquee (scrolls whatever is in the screen text box). Tapping one previews it on the page and plays it on Mate; **loop** or **once** sets `X-Repeat`. They live in `FACES` in the page script: each is `[frames, fps, draw(i, n)]` on a 128×64 canvas, white on black.
- **Flipper servo:** a slider (raw angle).
- **Screen:** a 128×64 preview to draw on with clicks, plus a text box whose text renders into the preview; sent to Mate as a bitmap as you go. Later: ready-made faces.
- **Camera:** snapshot (`/capture`), live video (`:81/stream`) and download.
- **Status:** busy, step counters, last move result, request latency.
- **STOP:** large, always visible.
- **Notes:** a place to record calibration findings (steps per mm, per degree, signs).

## Stack

Plain HTML + JavaScript, no build step. The live view is for watching and debugging — the agent's interface is `capture`.
