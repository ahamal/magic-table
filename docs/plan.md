# Plan

Hackathon: Oct 26 – Nov 4, 2026. **Submissions due Nov 4, 9:00 PM ET.**

> **Status, Nov 3 evening:** the checklist below is from the start and is out of date. Working now: the crane picks, places and stacks cards and chips; Esper drives, goes home, turns, flips and peeks at cards; vision (free scene, SAM 3.1 find, Muse Spark reading, the robot filtered out); calibration and the 3D scene; the talk page with live transcription, the voice and Esper's gestures; the MCP server and the live Muse Spark agent. Left: a full poker hand run by Muse alone; record the demo video; submit. Dropped: Ghost, Go/chess.

## Build steps

### Step 1 — Esper + human ◀ now
Esper runs standalone; a person drives it from a browser.
- [ ] Esper hardware assembled: chassis, 2× 28BYJ-48 + ULN2003, ESP32-S3 CAM, servos, OLED
- [x] Hub board: 5V and I2C buses, JST-XH connectors (I2C side tested)
- [ ] Power: power bank into the hub, one 5V source split there, shared ground
- [x] ESP32-S3 firmware: Wi-Fi API, both steppers together, servos, OLED, camera snapshot + stream, stop ([`software/esper/firmware`](../software/esper/firmware))
- [ ] ESP32-S3 CAM: swap boards, `/capture`, card-corner test
- [ ] Control page ([`software/esper/ui`](../software/esper/ui))
- [ ] A human can drive, look, flip, change faces, capture photos and stop
- [ ] By hand: figure out steps per mm / per degree (what the AI will later learn)

### Step 2 — Frame + human
The table hub on the Pi 5; a person plays with the gantry from a browser.
- [x] Frame driver; limits in the hub instead of homing (no limit switches)
- [x] Pump + vent valve via GRBL (CNC Shield), grip/drop in the hub
- [x] Overhead camera: `GET /api/capture` on the hub
- [ ] Camera mount + calibration (head marker)
- [ ] VL6180X on the head (`sense_z`), optional probe switch
- [ ] Hub web server + human table page; Esper connected through the hub
- [ ] Safety layer: limits, Esper no-go zone, e-stop

### Step 3 — Ghost
- [ ] Scene file format, physics-lite, camera-like renderer, simulated sensors
- [ ] Same API as the hub; switch with one setting

### Step 4 — AI agent
- [ ] MCP server wrapping the body API
- [ ] Labeler (SAM 3.1 + ArUco), body model / self-calibration
- [ ] Muse Spark turn loop: look → act → check

### Step 5 — Games and demo
- [ ] Poker (hero demo): deal, flip, chips, peek, table talk
- [ ] Backup video
- [ ] Stretch: Go 9×9 with KataGo, two AI agents, open "build your own" guide
- [ ] Submission

## Timeline

| Date | Target |
|---|---|
| Oct 26 | Kickoff. Project structure. Step 1 begins. |
| Oct 27–28 | Step 1 done (Esper + human). Step 2 started. |
| Oct 29–30 | Step 2 done (Frame + human). Ghost started. |
| Oct 31–Nov 1 | Ghost + AI agent loop |
| Nov 2–3 | Poker end to end, backup video, polish |
| Nov 4 | Submit by 9:00 PM ET |

> **Note:** the original brief aimed for a playable poker hand with backup video by **Oct 30** and put the companion robot last (days 7–9). Starting with Esper shifts that. Watch the schedule — if step 2 slips, poker on the Frame is the priority.
