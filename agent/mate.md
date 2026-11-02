# Mate guide

Mate is a small wooden robot on the board: two wheels, a flipper arm, a face screen and a camera, on its own Wi-Fi API at `http://mate.local`. It's the table's friendly helper and a character you puppeteer: it **never speaks and makes no sound**. It talks with gestures (below): its face, flipper and wheels. The full API reference (every endpoint, field and error) is [software/mate/README.md](../software/mate/README.md); this page is how to use it. Served at `GET /api/guide/mate`.

## Calls you'll use

| Call | What |
|---|---|
| `GET /info` | Limits, screen size, camera. Once at start. |
| `GET /status` | `busy`, the last move (`last.d1/d2`, `result`), flipper angle (`servo_now`), screen, `boots`. |
| `POST /step?s1=&s2=&speed=800&accel=1000` | Move both wheels (half-steps, ±4096 max per call). Returns at once; poll `/status` until `busy` is false. Use full speed and acceleration (`speed=800&accel=1000`): slower is sluggish. |
| `POST /stop` | Stop the wheels now. |
| `POST /servo?angle=&speed=` | The flipper (degrees). |
| `POST /screen` | Show frames on the face (128×64, 1 bit/pixel, 1024 bytes a frame, up to 64 frames, `X-FPS`, `X-Repeat`). |
| `GET /capture` | A 640×480 JPEG from Mate's camera, ~1 s. |

## Driving

- **Easiest: let the hub drive it.** `POST hub/api/mate/goto {x, y, heading}` puts Mate's turning centre on (x, y) in board mm and turns it to `heading`, looking with the camera and correcting until it's within ~5 mm and ~3°. It raises the gantry head out of the way first and refuses spots off the board.
- **It looks before it drives.** Unless you pass `check: false`, before a move (`goto`, `home`, `look`) cam 1 takes a fresh picture and checks where Mate's footprint will go (the turns it makes and the drive, 3 mm to spare) for anything on the mat that isn't Mate, the crane or a board marker (~1 s, no API call). Something there: it refuses with `in_the_way` [{x, y}] and doesn't move. Then go around (a waypoint first), pick another `side` to look from, or ask a person to move it. It can't see dark things on the dark mat, and it only checks the mat.
- **Cards aren't in Mate's way.** It rides 3 mm off the board and drives over or nudges a card, so the check ignores anything shaped like one lying card. Chips, stacks of cards and everything else still stop it.
- **When to skip it:** `check: false` for a short hop where you've just looked, or to push things on purpose. Mate is a fine bulldozer for chips: shove the pot to the winner, sweep a mess off the play area. Say it as you do it ("Your winnings, sir."). Never push through cards you'll want to pick later, or anything tall that could topple onto them.
- **Home:** `POST hub/api/mate/home` parks Mate at its home spot: on this build the middle of the far margin, facing the players (the notes have it). Park the gantry head where the notes say first (this build: the back right corner): parked elsewhere, the Z bar or its wires can hide Mate's marker from the camera. `GET hub/api/mate/home` says where that is; `POST hub/api/mate/home/set` saves a new one (no body = where Mate is now). Send Mate home when it's done helping, and before calibrating the cameras.

- **Signs:** forward = `s1` −, `s2` +. Backward = `s1` +, `s2` −. Turn left (anticlockwise from above) = `+, +`. Turn right = `−, −`.
- **Where it is:** Mate doesn't know. The hub does: `GET hub/api/scene` → `mate {x, y, heading}` (heading = the way its face points, degrees anticlockwise from the gantry's +X), from cam 1 seeing the marker on its top. **When cam 1 can't see it** (window glare, the gantry's cable lying over it, the Z bar in the way), the hub keeps where it last saw it plus every move the hub made since, marked `assumed: true`, and drives on that until the camera finds it again. It's kept across hub restarts. Moves you make with Mate's own API (`/step`) aren't counted: after those, the assumed place is wrong until it's seen again.
- **Calibrate it first** (each build differs): drive a known number of half-steps forward and turn in place, measure with `/api/scene` before and after (average a few reads), and write mm per half-step and degrees per half-step (left and right separately) to the notes. This build's numbers are in the notes.
- **Stay on the board.** There's no edge sensor. Keep moves short (one call is at most ~20 cm or ~150°) and check `/api/scene` between them.

## Flipper

- A black plastic knife on a servo on Mate's **right side**, 42 mm from the right wheel's axle at 45° (forward and up). The shaft points out of the side, so the arm swings beside the box: out 73 mm, then bent 90° inward across the whole front of the face.
- **20° is rest**: the arm angles down and the bent part lies on the table in front of the face. **It can't go below 20°**; up is fine. **~65°**: the arm points straight forward and the bent part stands flat, parallel to and centred on the face. ~110° reaches up over the top.
- **Always give the flipper a `speed`, at most ~60% of the max (`speed` ≤ 360).** A jump (no `speed`) or full speed pulls a lot of current and drops Mate's Wi-Fi now and then. The wheels are fine at full speed.
- **Gestures:** use the hub's gestures (below), which keep the flipper at gentle speeds; `speed` up to ~300 is fine for small, quick moves.
- At rest it's down at the table in front of Mate: it can slide under a thin edge there.

## Gestures: how Mate talks

`POST hub/api/mate/gesture {"name": "thumbs_up", "to": "Sam"}`: a reaction face, flipper and wheel moves, and a line in the chat as Mate's ("👍 thumbs up at Sam"). `GET hub/api/mate/gestures` lists them; they're defined in [gestures.json](gestures.json) (edit it to tune them or add more; the hub reads it each time). Returns at once (`wait: true` to block until done); refused while Mate is busy.

| Mood | Gestures |
|---|---|
| Answers | `yes`, `no`, `thumbs_up`, `thumbs_down`, `shrug`, `maybe` |
| Feelings | `celebrate`, `laugh`, `shocked`, `sulk`, `nervous`, `smug`, `love`, `bored`, `angry`, `eye_roll`, `wink` |
| Social | `hello`, `bye`, `point`, `bow`, `suspicious` |
| Game | `thinking`, `your_turn`, `ready`, `peek`, `fold`, `all_in`, `bluff` |
| Helping | `on_it` (asked to do something), `counting` (taking a close look) |
| Recovering | `woke_up` (back from a blackout: x x eyes, a wobble, then blinking awake) |

- **One-offs:** no `name`, and your own `{emoji, text, face, steps}` (same format as gestures.json). Faces are the 24 reactions in [software/mate/faces/reactions/](../software/mate/faces/reactions.png).
- Every gesture **ends where it started** (moves are a few cm, turns come back), with the flipper back at rest (20°) and the eyes back. Give Mate ~5 cm of room around it, and never gesture with a card on Mate or the cup low over it.
- Gestures take ~4–12 s. Turns add up a little (~4° over a dozen gestures): re-square Mate with `/api/mate/goto` before precise work.
- **Aim it:** `to` only names who it's for in the chat. To really face a player, turn Mate first (`/api/mate/goto` with a `heading`, or a turn), then gesture.

## Peeking at your own cards

Your hole cards lie face down, and no camera sees a face-down card's face. Mate peeks for you, the way a player lifts a corner:

1. Mate square to the card's spot, flipper down (20). The crane puts the card face down in front of Mate's face, its long side along Mate's heading, ~130-135 mm ahead of Mate's marker (114, as for flipping, is too close: the camera sees one pip). Drop it from 2 mm.
2. Flipper up **slowly** (`speed=60`) to ~50-60°: the card's near edge lifts toward Mate's camera. At 40° only the middle shows; at 50° the corner index shows (Nov 2: a 5♣, upside down, the flipper blade across the middle).
3. `GET hub/api/see?cam=mate&effort=low&ask=...` and **read the corner index yourself if you can**: Muse misread 5♣ as 6♣ twice from this view (low light, upside down).
4. Flipper back to 20 slowly. The card stays on the flipper; Mate backing up drags it along (Nov 2: 45 mm, turned 15°), so look with cam 1 and pick it where it is, then put it back in its place.
5. Never say your cards out loud.

Holding the card above Mate's camera with the cup instead: at Z 120 it's out of view; at Z 65 about 160 mm in front the whole face shows but too small to read reliably.

## When Mate blacks out

Mate sometimes browns out and restarts, mostly on a flipper move (the servo pulls too much current), and its Wi-Fi drops for ~10-20 s. You'll see a gesture or a move come back with "Mate didn't answer", and then `GET /status` shows a small `uptime_ms` and `reset_reason` (e.g. `power_on`). Play it as part of the show, not as an error:

1. **Cover for it, in character, right away.** Make up an excuse and vary it: "My helper needs a moment. Union rules." / "He's thinking very hard." / "Overwhelmed by the stakes, I'm afraid." Never say brownout, Wi-Fi or reboot to the table.
2. **Wait for it:** `GET /status` every ~2 s until it answers (give it ~30 s; if not, ask the people at the table to check its switch).
3. **When it's back, play `woke_up`** (x x eyes, a wobble, then blinking awake) and say something to close it ("Welcome back." / "There he is."). Its face goes back to the plain eyes on its own.
4. **Then pick up where you were.** Its flipper is wherever it stopped (bring it to 20 slowly), and a move it was making stopped part-way: check `hub/api/scene` for where it is before carrying on.

## Face

- **Default: happy, lively eyes.** Loop `software/mate/faces/eyes.bin` (56 frames at 12 fps: blinks, looks left and right) whenever nothing else is going on. Vary it: random eye moves, a blink at the right moment.
- **Communicate:** gestures show a reaction face for you. For anything else, draw anything 128×64 one-bit (Pillow: `Image.new("1", (128, 64))`, `.tobytes()` is already the right format): text for a player ("Your turn!"), an arrow, a score, a reaction (surprised, laughing, thinking). Play reactions once (`X-Repeat: 1`), then go back to the eyes.
- Be creative: it's the table's face. Faces in [software/mate/faces/](../software/mate/faces/) (`make.py` shows how to draw them).

## Camera

- `GET /capture`: what Mate sees, from ~6 cm up: the cards in front of it, the players' side of the table, people. Turn Mate to look around. ~1 s a photo; don't use the stream (`:81`) from an agent, it slows Mate's Wi-Fi.
- Good for close looks the overhead cameras can't give: reading a card in front of it, looking at a player, how tall something is or how many chips are in a stack (the overhead cameras look down on it and can't tell).

## Looking with Mate

When the cameras above can't tell you something (a stack's height, what's under or behind something, a card's face from the side), send Mate to look:

1. **Say what you're doing, and have Mate show it.** Out loud first, as yourself: "Let me ask my helper to count that." Then `on_it` (Mate nods: no flipper, so it can't brown out on the way). The table should never wonder why Mate is moving.
2. **Drive there:** `POST hub/api/mate/look {x, y, distance}` sends Mate to `distance` mm from (x, y) (its camera to the spot), facing it, from the side it's already on (`side`: degrees, to choose). Cam 1 checks the way first (above) and it refuses with `in_the_way` if anything's on it (the thing it's looking at doesn't count): pick another `side`, go around, or ask. ~15–20 s; `ok`, `off_mm`.
3. **Look:** `counting` while you do. `GET hub/api/find?cam=mate&what=<it>&ask=<question>&effort=low` crops the thing out of Mate's picture and asks Muse Spark about the crop. Or `GET hub/api/see?cam=mate&ask=...` for the whole view.
4. **Say what Mate found** ("Four reds.") and react with a gesture (`thumbs_up`, `shocked`...). Send Mate home when it's done helping.

Tested Nov 2 on a stack of 4 red chips: from home (~300 mm) Muse said "about 3"; at 150 mm, whole picture, 3; at 120 mm with `find` (a crop) and `effort=low`, **4, right**; `minimal` effort still said 3. At 80 mm the stack's bottom was out of the picture (the camera sits ~6 cm up and tilts up a little). So: **~120 mm, crop with find, effort low.**

## Helping the gantry

- **Turning cards** (tested: 6 cards turned and stacked, ~35 s each):
  1. Turn the empty Mate so the card will land **square to it**. A card at ~45° to Mate lands tilted on a corner cap and won't pick back up.
  2. Pick the card off the board; put it on Mate's **turning centre** (in the notes; ~9 mm in front of its marker) at cup Z ≈ 105.5 (just above Mate's plywood top, 103) and drop.
  3. Turn Mate by the angle the card needs (degrees per half-step from the notes). The card turns with it.
  4. Look with cam 1 where the card really is on Mate's top (it drifts 5–15 mm): map the card at board + 103.5 mm, not at the board.
  5. Pick it there: cup to Z ≈ 102 (a gentle squeeze), `grip?pump_s=2`, peel off slowly (F600), lift above travel height, and place it.
- **Flipping cards over** (tested: 14 flips, all flat, either way over; ~4 s plus the place):
  1. Mate square to the card, and the flipper **lowered to rest (20°) first**: a card placed while the hand is up just gets pushed (and run over). The card's long side along Mate's heading.
  2. The crane places the card just in front of Mate's face so its near edge rests on the flipper's bent part (it lies on the table there). This build: card centre ~114 mm ahead of Mate's marker, centred left-right (the notes have the latest).
  3. **At the same time:** flipper to 65° (`speed=60`) and drive forward ~95 mm (wheels at full speed). The near edge lifts, the card stands up, then tips over. ~4 s. It lands flipped ~10 cm further on, turned 3–5° clockwise (from above). Curving Mate during the push doesn't change that.
  4. Back up ~50 mm **before** lowering the flipper (or it comes down on the card), then flipper to 20°.
  5. Look where it landed before picking it. The small turn adds up if you flip the same card again and again (Mate squares to it each time): re-square it once it's ~20° off.
- Keep Mate's turning centre at least ~2 cm inside the cup's board bounds, or a card that drifts on its top can end up out of reach.
- Keep the gantry above travel height (Z 110) over Mate. Never lower onto it.
