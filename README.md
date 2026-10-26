# The Magic Table

**A table that learns any game you teach it — and you can build your own.**

A tabletop robot system that learns a game from a plain-English explanation, then deals, plays, keeps score and talks. Entry for the Meta Global AI Developer Hackathon (indie developer track, theme "Push the Frontier"). Submissions due **Nov 4, 2026, 9:00 PM ET**.

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

| | **The Frame** | **Mate** |
|---|---|---|
| What | The Robo Diner CoreXY gantry | Small wheeled companion robot |
| Job | All precise physical work: pick, place, flip, stack | The AI's body at the table: faces players, peeks, emotes, flips |
| Brain host | Raspberry Pi 5 — also the hub for the whole table | Raspberry Pi 3B — self-contained, own API |
| Motion | GRBL on Arduino + RAMPS, limit switches | Arduino (our firmware), 2× 28BYJ-48 + ULN2003 |
| Sensing | Overhead Camera v2, VL6180X on the head | ov5647 camera, VL6180X edge sensor, (TF-Luna later) |
| Gripper / extras | 12 mm 2-layer suction cup on a 12V peristaltic pump | Pan/tilt servos, tiny screen, optional flipper paddle |

## Repository layout

```
the-magic-table/
├── docs/                  brief, architecture, decisions, plan, open questions
├── hardware/
│   ├── frame/             gantry, gripper, pump, sensors, camera mount, wiring
│   ├── mate/              chassis, drive, servos, sensors, screen, power, wiring
│   └── shared/            power, network, markers, printed parts common to both
└── software/
    ├── mate/              ◀ step 1
    │   ├── firmware/      Arduino: raw steppers, servos, edge reflex
    │   ├── server/        Pi 3 web server: Mate's own API
    │   └── ui/            human control panel for Mate
    ├── hub/               Pi 5: the table's body API, Frame driver, safety, Mate client
    ├── ghost/             simulated body: scene files, physics-lite, camera-like renders
    └── agent/             AI brain (Muse Spark via MCP), labeler, body model, game prompts
```

## Where we are

**Step 1 — Mate, driven by a human.** Mate runs standalone: Arduino firmware for raw motion, a small web server on its Pi 3, and a control page in the browser. See [`software/mate/README.md`](software/mate/README.md).

Full sequence in [`docs/plan.md`](docs/plan.md). Open items in [`docs/open-questions.md`](docs/open-questions.md).

## Docs

- [`docs/brief.md`](docs/brief.md) — the original project brief (hackathon, concept, games, hardware notes, risks)
- [`docs/architecture.md`](docs/architecture.md) — layers, body interface, ghost vs real, network
- [`docs/decisions.md`](docs/decisions.md) — what's been decided and why
- [`docs/plan.md`](docs/plan.md) — build steps and timeline
- [`docs/open-questions.md`](docs/open-questions.md) — what's still unknown
