# Ghost (simulated body)

A simulated table with **exactly the same API and outputs** as the hub. Step 3.

## Responsibilities

- **Scene file** (data, not code): generic shapes — box, dome, cylinder — with sizes, front and back images, positions, stacks; actuators with generic types (e.g. `invert`, `push`).
- **Physics-lite:** stacking; `pick` succeeds only if the cup lands on an object and takes the top one; actuators act on whatever sits in their area. Optional failure rates (e.g. double picks).
- **Camera-like rendering:** same resolution and viewpoint as the overhead camera, ArUco markers, real textures (photos of the actual pieces), only the back of face-down objects. A matching render for Mate's camera.
- **Simulated sensors:** `sense_z` = top surface height + ~1 mm noise; `probe` = exact height.
- **Simulated Mate:** raw `step {s1, s2}` with a hidden "true" calibration the agent has to discover.
- Optional realistic delays.

## Rule

The ghost must never reveal more than the real table could. Hidden faces stay hidden because the renderer only draws backs.
