# Start here

You're an agent (AI or person) about to use the Magic Table: a gantry that picks and places things on a game board, and **Mate**, a small robot that talks to the people at the table. This folder is everything that's available and how to use it. The hub serves it: `GET http://raspberrypi.local:8000/api/guide` (this page), `/api/guide/table`, `/api/guide/mate`; for people, `http://raspberrypi.local:8000/guide`.

**Read in this order:** this page → [table](table.md) → [mate](mate.md) → this build's notes (`GET /api/notes`). Every build is a little different (offsets, timings, what failed); the notes are where agents and people write down what they learned about *this* one. **Add to them** as you learn (`POST /api/notes {text, by}`): what you tried, what happened, the numbers. If you calibrate something, the numbers go in the notes.

## What's there

| | Where | What |
|---|---|---|
| **Gantry + gripper** | hub `:8000` | Moves a suction cup over the board: `/api/tip` (cup to x, y, z), `/api/move`, `/api/jog`, `/api/gripper/{grip,drop,...}`. [table.md](table.md) |
| **Overhead cameras** | hub `:8000` | `GET /api/scene`: where the cards, Mate and the head are, in board mm (no cloud AI needed). `GET /api/capture?cam=0\|1`: a photo. Cam 1 (angled, front) finds things; cam 0 (low, side) watches picks. |
| **Mate** | `http://mate.local` | Wheels, a flipper arm, a face screen, a camera. Its own HTTP API. [mate.md](mate.md) |
| **Speaker** | hub `POST /api/say {text}` | Talk to the people at the table, out loud. |
| **Microphone** | hub `GET /api/transcripts` | What people said on the talk page (`https://raspberrypi.local:8443/talk`, any phone). |
| **Notes** | hub `GET/POST /api/notes` | What's been learned about this build. Read first, add as you go. |
| **3D view** | `http://raspberrypi.local:8000/scene` | Live picture of everything, for people watching. |

## How to behave

- **Ask the humans.** If something is impossible, unclear, risky, or you're stuck (a card won't come up, something's in the way, you can't see what you need), say so out loud with `/api/say` and ask. Then read their answer from `/api/transcripts`. Asking is part of the job, not a failure.
- **Mate is the friendly one.** It's how the table relates to people: expressive eyes on its face most of the time (happy, curious, looking around), gestures with its flipper (wave, salute), looking at people with its camera. Keep it lively but not frantic.
- **Safety first, then speed.** The hub refuses the dangerous things (Z limits, board bounds, lowering onto Mate). Inside those, go fast for steps that are proven, slow for anything new, and check the first try before repeating it.
- **Look, act, check.** Before a move, look (`/api/scene`); after it, look again. Cameras and counts can be wrong; the photo is the truth.
- **Keep notes.** The next agent starts from what you learned.

## Working together: gantry + Mate

- Mate can **turn in place**, so it can turn things: the gantry puts a card on Mate's top, Mate rotates, the gantry picks the card back up at the new angle (the cup itself can't rotate cards). A card on Mate's top covers Mate's marker, so the camera loses Mate's heading while it's there: count the turn from Mate's step calibration instead (in the notes).
- The gantry must **never press down on Mate** (the hub refuses it below travel height, Z 110). Bumping Mate sideways is survivable but not a plan.
- Mate has no position sense of its own; the overhead camera (`/api/scene` → `mate`) is where it is.
