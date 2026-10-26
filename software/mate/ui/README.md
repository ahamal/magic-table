# Mate control page

The human agent's interface to Mate. Served by the Mate server; uses only the public API, exactly what an AI would use.

## Controls

- **Wheels:** two raw inputs (s1, s2 half-steps) plus speed and accel, and a few quick buttons (e.g. `+400/+400`, `+400/−400`) — the human works out what they do.
- **Servos:** a slider per servo (raw angle).
- **Screen:** face buttons or image upload (depends on the screen decision).
- **Say:** text box, if a speaker is fitted.
- **Capture:** button + last photo.
- **Status:** busy, step counters, edge reading, power warnings.
- **STOP:** large, always visible.
- **Notes:** a place to record calibration findings (steps per mm, per degree, signs).

## Stack

Plain HTML + JavaScript, no build step. Optional live view for debugging only — the interface is `capture`.
