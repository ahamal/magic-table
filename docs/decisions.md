# Decisions

Running log. Newest at the bottom of each section.

## System

- **Body / agent split.** The body is game-agnostic; everything clever is in the agent. *Why:* "learns any game" must be true — nothing below the agent changes per game.
- **Ghost and real share identical I/O,** including images. *Why:* develop the agent without hardware, test the whole perception pipeline in simulation, demo fallback.
- **Images out, raw actions in.** The labeler (SAM + ArUco) is agent-side. *Why:* the body stays dumb and uniform; the agent decides when to spend tokens on labeling.
- **No abstraction in the body.** Raw steps and angles; the agent learns calibration. *Why:* the robot learning its own body is the core of the brain and a strong "push the frontier" story.
- **Safety stays in the body.** Limits, Mate no-go zone, edge reflex, stop. *Why:* falling off the table or crashing the gantry is not something to learn by trying.
- **The agent can be human.** Same API through a web page. *Why:* hardware testing without AI, demo fallback, human-vs-AI on the same interface.
- **Not built on Xenote relays.** Plain web endpoints instead. Xenote stays an option for docs/publishing.

## Hardware

- **The Frame is the Robo Diner gantry** (CoreXY, GRBL, Arduino + RAMPS, limit switches).
- **Pi 5 is the table hub** — body API, Frame driver, overhead camera, VL6180X, pump, Mate client. The brain probably runs there too.
- **Pump: H-bridge driven from Pi 5 GPIO** on the RAMPS 12V supply (recommended, pending pump type). *Why:* RAMPS MOSFETs only switch on/off; the peristaltic pump must reverse to release.
- **Gripper: 12 mm, 2-layer bellows suction cup.** *Why:* fits on a dime; 2 layers are enough because Z, the spring mount and the known stack height handle height; fewer layers grip faster and sway less.
- **VL6180X #1 on the gantry head** (stack heights, picks, pick confirmation). Optional touch switch on GRBL's probe pin for exact contact.
- **Overhead camera: Camera v2 (imx219)** on the Frame, about 50 cm up, on a long ribbon (≤ 1 m) with a 22→15-pin adapter for the Pi 5.
- **Mate: Pi 3B + Arduino + 2× 28BYJ-48/ULN2003 + servos + ov5647 camera + tiny screen.**
- **Peek camera is Mate's camera** (the cheaper ov5647). No third camera needed.
- **VL6180X #2 on Mate**, front, pointing down, wired to the Arduino: table-edge reflex.
- **TF-Luna:** later, on Mate's pan mount, for finding players and obstacles at a distance. Not for Z (20 cm blind zone, ±6 cm).
- **Markers should blend in:** head-marker calibration (removable), small markers on top of frame corners, Mate's marker designed into its look.

## Mate

- **Mate is self-contained:** own API, own control page, own safety. The hub later becomes a client.
- **Raw drive:** `step {s1, s2}` moves both steppers simultaneously and they finish together. No turn/drive abstraction.
- **Firmware keeps physics and safety only:** acceleration ramps, max speed, max steps per command, stop, coils off when idle, edge reflex.
- **Mate doesn't track its own position.** The overhead camera (and in step 1, the human) is the feedback.

## Build order

- **Step 1: Mate + human.** Then Frame + human, then ghost, then the AI agent.
