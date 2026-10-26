# Plan

Hackathon: Oct 26 – Nov 4, 2026. **Submissions due Nov 4, 9:00 PM ET.**

## Build steps

### Step 1 — Mate + human ◀ now
Mate runs standalone; a person drives it from a browser.
- [ ] Mate hardware assembled: chassis, 2× 28BYJ-48 + ULN2003, Arduino, servos, camera, screen, edge sensor
- [ ] Power: 3A two-port bank (Pi on one port, Arduino + motors on the other, shared ground)
- [ ] Arduino firmware: raw steps for both steppers together, servos, edge reflex, stop ([`software/mate/firmware`](../software/mate/firmware))
- [ ] Mate server on the Pi 3 ([`software/mate/server`](../software/mate/server))
- [ ] Control page ([`software/mate/ui`](../software/mate/ui))
- [ ] A human can drive, look, flip, change faces, capture photos and stop
- [ ] By hand: figure out steps per mm / per degree (what the AI will later learn)

### Step 2 — Frame + human
The table hub on the Pi 5; a person plays with the gantry from a browser.
- [ ] GRBL homing, soft limits, Frame driver
- [ ] Pump via H-bridge, pick/release
- [ ] Overhead camera + calibration (head marker)
- [ ] VL6180X on the head (`sense_z`), optional probe switch
- [ ] Hub web server + human table page; Mate connected through the hub
- [ ] Safety layer: limits, Mate no-go zone, e-stop

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
| Oct 27–28 | Step 1 done (Mate + human). Step 2 started. |
| Oct 29–30 | Step 2 done (Frame + human). Ghost started. |
| Oct 31–Nov 1 | Ghost + AI agent loop |
| Nov 2–3 | Poker end to end, backup video, polish |
| Nov 4 | Submit by 9:00 PM ET |

> **Note:** the original brief aimed for a playable poker hand with backup video by **Oct 30** and put the companion robot last (days 7–9). Starting with Mate shifts that. Watch the schedule — if step 2 slips, poker on the Frame is the priority.
