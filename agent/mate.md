# Mate guide

Mate is a small wooden robot on the board: two wheels, a flipper arm, a face screen and a camera, on its own Wi-Fi API at `http://mate.local`. It's the table's human communicator. The full API reference (every endpoint, field and error) is [software/mate/README.md](../software/mate/README.md); this page is how to use it. Served at `GET /api/guide/mate`.

## Calls you'll use

| Call | What |
|---|---|
| `GET /info` | Limits, screen size, camera. Once at start. |
| `GET /status` | `busy`, the last move (`last.d1/d2`, `result`), flipper angle (`servo_now`), screen, `boots`. |
| `POST /step?s1=&s2=&speed=800&accel=1000` | Move both wheels (half-steps, ±4096 max per call). Returns at once; poll `/status` until `busy` is false. Use the max `speed=800` and `accel=1000`: it's slow otherwise. |
| `POST /stop` | Stop the wheels now. |
| `POST /servo?angle=&speed=` | The flipper (degrees). |
| `POST /screen` | Show frames on the face (128×64, 1 bit/pixel, 1024 bytes a frame, up to 64 frames, `X-FPS`, `X-Repeat`). |
| `GET /capture` | A 640×480 JPEG from Mate's camera, ~1 s. |

## Driving

- **Signs:** forward = `s1` −, `s2` +. Backward = `s1` +, `s2` −. Turn left (anticlockwise from above) = `+, +`. Turn right = `−, −`.
- **Where it is:** Mate doesn't know. The hub's camera does: `GET hub/api/scene` → `mate {x, y, heading}` (heading = the way its face points, degrees anticlockwise from the gantry's +X). Its marker is on the top, so it needs to be in cam 1's view.
- **Calibrate it first** (each build differs): drive a known number of half-steps forward and turn in place, measure with `/api/scene` before and after (average a few reads), and write mm per half-step and degrees per half-step (left and right separately) to the notes. This build's numbers are in the notes.
- **Stay on the board.** There's no edge sensor. Keep moves short (one call is at most ~20 cm or ~150°) and check `/api/scene` between them.

## Flipper

- A bent black plastic knife on a servo on Mate's **right side**, just ahead of the right wheel. It sweeps beside that wheel.
- **20° is rest** (down at the table). **It can't go below 20°**; up is fine. ~60° lies back over the wheel; ~110° reaches up and over the top.
- **Gestures:** wave = up to ~80°, then swing 60↔110 a few times fast (`speed=600`), back to 20 at `speed=300`. Salute = sweep to ~110 and hold a moment, back down. A slow sweep reads as a shrug or a "hmm".
- At rest it's down at the table beside Mate: it can slide under a thin edge there.

## Face

- **Default: happy, lively eyes.** Loop `software/mate/faces/eyes.bin` (56 frames at 12 fps: blinks, looks left and right) whenever nothing else is going on. Vary it: random eye moves, a blink at the right moment.
- **Communicate:** draw anything 128×64 one-bit (Pillow: `Image.new("1", (128, 64))`, `.tobytes()` is already the right format): text for a player ("Your turn!"), an arrow, a score, a reaction (surprised, laughing, thinking). Play reactions once (`X-Repeat: 1`), then go back to the eyes.
- Be creative: it's the table's face. Faces in [software/mate/faces/](../software/mate/faces/) (`make.py` shows how to draw them).

## Camera

- `GET /capture`: what Mate sees, from ~6 cm up: the cards in front of it, the players' side of the table, people. Turn Mate to look around. ~1 s a photo; don't use the stream (`:81`) from an agent, it slows Mate's Wi-Fi.
- Good for close looks the overhead cameras can't give: reading a card in front of it, looking at a player.

## Helping the gantry

- **Turning cards:** the gantry puts a card on Mate's top, Mate turns in place, the gantry picks it up again at the new angle. While a card covers Mate's marker, the camera can't see Mate's heading: turn by the calibrated degrees per half-step, then check the card's angle once it's back on the board.
- Keep the gantry above travel height (Z 110) over Mate. Never lower onto it.
