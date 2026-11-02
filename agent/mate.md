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
- **Home:** `POST hub/api/mate/home` parks Mate at its home spot: the middle of the left margin, in line with the left board markers, facing into the board. `GET hub/api/mate/home` says where that is; `POST hub/api/mate/home/set` saves a new one (no body = where Mate is now). Send Mate home when it's done helping, and before calibrating the cameras.

- **Signs:** forward = `s1` −, `s2` +. Backward = `s1` +, `s2` −. Turn left (anticlockwise from above) = `+, +`. Turn right = `−, −`.
- **Where it is:** Mate doesn't know. The hub's camera does: `GET hub/api/scene` → `mate {x, y, heading}` (heading = the way its face points, degrees anticlockwise from the gantry's +X). Its marker is on the top, so it needs to be in cam 1's view.
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

- **One-offs:** no `name`, and your own `{emoji, text, face, steps}` (same format as gestures.json). Faces are the 24 reactions in [software/mate/faces/reactions/](../software/mate/faces/reactions.png).
- Every gesture **ends where it started** (moves are a few cm, turns come back), with the flipper back at rest (20°) and the eyes back. Give Mate ~5 cm of room around it, and never gesture with a card on Mate or the cup low over it.
- Gestures take ~4–12 s. Turns add up a little (~4° over a dozen gestures): re-square Mate with `/api/mate/goto` before precise work.
- **Aim it:** `to` only names who it's for in the chat. To really face a player, turn Mate first (`/api/mate/goto` with a `heading`, or a turn), then gesture.

## Face

- **Default: happy, lively eyes.** Loop `software/mate/faces/eyes.bin` (56 frames at 12 fps: blinks, looks left and right) whenever nothing else is going on. Vary it: random eye moves, a blink at the right moment.
- **Communicate:** gestures show a reaction face for you. For anything else, draw anything 128×64 one-bit (Pillow: `Image.new("1", (128, 64))`, `.tobytes()` is already the right format): text for a player ("Your turn!"), an arrow, a score, a reaction (surprised, laughing, thinking). Play reactions once (`X-Repeat: 1`), then go back to the eyes.
- Be creative: it's the table's face. Faces in [software/mate/faces/](../software/mate/faces/) (`make.py` shows how to draw them).

## Camera

- `GET /capture`: what Mate sees, from ~6 cm up: the cards in front of it, the players' side of the table, people. Turn Mate to look around. ~1 s a photo; don't use the stream (`:81`) from an agent, it slows Mate's Wi-Fi.
- Good for close looks the overhead cameras can't give: reading a card in front of it, looking at a player.

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
