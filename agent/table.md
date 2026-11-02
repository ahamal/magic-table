# Table guide

How to drive the gantry and the gripper safely and well. The hub enforces the hard limits; everything else here is a recipe that works, not a rule baked into the code. Served at `GET /api/guide/table`. Start at [the agent README](README.md) if you haven't.

## Coordinates

- **Gantry work coordinates, in mm.** X/Y 0, 0 is the middle of the area inside the board markers; Z 0 is the cup touching the board. **Z is the cup's height above the board** (Z+ up).
- **Head vs cup.** GRBL positions the head marker. The cup sits ~20 mm in front of it. To put the **cup** somewhere, use `POST /api/tip {x, y, z}`; `/api/move` moves the head.
- **Cards, Mate and the board** come from `GET /api/scene` in the same coordinates (card `x, y` = center, `angle` = long side, `face` up/down; Mate `x, y, heading`).
- **Anything else: vision.** Cheap first: `GET /api/see` names what's on the board (`[{name, look, count, find}]`). Then `GET /api/find?what=<find>` (comma-separate several) says where each one is in one camera (`cam=1`, the default; `0`; or `mate` for pixels only): `board {x, y, w, h, angle}`, `on_board`, `pick {x, y, clear_mm}`. Use cam 1 for places: cam 0 looks so low that a thing's side stretches its footprint (a 55 mm case came out 95 mm long). Use `see`'s `find` strings: they carry a backup name after `|` ("earbuds case|white object"), because SAM is fussy about names, especially from above. Skip `on_board: false` (markers, the frame) and matches far from the size you expect (the edge of a card in a stack looks like a thin card).
- **Robots in the picture:** find knows where the cup, the head and Mate are and drops a match that's mostly (60 %+) inside one of them, unless Muse Spark says it's a separate thing there (a card on Mate). Every item keeps its `pick`; `robot {inside, near}` says how much of it overlaps a robot and which ones it touches. Something touching the cup or Mate may move when they do: find again after they move.
- **What things are** (which card, a chip's colour, whether a hand holds something): add `ask=<question>` to `find` and each found thing gets Muse Spark's `answer` from its crop, tied to its board place. Tested Nov 2: `what=playing card&ask=Which card is this? Answer like K♠, or face down.` read all 4 face-up cards and the backs right, ~1 s each, all at once. For the whole picture: `GET /api/see?ask=<question>`.
- **How tall is it?** `find` gives where, not how tall: it looks from above. Know it (a card: 0; a chip: 3.3 mm, so a stack of n is 3.3 n; the AirPods case: 21 mm; the notes have more), read it (the notes say how to count chip stacks from the outline), or look with cam 0, the low side view (it doesn't cover the whole board, and Mate or other things can block it). **If you still can't tell, ask the people at the table** rather than guess: say so with `/api/say` ("I can't see that from above: how many chips are in the stack by the red five?"), then wait for the answer (see the agent README). Going down onto something taller than you think presses into it.
- **Picking something found:** with the height known: cup to `pick.x, pick.y` above it, down slowly (F600) to the height minus ~5 mm for a solid thing (the cup must squash to seal: 1.5 mm only touched the case), ~1.5 mm for a card; grip with the pump left on for anything heavier than a card; lift. Then `GET /api/find/check?id=<its id>` with it lifted: `gone: true` means it came up (it compares the item's outline in a fresh picture with find's; same camera). The pick point is within ~2 mm in the middle and near side of the board and up to ~6 mm short (toward the front) on the far side (Nov 2, the notes have the numbers); fine for a 15 mm cup on things wider than ~30 mm.
- **Accuracy:** the cup lands within ~2–3 mm of a target on the board. Best near the middle of the board; weaker far out and high up.

## Hard limits (the hub enforces these)

| | |
|---|---|
| Board bounds | The cup stays **inside the rectangle between the four board markers** (not over them). Moves outside are refused; X/Y jogs stop at the edge. `POST /api/calibration/bounds` re-measures them (do it after moving the markers or the board); it also re-centres X/Y 0, 0 on the rectangle. |
| Z range | **−1 to 150.** −1 is a 1 mm squeeze into the board for a grip; 150 is the top of travel. Moves outside are refused; jogs stop at them. |
| Travel height | **Z 110.** Clears Mate (105 mm to the top of its corner caps). |
| Mate | Never lower the cup onto Mate below Z 110, and never end a move over it below Z 110 (refused). Moves that cross Mate below 110 go up first. A sideways bump is survivable; pressing down into it isn't. **Carrying a card, Mate is in the card's way too:** the hub keeps the *cup* 40 mm off Mate, but a card hangs up to 44 mm past the cup. Near Mate, carry cards at Z 110, or keep the card's far edge 10 mm from Mate. |
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
3. `G1 Z-1.5 F600`: the cup touches and squeezes (its top is soft: 2 mm in is fine). On a stack of n cards add 0.3 × (n − 1). If the card stays behind, go to −2 (only via `/api/send`), and suspect Z: see below.
4. `grip?pump_s=1`. One second of pumping is enough; the sealed line holds ~20 s (a domino held 15 s after 4 s of pumping).

**If cards stop coming up, check Z first.** Nov 2 Z 0 had crept ~1 mm above the board, so −1.5 barely touched and cards stayed behind. Lower the cup over a card 0.5 mm at a time until a person says it touches, then `POST /api/calibration/table` (Zero Z). That fixed it at once.
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
- **Park the head before every `see`, `find` or `look`.** The crane blocks cam 1: the cup hides what's under it, and the tall Z bar hides a strip of board behind it, worst when the head is on the near (−Y) side. Nov 2, head near the front: find missed 2 of 5 red chips and got a third's shape wrong; parked, it found all 5. This build's park spot is in the notes. Nothing warns you: a missing item just isn't there.
- `camera_moved_px` above a couple of pixels means a camera or the board moved: recalibrate (camera) or re-measure the bounds (board). Nothing is corrected automatically.
- **Known gaps:** in `/api/scene`, overlapping or touching cards come out as one blob (or not at all), and rank and suit aren't read: use `find` with `ask=` for those. Detection jitters by ~1 mm between frames.

## After a reset

An Uno reset, a Pi reboot or a power cycle loses GRBL's position (a hub restart doesn't). The hub flags it (`/api/calibration` → `needs_reanchor`) and refuses moves until it's fixed. Unlock (`$X`), then `POST /api/calibration/reanchor`: it restores the saved position, which is exact if nothing moved the head. If the head did move (skipped steps, moved by hand), use `?camera=true` instead: both cameras triangulate the head marker for X/Y, and Z stays GRBL's count (`camera_z` in the answer is a check). A reset after a feed hold (STOP) usually keeps the position; compare `camera_off_mm` before choosing. Never use the jog page's Work zero after calibrating.

## Calibrating

Only when a camera moved (`camera_moved_px` climbing past a few px) or the head marker changed. The 3D page's Calibrate covers the middle of the board (3 × 3 stops at 3 heights, ±90 mm: clear of Mate at its home) in ~1.5 min and keeps the board touch-off and bounds. With bounds set, it rises to the travel height and centres on the board itself, wherever the head is, and refuses (nothing moves) if a stop would take the cup past the bounds or Mate is under the grid; drive Mate home first. Sideways moves are at 6000 mm/min, up and down at 2000. "Stop calibrating" (`POST /api/calibrate/stop`) ends it after the current move, keeping GRBL's position. A first calibration (no bounds yet) is around where the head is: start with the cup at Z 110 or higher over the middle of the board, then touch the cup to the board and press **Zero Z** on the 3D page (`POST /api/calibration/table`: Z becomes 0 there). Use the same after Z skips steps (a stalled lift: the camera's head check jumps): jog down until the cup just touches, press it, raise. Any reset, pause or STOP aborts calibration with no further moves.
