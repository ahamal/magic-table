# Magic Table — Project Brief

*Oct 26, 2026 · Ashwin. Original brief, kept for reference. Later decisions in [`decisions.md`](decisions.md) take precedence where they differ (e.g. naming: "companion robot" is now **Mate**; the gantry is **the Frame**).*

## Overview

Magic Table is a tabletop robot that learns any game you explain to it in plain English, then deals, plays, keeps score and talks. It is the planned entry for the Meta Global AI Developer Hackathon (Oct 26 to Nov 4, 2026), indie developer track, theme "Push the Frontier".

- **Hardware:** the builder's existing CoreXY gantry with a suction gripper, an overhead camera, printed fixtures (card flipper, peek camera window), and an optional small companion robot that acts as the AI player's body.
- **Software:** Meta's SAM 3.1 sees the table, Muse Spark reasons about the game and calls the table's MCP tools, and G-code moves the gantry.
- **Hero demo:** poker. The table deals, flips community cards, moves chips, privately peeks at its own hole cards, and bluffs out loud.
- **Pitch:** "A table that learns any game you teach it, and you can build your own."

## The hackathon

Ten days, fully remote, run by Meta and Cerebral Valley. Submissions due Nov 4 at 9:00 PM ET. Check the official rules, especially on pre-existing work.

| Item | Detail |
|---|---|
| Kickoff | Oct 26, livestream |
| Workshops | Oct 27 – Nov 4, live sessions plus Discord office hours |
| Submissions due | Nov 4, 9:00 PM ET |
| Judging | Nov 4 – Nov 8 |
| Winners | Nov 9, closing ceremony with live finals |
| Track | Indie developer: creativity, technical ambition, whether it works |
| Theme | Push the Frontier (robotics, giving a machine a new capability) |
| Models | Muse Spark series, Muse Wonder, Muse Image, SAM 3.1 via Meta Model API; Meta open-weights models; Muse Code coding agent |
| Credits | $150 Meta Model API per participant; for select participants Baseten $100, Modal $100, Fireworks $25 |
| Prizes | $1M cash pool across both tracks; per-place split not yet published |
| Size | Up to 20,000 accepted participants |

Competition estimate (not published): perhaps 6,000–10,000 actually build, 1,000–3,000 submit, a few hundred have a polished working demo, and only dozens to low hundreds are physical hardware projects. Roughly 40–60% likely students.

Past Meta hackathon winners were practical problems with working demos: OrgLens (LlamaCon 2025, expert matching) and Guardian (London 2024, hospital triage). A vision-controlled robot arm made the London finals.

## Existing assets

Most of the plumbing already exists, so the ten days go to AI and robotics, not setup.

- **Xenote:** the builder's browser notebook platform (web-runner, box-runner, versions, AI integration, own MCP server).
- **Vani:** Xenote's messaging layer (browser ↔ Raspberry Pi / ESP32).
- **Robo Diner:** a dosa-cooking robot under $500, built end to end — the CoreXY gantry used here.
- **TinyESP:** ESP32 wireless controllers.
- **Card Games workspace:** existing Xenote card-game work.
- **Other:** Logic Lab, Casita, other education work.

**On hand:** CoreXY gantry, 3D printer, peristaltic pump, Raspberry Pi 3, a small Pi (model to confirm), Arduinos, 28BYJ-48 steppers with ULN2003 boards, Pi Camera v2.1.

Keep the Magic Table clearly new work, separate from existing projects.

## Concept and positioning

The novel part is an AI that learns game rules it has never seen and plays them physically; plain "talk to a robot and it picks things up" is not novel.

**Novelty check (Oct 25):** natural-language pick-and-place is well covered — hackathon entries (ArmMind, a voice-controlled surgical-instrument arm), research on desk organizing and sorting by voice (one picks playing cards), a Fab Academy CoreXY + AI zen-garden machine. A TH Köln paper (May 2026) controls a robot arm through MCP tools. Physical robots still win when the use is fresh (a make-up robot won a Hong Kong physical AI hackathon).

**Positioning:**
1. Lead with the experience: "A table that learns any game you teach it."
2. Add reproducibility: an open guide so anyone can build their own.
3. Plumbing second: "The table is an MCP server, so Muse Spark, or any AI agent, can see and move things in the physical world."
4. Stretch: two AI agents playing cards against each other on the same physical table.

**Dropped:** live assembly copilot (safe but less striking), Junk Drawer Robotics (higher 3D risk), generic desk organizer or coin sorter (not novel).

## Games

Poker is the hero demo; Go and chess are stretch goals to show breadth.

| Game | Role | Needs | Opponent logic | Main risk |
|---|---|---|---|---|
| Poker | Hero demo | Card picks, chips, flipper, peek camera | Muse Spark (logic, pot math, table talk, bluffing) | Picking a single card off a deck |
| Simple card games | Core, days 3–5 | Card picks and dealing | Muse Spark | Same as poker |
| Go (9×9) | Stretch | Stone dispenser, prisoner tray, grid calibration | KataGo for moves, Muse teaches | Board size vs gantry travel |
| Chess | Brief mention at most | Flat-top printed pieces, capture tray, spare queen | Stockfish for moves, Muse teaches | Low novelty |

**Poker:**
- Chips: the cup picks the top chip off a stack; the camera counts stacks.
- Flipping: a printed passive flipper — card face down on a hinged paddle, the gantry pushes its lever, the card lands face up. Curved chute as fallback.
- Peek: the robot reads its own card privately; the table camera never sees other players' cards. *(Now done with Mate's camera — see decisions.)*

**Go:** stones are smooth domes about 22 mm wide, likely the easiest pick. 19×19 is about 42×45 cm, so 9×9 (about 21 cm) or 13×13 (about 30 cm) depending on travel. Feed stones from a printed dispenser, never a heaped bowl.

**Chess:** read the board by detecting which squares changed from the known position, not by identifying pieces. Castling is two pick-and-places.

## System architecture (original)

- **Turn loop:** Muse plans with look(), acts with pick and place, then checks with look() again.
- **Vision:** SAM 3.1 segments the overhead image; ArUco markers map pixels to gantry millimetres. The companion robot carries an ArUco marker.
- **Cost control:** call the model only when a command is given or a turn ends, never per camera frame.
- **Specialist engines:** KataGo (Go), Stockfish (chess); Muse stays teacher and host.

*(Superseded in detail by [`architecture.md`](architecture.md).)*

## Gantry hardware

**Gripper:** 12 mm, 2-layer bellows suction cup on the existing peristaltic pump; no electromagnet for now.

- **Cup:** Industrial Vacuum Suction Cup, 12 mm, 2-layer, Amazon, $15.99 (buy two). Fits on a dime (about 18 mm); 2 layers give height tolerance and seal over coin relief. 25 mm rejected (wider than every US coin).
- **Pump:** the peristaltic pump holds vacuum when stopped (rollers pinch the tube); reversing releases. Expect a grip in 1–3 s. Keep the tube short and narrow.
- **Fitting:** the cup's push-in adapter (likely 4 mm or 6 mm tube) needs an adapter to the pump's silicone tubing, sealed with a zip tie or hot glue.
- **Mount:** printed holder with a small spring or slot so the cup can press down a few mm.
- **Backup:** 12V 370 mini diaphragm vacuum pump + 12V 3-way solenoid valve, or a pump-valve kit.

**Pick sequence:** lower until the cup touches, pump forward 1–2 s, stop (grip holds), move, reverse about 0.5 s to drop.

**Other gantry needs:**
- Z axis to lift and lower the gripper.
- Camera calibration with ArUco markers, day 1.
- G-code from Python; spare outputs can switch the pump.
- Printed fixtures: card flipper, chip and card trays, stone dispenser, flat-top chess set.

**Deferred:** 12V electromagnet + steel washers, MOSFET modules with 1N4007 diodes, vacuum pressure sensor (XGZP6847, to confirm picks). US coins are not magnetic, which is why suction is the main tool.

## Companion robot (now: Mate)

A small wheeled robot on the table. Recommended role: the AI player's body — faces whoever is talking, reacts to bets, "thinks" before calling, shows emotions on a small screen. Alternatives considered: courier (carries chips/cards beyond the gantry's reach), recon (low-angle views; never look at other players' faces or cards).

**Hardware options considered:**

| Option | Parts | Pros | Cons |
|---|---|---|---|
| ESP32 alone | ESP32, 2× 28BYJ-48 + ULN2003, servo | Light, ~10–12 h battery, instant boot | No Camera v2.1 support |
| Pi + Arduino over USB *(chosen)* | Pi 3, Arduino, 2× 28BYJ-48 + ULN2003, servo, camera | Smooth AccelStepper motion, good camera | Heavier, ~4–5 h battery |
| Pi driving ULN2003 directly | Pi, 2× 28BYJ-48 + ULN2003, servo | Fewest parts | Possible stutter |

**Drive:** two 28BYJ-48 wheels, differential steering, ball caster or skid at the back. About 3–5 cm/s with 60 mm wheels. Half-step mode, AccelStepper ramps, coils off when idle.

**Camera pan:** SG90 or MG90S servo; optional second servo for tilt. Power servos from the battery 5V line, `detach()` after moves.

**Tracking and safety:** ArUco marker on its roof; the gantry never lowers where the robot is.

**Power budget (5V):**

| Part | Typical | Peak |
|---|---|---|
| 28BYJ-48, each while moving | ~150 mA | ~200 mA |
| SG90 / MG90S servo | 10 mA idle, 150 mA moving | ~650 mA stalled |
| ESP32, Wi-Fi on | ~120 mA | ~250 mA |
| Raspberry Pi 3 | 500–700 mA | ~1.2 A |
| Camera v2.1 | ~250 mA | ~250 mA |
| Arduino Nano | ~30 mA | ~50 mA |

Pi version: 1.2–1.5 A typical, 2–2.5 A peak — use a 3 A bank, ideally two ports (Pi on one, motors on the other), shared ground, short thick cable. A 10,000 mAh bank gives about 6,000 mAh usable at 5V. Mount the battery low and centred.

**Wi-Fi:** Pi 3 is 2.4 GHz only; use WPA2 (or WPA2/WPA3 mixed). A phone hotspot on 2.4 GHz WPA2 is easiest for demos.

## Scope and risks

A working poker loop with a backup video by Oct 30 matters more than any extra feature.

**Scope tiers:**
- **Must have:** reliable card pick and placement, overhead camera calibration, SAM detection, Muse Spark calling the table's tools, dealing and a playable poker hand with talk.
- **Nice to have:** card flipper, peek camera, chips, a live overlay of what the AI sees and plans.
- **Stretch:** companion robot as the AI's body, 9×9 Go with KataGo, two AI agents playing each other, open "build your own" guide.

| Risk | Fallback |
|---|---|
| Picking one card off a deck drags the next | Lift slowly for the first few mm, or a small diagonal peel |
| Calibration error makes picks miss | Calibrate on day 1 before anything else |
| Peristaltic grip too slow or leaky | Seal every joint; backup diaphragm pump + valve |
| Cup or fitting arrives late | Improvised cup: eyedropper bulb, baster bulb or TPU print |
| API latency too high | Call the model only on commands or end of turn |
| $150 API credits run out | Same as above; partner credits for open-weights models |
| Working solo, hardware eats days | Backup video on Oct 30; companion robot only if core is solid |
| Pre-existing work rules | Check official rules; keep Magic Table clearly new work |

## Sources

- Cerebral Valley event page
- Eventopia listing (themes and model list)
- Meta for Developers announcement on X
- Meta AI: LlamaCon Hackathon winners
- Meta Newsroom: Llama Impact Hackathon London
- TH Köln: robot manipulation via MCP
- ArmMind on lablab.ai
- Fab Academy 2025: RYOAN-JI XY
- Silicon UK: make-up robot wins hackathon
