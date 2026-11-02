# Table guide

How to drive the gantry and the gripper safely and well. The hub enforces the hard limits; everything else here is a recipe that works, not a rule baked into the code. Served at `GET /api/guide/table`. Start at [the agent README](README.md) if you haven't.

## Coordinates

- **Gantry work coordinates, in mm.** X/Y 0, 0 is the middle of the area inside the board markers; Z 0 is the cup touching the board. **Z is the cup's height above the board** (Z+ up).
- **Head vs cup.** GRBL positions the head marker. The cup sits ~25 mm in front of it. To put the **cup** somewhere, use `POST /api/tip {x, y, z}`; `/api/move` moves the head.
- **Cards, Mate and the board** come from `GET /api/scene` in the same coordinates (card `x, y` = center, `angle` = long side, `face` up/down; Mate `x, y, heading`).
- **Accuracy:** the cup lands within ~2–3 mm of a target on the board. Best near the middle of the board; weaker far out and high up.

## Hard limits (the hub enforces these)

| | |
|---|---|
| Board bounds | The cup stays **inside the rectangle between the four board markers** (not over them). Moves outside are refused; X/Y jogs stop at the edge. `POST /api/calibration/bounds` re-measures them (do it after moving the markers or the board); it also re-centres X/Y 0, 0 on the rectangle. |
| Z range | **−1 to 150.** −1 is a 1 mm squeeze into the board for a grip; 150 is the top of travel. Moves outside are refused; jogs stop at them. |
| Travel height | **Z 110.** Clears Mate (105 mm to the top of its corner caps). |
| Mate | Never lower the cup onto Mate below Z 110, and never end a move over it below Z 110 (refused). Moves that cross Mate below 110 go up first. A sideways bump is survivable; pressing down into it isn't. |
| Raw G-code | `/api/send` isn't checked against any of this. Use `/api/tip`, `/api/move`, `/api/jog`. |

## Gripper

- `POST /api/gripper/grip` closes the vent valve and turns the pump on; it **stays on** until a drop. Use this for anything heavy, porous or uneven.
- `POST /api/gripper/grip?pump_s=N` runs the pump N seconds, then stops it. The sealed line keeps holding for **about 20 s**: carry and drop within that. `state.held_s` counts up from the grip.
- `POST /api/gripper/drop` stops the pump and vents for 0.3 s: whatever is on the cup falls.
- Gripper commands wait for queued motion, so "move, grip, move, drop" runs in order.

## Recipes

**Pick a card** (thin, flat, smooth)
1. `GET /api/scene` → the card's `x, y`.
2. `POST /api/tip {x, y, z: 3}`: rapid to just above it (stay at travel height first if Mate is anywhere near the path).
3. `G1 Z-0.8 F1200`: the cup touches and squeezes a little. On a stack of n cards add 0.3 × (n − 1).
4. `grip?pump_s=1`. One second of pumping is enough; the vacuum then holds ~20 s.
5. **Peel off at F1500** (`G1 Z5 F1500`), then rapid up to **Z 40** and move. A faster peel (F2000) left every card behind: the seal isn't strong enough yet to yank it.

**Place a card**
1. `POST /api/tip {x, y, z: 5}` (rapid, from Z 40).
2. `G1` at F1200 to **1.2 mm above whatever it lands on** (the board: Z 1.2; on a stack of n cards: 1.2 + 0.3 × n).
3. `drop`, then rapid up to Z 40 before moving away. Getting close before letting go keeps the card from sliding or turning.

**Keep it fast, but check.** Rapid (`G0`) in clear air, slow feed only for the last few mm. Don't sync between steps: GRBL runs the queue in order, and gripper commands wait for the motion before them. A pick and place takes **~7.5 s**. Don't stop for photos mid-carry (it eats the 20 s hold); look after the drop. When trying anything new, check the first card before doing a batch.

**Stack cards neatly.** The cup can't rotate a card: a card keeps the angle it was picked at. Pick a card whose `angle` is within a few degrees of the one it goes onto, and put its center on the other's center. Expect ~2–4 mm and the angle difference of misalignment.

**Other objects.** Leave the pump running (plain `grip`). Approach slowly; stop at the object's top plus the 1 mm squeeze. Unknown heights: come down in small steps and look with cam 0 (the side view).

## Looking

- **Cam 1** (angled, from the front) finds things: cards, Mate, the board markers. **Cam 0** (low, side) shows contact and lifts; use it to check a pick worked.
- Park the head out of the way before a `look`: it hides what's under it (this build's park spot is in the notes).
- `camera_moved_px` above a couple of pixels means a camera or the board moved: recalibrate (camera) or re-measure the bounds (board). Nothing is corrected automatically.
- **Known gaps:** overlapping or touching cards come out as one blob (or not at all); card rank and suit aren't read (ask a vision model with a crop). Detection jitters by ~1 mm between frames.

## After a reset

Any hub restart, Uno reset or power cycle loses GRBL's position. Unlock (`$X`), then `POST /api/calibration/reanchor`: it restores the saved position, which is exact if nothing moved the head. If the head did move (skipped steps, moved by hand), use `?camera=true` instead. Never use the jog page's Work zero after calibrating.

## Calibrating

Only when a camera moved (`camera_moved_px` climbing past a few px) or the head marker changed. It takes ~40 s and keeps the board touch-off and bounds. Start with the cup at Z 110 or higher over the middle of the board, Mate out from under the 120 mm square around it. Calibrate (scene page or `POST /api/calibrate {room}`), then touch the cup to the board and press **Board is here**. Any reset, pause or STOP aborts calibration with no further moves.
