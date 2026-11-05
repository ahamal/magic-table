# The Magic Table

**Two small, limited robots and an AI that sees the table: together they run a game of cards that neither robot could play alone.**

Entry for the Meta Global AI Developer Hackathon (indie developer track, theme "Push the Frontier"). Submissions due **Nov 4, 2026, 9:00 PM ET**.

**Demo video:** [https://youtu.be/PkLwDHRM7E8](https://youtu.be/PkLwDHRM7E8)

> **Agents (and people) driving the table: start at [agent/](agent/README.md).** Everything that's available (gantry, cameras, Esper, speaker, talk page, notes) and how to use it. The hub serves it at `http://raspberrypi.local:8000/guide`, and as plain text at `/api/guide`.

## The idea: more than the sum of its parts

Neither robot can play cards on its own:

| | Can | Can't |
|---|---|---|
| **The crane** (a CoreXY gantry with a suction cup) | Lift a card and put it anywhere on the table, to within ~2–3 mm | Turn a card (the cup can't rotate), or see a face-down card's face |
| **Esper** (a small wheeled robot with a flipper arm, a face and a camera) | Turn a card on her back, flip it over, lift its corner to peek at it, and react to the players | Lift anything |
| **Muse Spark** (Meta's model) | See the table, read the cards, know the rules, talk to the players | Touch anything |

Together they deal, turn, flip and peek at cards, and Muse runs the game and talks to the people at the table while Esper reacts. The parts are humble on purpose: the frame is rebuilt from a dismantled machine, Esper runs on cheap stepper motors, and her arm is a bent plastic knife. What makes them a card dealer is how they work together.

## What it does

- **Talk to the table.** Players speak (or type) on the talk page from any phone: `https://raspberrypi.local:8000/talk`. Muse Voice Transcribe turns the speech into text live; Muse Spark acts on it and answers out loud on the table's speaker; Esper reacts with gestures (faces, flipper and wheel moves). Esper never speaks.
- **See the table.** Two cameras and printed ArUco markers give every card, chip stack, deck, the crane's head and Esper a position in millimetres. Free, on the Pi, twice a second. When that's not enough, SAM 3.1 finds things by name and Muse Spark reads what they are.
- **Move cards.** Pick, place and stack cards (~7.5 s a card), stack chips, carry cards to Esper.
- **Turn, flip and peek with Esper.** The crane puts a card on Esper; she turns it to any angle, flips it over (14 of 14 flat in testing), or lifts its edge so her camera can read a face-down card.
- **Run a game.** Muse Spark drives all of it through an MCP server, following written guides for the table, Esper and poker.

**Tested:** every piece above, by hand and through the hub's API, plus the live Muse agent on short tasks (describing the table, stacking chips). **Not done yet:** a full hand of poker run by Muse alone from start to finish, and the simulated table ("ghost") planned in the design.

## Built with Meta AI

| Model | Used for |
|---|---|
| **Muse Spark** (`muse-spark-1.3`, Meta Model API) | The agent: runs the table through MCP tools. Also reads cards from camera crops, names what's on the board, and checks which things a search found. |
| **SAM 3.1** (Meta Model API) | Finds things by name in a camera picture ("playing card", "poker chip", "white object") and outlines them, so the hub can place them on the board. |
| **Muse Voice Transcribe** (Meta Model API) | Live speech-to-text on the talk page (realtime stream, ~0.3 s behind the speaker), biased toward card-table words. |

Speech out is Piper, a local voice on the Pi (Meta's Model API has no text-to-speech).

## How it fits together

```
 phones (talk page)          Muse Spark agent (agent_runner.py --live)
        │                                │  MCP tools (mcp_server.py)
        ▼                                ▼
 ┌──────────────── hub: Raspberry Pi 5, port 8000 ────────────────┐
 │  chat + speech in/out · cameras + vision · calibration          │
 │  safety: board bounds, Z limits, keeps the cup off Esper        │
 └──────┬──────────────────┬──────────────────┬───────────────────┘
        │ USB              │ Wi-Fi            │ Bluetooth
        ▼                  ▼                  ▼
  Uno + GRBL          Esper (ESP32-S3)     speaker
  crane + suction     wheels, flipper,
  pump and valve      face, camera
```

- **The hub** (`software/hub/`) owns all the hardware and keeps the agent safe: it refuses moves outside the board or into Esper, drives Esper with the overhead camera checking, and serves every page (home, jog, 3D scene, vision, talk).
- **The agent** (`software/agent/`) is Muse Spark in a loop over the MCP server. It has no raw G-code and no direct access to Esper: every move goes through the hub's limits.
- **The guides** (`agent/`) are how the agent knows what to do: recipes, measured numbers and lessons learned live there, not in code.

## The robots

| | **The crane (the Frame)** | **Esper** |
|---|---|---|
| What | A CoreXY gantry, rebuilt from salvaged parts | Small wheeled companion robot, 130 × 130 × 100 mm plywood box |
| Job | All precise physical work: pick, place, stack | Turn, flip and peek at cards; the table's character |
| Controller | Arduino Uno + GRBL CNC Shield, driven by the Raspberry Pi 5 hub | Freenove ESP32-S3 CAM, its own API over Wi-Fi (`esper.local`) |
| Motion | Standard GRBL 1.1 (CoreXY), NEMA 17 on GT2 belts; no limit switches | 2× 28BYJ-48 steppers + ULN2003, a servo flipper arm |
| Sensing | Two cameras (Camera v2 angled from the front, ov5647 low at the side), ArUco markers on the board and the head | GC0308 camera on the board |
| Gripper / extras | 15 mm 2-layer suction cup, 12V diaphragm pump + vent valve, switched by GRBL | 0.96" OLED face (32 gestures, 24 reaction faces), flipper arm |

**Built from:** the crane is new for this project, built from a dismantled earlier machine: its rails, NEMA 17 steppers, GT2 belts and drivers were salvaged, then cut, modified and reassembled into a new CoreXY frame with a new head (suction gripper, cameras, markers). The electronics come from a Longruner CNC kit (an Arduino Uno with a GRBL CNC Shield) running standard, unmodified GRBL 1.1 with CoreXY. Everything else (the hub, vision, calibration, Esper, the agent) was written during the event; see the git history.

## Run it

1. **Hub on the Pi 5:** setup, the API key file and the service in [software/hub/README.md](software/hub/README.md). Pages at `http://raspberrypi.local:8000/`.
2. **Esper:** flash [software/esper/firmware](software/esper/firmware/README.md) (Wi-Fi in a git-ignored `secrets.h`).
3. **Calibrate** from the 3D page (`/scene`): Work zero with the cup on the board in the middle, then Calibrate.
4. **The agent**, on the Pi:

   ```bash
   cd ~/hub && export MODEL_API_KEY=$(grep MODEL_API_KEY .env | cut -d= -f2)
   .venv/bin/python mcp/agent_runner.py --live --clear-chat
   ```

   Then talk to the table on the talk page. Details in [software/agent/MCP_README.md](software/agent/MCP_README.md). Keep STOP (on the jog page) in reach.

## Repository layout

```
the-magic-table/
├── agent/                 the guides the agent reads: start, table, Esper, poker; Esper's gestures
├── docs/                  brief, architecture, decisions, plan, build log, demo shooting script
├── media/                 the demo video, clips, photos and screenshots (shot list in its README)
├── hardware/
│   ├── frame/             the crane: parts, wiring, GRBL settings, ArUco markers and head plate
│   ├── esper/             chassis and wheels (printable parts)
│   └── shared/            power and parts common to both
└── software/
    ├── hub/               Pi 5: the table's API, GRBL, gripper, cameras, vision, calibration, chat, voice, pages
    ├── agent/             MCP server, Muse Spark runner (live mode), tests
    ├── esper/             ESP32-S3 firmware, faces, control page
    ├── gripper/           retired: the first gripper on a separate Nano (replaced by GRBL's own pins)
    └── ghost/             planned simulator (not built)
```

## Docs

- [`docs/log.md`](docs/log.md): dated build log, what happened and what we learned
- [`docs/notes-on-this-build.md`](docs/notes-on-this-build.md): the hub's notes, measured numbers and lessons the agents read before moving anything
- [`docs/decisions.md`](docs/decisions.md): what was decided and why
- [`docs/architecture.md`](docs/architecture.md): layers, body interface, network
- [`docs/plan.md`](docs/plan.md), [`docs/open-questions.md`](docs/open-questions.md), [`docs/brief.md`](docs/brief.md) (the original brief)
- [`docs/desk-duo-shooting-script.md`](docs/desk-duo-shooting-script.md): the demo video plan

## License

MIT: see [LICENSE](LICENSE).
