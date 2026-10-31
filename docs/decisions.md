# Decisions

Running log. Newest at the bottom of each section.

## System

- **Body / agent split.** The body is game-agnostic; everything clever is in the agent. *Why:* "learns any game" must be true — nothing below the agent changes per game.
- **Ghost and real share identical I/O,** including images. *Why:* develop the agent without hardware, test the whole perception pipeline in simulation, demo fallback.
- **Images out, raw actions in.** The labeler (SAM + ArUco) is agent-side. *Why:* the body stays dumb and uniform; the agent decides when to spend tokens on labeling.
- **No abstraction in the body.** Raw steps and angles; the agent learns calibration. *Why:* the robot learning its own body is the core of the brain and a strong "push the frontier" story.
- **Safety stays in the body.** Limits, Mate no-go zone, stop. *Why:* falling off the table or crashing the gantry is not something to learn by trying.
- **The agent can be human.** Same API through a web page. *Why:* hardware testing without AI, demo fallback, human-vs-AI on the same interface.
- **Not built on Xenote relays.** Plain web endpoints instead. Xenote stays an option for docs/publishing.

## Hardware

- **The Frame is the Robo Diner gantry** (CoreXY, GRBL, limit switches). The board turned out to be an **Uno + CNC Shield V3**, not RAMPS.
- **Pi 5 is the table hub** — body API, Frame driver, overhead camera, VL6180X, pump, Mate client. The brain probably runs there too.
- ~~**Pump: H-bridge driven from Pi 5 GPIO** on the RAMPS 12V supply.~~ Replaced below.
- **Gripper: 12 mm, 2-layer bellows suction cup.** *Why:* fits on a dime; 2 layers are enough because Z, the spring mount and the known stack height handle height; fewer layers grip faster and sway less.
- **VL6180X #1 on the gantry head** (stack heights, picks, pick confirmation). Optional touch switch on GRBL's probe pin for exact contact.
- **Overhead camera: Camera v2 (imx219)** on the Frame, about 50 cm up, on a long ribbon (≤ 1 m) with a 22→15-pin adapter for the Pi 5.
- ~~**Mate: Pi 3B + Arduino + 2× 28BYJ-48/ULN2003 + servos + ov5647 camera + tiny screen.**~~ Replaced below.
- **Peek camera is Mate's camera.** No third camera needed. (Now the S3 board's GC0308; an OV2640 fits the same connector if it can't read cards.)
- ~~**VL6180X #2 on Mate**, front, pointing down: table-edge reflex.~~ Dropped Oct 31 with the move to the S3. *Why:* frees I2C and space; the hub's no-go zone (overhead camera) and the per-command step limit keep Mate on the table instead.
- **Mate runs on an ESP32, no Pi.** Freenove ESP32-S3-WROOM CAM (8 MB PSRAM, USB-C, bundled GC0308 camera) since Oct 31; a regular ESP32 DevKit before that. *Why:* the Pi was bulky, slow to set up and kept under-volting; the ESP32 is lighter, boots instantly and gives ~2–3× the battery life. The heavy thinking is in the cloud and on the Pi 5 anyway. *Risk:* the 640×480 GC0308 reading card corners — test first.
- **Face: 0.96" SSD1306 OLED (128×64) on the head, camera just below it.** *Why:* the face and the camera always look the same way; `/screen` takes raw images.
- **No pan or tilt servos; only the flipper** (Oct 31). The head is fixed; Mate turns its body to look around.
- **Screen animations are preloaded, not streamed** (Oct 31): up to 64 frames in one `/screen` request, looped on Mate at `X-FPS`. *Why:* a frame is only 1 KB, but streaming stutters whenever Wi-Fi does.
- ~~**Servos on a PCA9685.**~~ **Servos straight from the ESP32-S3's PWM** (GPIO 38–40) since Oct 31. *Why:* the PCA9685 took too much space, and without the edge sensor the S3 has the pins. Servo power stays on the 5V side. **Speech moves to the hub.**
- **Power: one 5V source split at a perfboard hub** (power bank via cut USB cable; CanaKit on the bench), JST-XH connectors, GND on pin 1.
- **TF-Luna:** later, on Mate's head, for finding players and obstacles at a distance. Not for Z (20 cm blind zone, ±6 cm).
- **Markers should blend in:** head-marker calibration (removable), small markers on top of frame corners, Mate's marker designed into its look.
- **Suction: 12V diaphragm pump + normally-closed solenoid vent valve** (AIRZOE 2V025-08, direct-acting). Pump on to grip and hold; pump off and valve pulsed ~0.3 s to drop. *Why:* the peristaltic pump was too weak; a diaphragm pump can't reverse, so a valve does the release, as on uArm/Dobot arms and vending pickers. A pilot-operated valve (4V210) won't work on vacuum.
- **Gripper driver: a Nano over USB from the Pi 5**, two 30N06L logic-level MOSFET modules, a 1N4007 across each load. No H-bridge. *Why:* the Pi 5 never touches the 12V side; a mistake costs a Nano, not the hub.
- **Frame speed at 12V: X/Y 9000 mm/min, acceleration 500 mm/s².** *Why:* 12000 skipped steps; 24V would be faster but needs a second supply for the 12V pump and valve. Not worth it before the deadline.

## Mate

- **Mate is self-contained:** own API, own control page, own safety. The hub later becomes a client.
- **Raw drive:** `step {s1, s2}` moves both steppers simultaneously and they finish together. No turn/drive abstraction.
- **Firmware keeps physics and safety only:** acceleration ramps, max speed, max steps per command, stop, coils off when idle.
- **Mate doesn't track its own position.** The overhead camera (and in step 1, the human) is the feedback.

## Build order

- **Step 1: Mate + human.** Then Frame + human, then ghost, then the AI agent.
