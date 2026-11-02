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
- **Gripper: 2-layer bellows suction cup, sold as 12 mm, measures 15 mm across.** *Why:* fits on a dime; 2 layers are enough because Z, the spring mount and the known stack height handle height; fewer layers grip faster and sway less.
- **VL6180X #1 on the gantry head** (stack heights, picks, pick confirmation). Optional touch switch on GRBL's probe pin for exact contact.
- **Overhead camera: Camera v2 (imx219)** on the Frame, about 50 cm up, with a 22→15-pin cable to the Pi 5.
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
- ~~**Gripper driver: a Nano over USB from the Pi 5.**~~ Replaced Oct 31: it made a ground loop that knocked the Uno off USB on every move.
- **Gripper driver: GRBL itself.** Two 30N06L logic-level MOSFET modules on the CNC Shield: pump on CoolEn (`M8`/`M9`), vent valve on SpnDir (`M4 S0` / `M3 S0`), a 1N4007 across each load. *Why:* one USB cable means one ground path; no extra board or firmware; grips and drops stay in order with the moves. The Pi 5 still never touches 12V.
- **Overhead camera on the Pi 5's own CSI port**, opened once by the hub (picamera2) and served at `GET /api/capture`. *Why:* about 0.04 s per photo, and one fewer board than a camera Pi.
- **Frame speed at 12V: X/Y 9000 mm/min, acceleration 500 mm/s².** *Why:* 12000 skipped steps; 24V would be faster but needs a second supply for the 12V pump and valve. Not worth it before the deadline.

## Mate

- **Mate is self-contained:** own API, own control page, own safety. The hub later becomes a client.
- **Raw drive:** `step {s1, s2}` moves both steppers simultaneously and they finish together. No turn/drive abstraction.
- **Firmware keeps physics and safety only:** acceleration ramps, max speed, max steps per command, stop, coils off when idle.
- **Mate doesn't track its own position.** The overhead camera (and in step 1, the human) is the feedback.
- **Mate flips cards** (Nov 2). The gantry places a card on Mate's lowered flipper; Mate lifts and rolls forward at the same time and the card tips over. *Why:* the suction cup can't turn a card over, and a passive flipper part on the board would need its own space and setup. Mate's flipper already exists and goes anywhere.
- **One agent runs it all: the crane is controlled, Mate is puppeteered, the agent speaks as itself** (Nov 2). The speaker is the table's (the Pi's); whoever drives the table (Muse, Claude) speaks through it under its own name: calm, exact, dry wit. The crane is its hand, with no personality. Mate is a character the same agent performs: it never speaks or makes a sound; it talks with gestures (a reaction face plus flipper and wheel moves, `/api/mate/gesture`), each logged in the chat as Mate's. *Why:* invented names (the House, Dr. Crane, Argus…) made it complicated; one mind playing both keeps speech and gestures in time, and a composed voice next to a silent, expressive Mate reads at once. Voice: Piper `en_US-norman-medium` (male), pace 0.85; a female voice (Semaine Prudence) didn't sound balanced. Meta's open-weight MMS-TTS was tried: one flat English voice, and ~2× slower than real time on the Pi.
- **Wheels at full speed and acceleration; the flipper at ≤ 60% of its max, always with a `speed`** (Nov 2). *Why:* a fast flipper draws enough current to drop Mate off Wi-Fi about 5% of the time.

## Build order

- **Step 1: Mate + human.** Then Frame + human, then ghost, then the AI agent.
