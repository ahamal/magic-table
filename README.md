# The Magic Table

**A table that learns any game you teach it — and you can build your own.**

A tabletop robot system that learns a game from a plain-English explanation, then deals, plays, keeps score and talks. Entry for the Meta Global AI Developer Hackathon (indie developer track, theme "Push the Frontier"). Submissions due **Nov 4, 2026, 9:00 PM ET**.

> **Agents (and people) driving the table: start at [agent/](agent/README.md).** Everything that's available (gantry, cameras, Esper, speaker, talk page, notes) and how to use it. The hub serves it at `http://raspberrypi.local:8000/guide`, and as plain text at `/api/guide`.

## The idea in one picture

```
┌──────────────── Agent (AI or human) ────────────────┐
│  understands images, knows the rules, plans moves,   │
│  learns its own body (calibration), budgets tokens   │
└──────────────────────────┬──────────────────────────┘
                           │  identical I/O: images out, raw actions in
┌──────────────────────────▼──────────────────────────┐
│  Body — game-agnostic, never knows what is played    │
│     ghost (simulation)   or   real (hardware)        │
│  + safety layer the agent can't bypass               │
└─────────────────────────────────────────────────────┘
```

- **The body knows nothing about games.** It exposes cameras, raw actuators and sensors. Poker, Go or anything else lives entirely in the agent.
- **Ghost and real are interchangeable.** Same inputs, same outputs (including camera-like images), so the agent can't tell them apart.
- **The agent can be an AI or a human.** Both use the same interface — the human through a web page, the AI (Muse Spark) through MCP.
- **No abstraction in the body.** Raw steps, raw servo angles. Mapping commands to motion (calibration) is the agent's job — the robot learns its own body.

## The two robots

| | **The Frame** | **Esper** |
|---|---|---|
| What | A CoreXY gantry, rebuilt from salvaged parts | Small wheeled companion robot |
| Job | All precise physical work: pick, place, flip, stack | The AI's body at the table: faces players, peeks, emotes, flips |
| Brain host | Raspberry Pi 5 — also the hub for the whole table | Freenove ESP32-S3 CAM — self-contained, own API over Wi-Fi |
| Motion | Standard GRBL 1.1 (CoreXY) on an Arduino Uno + GRBL CNC Shield, NEMA 17 on GT2 belts; no limit switches | ESP32 (our firmware), 2× 28BYJ-48 + ULN2003 |
| Sensing | Overhead Camera v2, VL6180X on the head | GC0308 camera on the S3 board (snapshot + live stream), (TF-Luna later) |
| Gripper / extras | 15 mm 2-layer suction cup, 12V diaphragm pump + vent valve | 0.96" OLED face (bitmaps and animations), flipper paddle servo (direct from the ESP32) |

**Built from:** the Frame is new for this project, built from a dismantled earlier machine: its rails, NEMA 17 steppers, GT2 belts and drivers were salvaged, then cut, modified and reassembled into a new CoreXY frame with a new head (suction gripper, cameras, markers). The electronics come from a Longruner CNC kit (an Arduino Uno with a GRBL CNC Shield) running standard, unmodified GRBL 1.1 with CoreXY. Everything else (the hub, vision, calibration, Esper, the agent) was written during the event; see the git history.

## Repository layout

```
the-magic-table/
├── docs/                  brief, architecture, decisions, plan, open questions
├── hardware/
│   ├── frame/             gantry, gripper, pump, sensors, camera mount, wiring
│   ├── esper/              chassis, drive, servos, sensors, screen, power, wiring
│   └── shared/            power, network, markers, printed parts common to both
└── software/
    ├── esper/              ◀ step 1
    │   ├── firmware/      ESP32-S3: Esper's own API, raw steppers, flipper servo, face, camera
    │   ├── server/        retired (was the Pi 3 web server)
    │   └── ui/            human control panel for Esper
    ├── hub/               Pi 5: the table's body API, Frame driver, safety, Esper client
    ├── ghost/             simulated body: scene files, physics-lite, camera-like renders
    └── agent/             AI brain (Muse Spark via MCP), labeler, body model, game prompts
```

## Where we are

**Step 1 — Esper, driven by a human.** Esper runs standalone: one ESP32 program serves its API over Wi-Fi, drives the motors, and serves a control page to the browser. See [`software/esper/README.md`](software/esper/README.md).

Full sequence in [`docs/plan.md`](docs/plan.md). Open items in [`docs/open-questions.md`](docs/open-questions.md).

## Docs

- [`docs/brief.md`](docs/brief.md) — the original project brief (hackathon, concept, games, hardware notes, risks)
- [`docs/architecture.md`](docs/architecture.md) — layers, body interface, ghost vs real, network
- [`docs/decisions.md`](docs/decisions.md) — what's been decided and why
- [`docs/log.md`](docs/log.md) — dated build log: what happened and what we learned
- [`docs/plan.md`](docs/plan.md) — build steps and timeline
- [`docs/open-questions.md`](docs/open-questions.md) — what's still unknown
