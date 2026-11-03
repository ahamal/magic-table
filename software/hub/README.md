# Table hub (Pi 5)

The body API for the whole table. Step 2.

> **How to use it: [agent/](../../agent/README.md)** (served at `/guide`, and as plain text at `GET /api/guide`, `/api/guide/table`, `/api/guide/mate`), then this build's notes at `GET /api/notes`. Limits, the gripper, Mate, and recipes live there, not in the code. Deploy the folder with the hub: `rsync -a agent/ ash@raspberrypi.local:hub/agent/`.

## Responsibilities

- **One web server** (FastAPI): the table body API (see [`docs/architecture.md`](../../docs/architecture.md#body-interface-table)) plus the human table page. WebSocket for events (`wait_for`) and the optional live view.
- **Frame driver:** GRBL over USB serial — homing, soft limits, `move_to`, probe (`G38.2`).
- **Gripper:** GRBL switches the 12V pump (`M8`/`M9`) and vent valve (`M4 S0`/`M3 S0`) through MOSFETs on the CNC Shield. The Pi never touches the 12V side.
- **Sensors:** VL6180X (`sense_z`), touch switch (`probe`).
- **Cameras:** the Pi 5's two CSI cameras (`capture`, `stream`); later named views like `capture("overhead")`.
- **Mate client:** the only caller of Mate's API once the table is assembled; `capture("mate")` and `mate.*` pass through.
- **Safety layer:** soft limits, Z only lowers when clear, the Mate no-go zone (from Mate's marker), e-stop.
- **Calibration:** head-marker grid → pixel-to-gantry mapping, served in `get_table()`.

## Frame server (running now)

[`server.py`](server.py) + [`grbl.py`](grbl.py) + [`gripper.py`](gripper.py) + [`camera.py`](camera.py) + [`static/index.html`](static/index.html): GRBL, the gripper and the cameras over HTTP, and a jog page. The first piece of the hub.

- **One serial connection, kept open.** Opening the port resets the Uno, so the server owns it. Lines go one at a time and wait for `ok`/`error`; real-time bytes (status, hold, resume, reset, jog cancel) skip the queue. Status is polled 5× a second and pushed to every page over a WebSocket.
- **Jog page** at `http://raspberrypi.local:8000/jog` (the home page `/` lists every page), after the Robo Diner jog page (click the XY table and the Z rail to set a target, then go), plus:
  - Live work and machine position, state and homed badges, a STOP button (feed hold, then reset).
  - Jog pad with diagonals and Z: tap for one step (0.1–100 mm), hold to keep moving until release (GRBL `$J` + jog cancel). Arrow keys and PgUp/PgDn do the same; 1–5 pick the step; Esc stops.
  - Zero buttons (`G10 L20 P1`), Home, Unlock, Pause/Resume/Reset, and a console with the GRBL command list and history.
  - Gripper: Pump and Valve switches, Grip and Drop (keys G and D).
  - Live views of every camera under the map, each with a link to a full-size photo. **Cameras** hides them; streams also pause while the tab is in the background.
  - If the last page closes mid-jog, the server cancels the jog.
- **Gripper commands go through GRBL's queue,** so they run after any motion already sent. GRBL doesn't report the valve pin at `S0`, so the hub tracks pump and valve itself; the valve closes itself after 10 s (the coil heats up), and after an unlock or home in case a reset left it open.
- **Cameras:** picamera2 opens every camera the Pi found at boot (now cam 0 = ov5647, cam 1 = imx219 / Camera v2) and keeps them streaming at 1640×1232, the full field of view, so a capture is the next frame, about 0.04 s. Cameras are only detected at boot: plug them in with the Pi off.

| Endpoint | |
|---|---|
| `GET /api/status` | State, `MPos`, `WPos`, `homed` |
| `GET /api/settings` | GRBL `$$` values |
| `POST /api/send {line}` | Any G-code or `$` command; returns GRBL's reply |
| `POST /api/jog {x,y,z,feed}` | Relative jog (`$J=G91 …`) |
| `POST /api/move {x,y,z,feed?}` | Absolute move in work coordinates; no feed = rapid |
| `POST /api/home` | `$H` |
| `POST /api/realtime/{status,hold,resume,reset,jog_cancel}` | Sent immediately |
| `GET /api/gripper` | `{pump, valve}` |
| `GET /api/guide`, `/api/guide/{table,mate}` | the agent guides (repo `agent/`), plain text |
| `POST /api/mate/goto {x, y, heading?, check?}` | drive Mate's turning centre to (x, y) and face `heading`, with the camera checking (~5 mm, ~3°); raises the gantry head first. Wheels at full speed. `check` (default): cam 1 looks at its lane and where it turns first (~1 s, no API call) and refuses with `in_the_way` if anything's on the mat there; `check: false` just goes |
| `POST /api/mate/look {x, y, distance?, side?, check?}` | send Mate to look at a spot with its own camera: `distance` mm (150) from it, facing it, from `side` (degrees) or where it is; then `see`/`find` with `cam=mate`. ~20 s |
| `GET /api/mate/home`, `POST /api/mate/home`, `POST /api/mate/home/set {x?, y?, heading?}` | Mate's home spot: where, go there, save a new one (no body = here) |
| `GET /api/mate/gestures`, `POST /api/mate/gesture {name, to?, wait?}` | Mate's gestures (repo `agent/gestures.json`): a reaction face, flipper and wheel moves that end where they started, and a chat line as Mate's (`by: mate`, `via: gesture`). Or a one-off: `{emoji, text, face, steps}`. Refused while Mate is busy |
| `POST /api/say {text, by?, wait?}` | speak on the table's Bluetooth speaker, and add the line to the chat under `by` (the agent's own name, default `agent`); a `speaking` event goes to the pages. Piper (local neural voice), streamed a sentence at a time; espeak-ng if Piper or the voice file is missing |
| `GET /api/voice`, `POST /api/voice {voice?, speaker?, pace?}` | which voice, speaker (in multi-speaker files) and pace (1 = normal, lower = faster), and the voices installed; kept in `voice.json`. The default is `en_US-norman-medium` at pace 0.85 |
| `GET /api/notes`, `POST /api/notes {text, by}` | this build's notes: what agents and people learned about this particular table. Kept on the Pi (`~/hub/notes.md`), never deployed over or committed |
| `POST /api/gripper/{pump_on,pump_off,valve_on,valve_off,grip,drop,stop}` (grip`?pump_s=N`: pump N s, then hold on vacuum ~20 s) | Runs after queued motion; returns `{pump, valve}`, plus `error` if GRBL refused (e.g. `error:9` in Alarm) |
| `WS /ws/listen` | live speech to text: send 16 kHz mono PCM16 as binary frames while someone talks, then the text `end`; get `{type: "partial", text}` as words are recognised (~0.3 s behind), then `{type: "final", item}` (the chat message) or `{type: "error"}`. The hub relays to Meta's Muse Voice realtime endpoint, biased toward table words. Other pages get `chat_partial` events |
| `POST /api/transcribe` | (fallback, not live) Body: one utterance as a 16/24 kHz mono 16-bit WAV. Returns `{id, at, text, audio_ms, took_ms}`, or `{text: ""}` if nothing was said |
| `GET /api/chat?after=0&wait=0&by=` | The chat, oldest first: `{id, at, by, via, text}`; `by` is `player`, `mate` or an agent's name, `via` is `voice`, `typed`, `speaker` or `gesture`. `after` = only newer; `wait=N` waits up to N s (max 60) for a new one (long-poll, for agents); `by=player` = only people |
| `POST /api/chat {text, by?}` | add a typed message (default `by: player`); spoken lines go through `/api/say`, Mate's through `/api/mate/gesture`, which add their own |
| `DELETE /api/chat` | clear it. (`GET /api/transcripts?since=` is the old name for the chat) |
| `GET /api/cameras` | `[{cam, model, ok, error}]` |
| `GET /api/see?cam=1&ask=&effort=minimal` | The eyes (`eyes.py`), step 1: Muse Spark (`muse-spark-1.3`) names the kinds of things on the board in a fresh picture: `{things: [{name, look, count, find}]}` (`find` = name plus a backup "<colour> object" after `|`). With `ask`, answers that question about the picture instead: `{answer}`. `cam` 0, 1 or `mate`. ~2 s |
| `GET /api/find?what=a|b,c&cam=1&ask=&effort=minimal` | Step 2: where each thing is, in one fresh picture from `cam` (1 default, 0, `mate`), by SAM 3.1; each name's fallbacks after `|` are tried in order. Items: `{id, what, matched, box, outline}`, and from a calibrated camera `board {x, y, w, h, angle, round?}` (`round`: a disc, `w` its diameter), `on_board`, `pick {x, y, clear_mm}` (the footprint centre); plus `answer` with `ask`. `height=true` (cam 1): cam 0 looks at the same moment and each item gets `height_mm` (off by default: on this build cam 0 doesn't line up at board level yet). Known things (cards, decks, poker chips, by name) come placed for their height from that one camera: `board` is where they really stand, plus `height_mm`, `count` (chips in a stack), `fit` and the stretched footprint in `flat` (a fit under 0.85 leaves `board` flat). `diameter=<mm>` does the same for any other upright cylinder (a can, a cup). ~3 s |
| `GET /api/find/check?id=` | After a pick: has item `id` of the last find left its spot? A fresh picture from the same camera compared with find's inside the item's outline: `{gone, changed}` (gone above 0.35). No API call |
| `GET /api/find/shapes?n=` | A find's things (`n`, the last by default) as low-poly models: Muse Spark describes each, from its crop turned lengthwise, as 4–12 solids, body then details (`{height_mm, axis, top, parts: [{shape, from, to, size, side, tall, lift, color}]}`; shapes: box, cylinder, cone, sphere, wedge, ring); the footprint places them. The 3D scene's "Render poly" draws them. ~7 s |
| `GET /api/vision/history?limit=50`, `GET /api/vision/last`, `GET /api/vision/image?n=&cam=1` | Every see, find and check is kept on the Pi (`~/hub/vision/`: `history.jsonl` and each action's pictures, the last 100; not in git), numbered `n`, and broadcast as a `vision` event. History newest first; the last one; an action's picture (`n` left out: the last picture from that camera). Check compares with the last find's saved picture, so it works after a restart |
| `GET /vision` | the vision page: the three steps (see, find, check) on the left; on the right every action (anyone's), one line each, newest first, opening on a click to its parameters, both pictures with outlines, and the results |
| `GET /api/capture?cam=0` | A fresh full-size JPEG from one camera; 404 if there's no such camera |
| `GET /api/stream?cam=0&fps=10` | Live MJPEG view, 820 px wide (~7 fps, ~40 KB a frame); open it in a browser tab or an `<img>` |
| `WS /ws` | `status`, `settings`, `gripper`, `chat`, `chat_cleared`, `speaking`, `scene` and `log` events |

**Voices** (Piper, not in git: ~60 MB each in `~/hub/voices/`):

```bash
cd ~/hub/voices && B=https://huggingface.co/rhasspy/piper-voices/resolve/main
for v in en/en_US/norman/medium/en_US-norman-medium en/en_GB/semaine/medium/en_GB-semaine-medium en/en_GB/alan/medium/en_GB-alan-medium; do
  curl -sLO $B/$v.onnx && curl -sLO $B/$v.onnx.json; done
```

Medium voices make ~5 s of speech in ~1.5 s on the Pi 5; "high" ones (e.g. ryan-high) take ~9 s, too slow.


**Run it on the Pi:**

```bash
rsync -a --exclude .venv --exclude __pycache__ --exclude certs --exclude .env --exclude chat.jsonl --exclude voices --exclude voice.json --exclude vision \
  software/hub/ ash@raspberrypi.local:hub/
rsync -a agent/ ash@raspberrypi.local:hub/agent/                 # the guides and Mate's gestures
rsync -a --include '*/' --include '*.bin' --exclude '*' software/mate/faces/ ash@raspberrypi.local:hub/faces/   # Mate's faces
ssh ash@raspberrypi.local
cd ~/hub && python3 -m venv --system-site-packages .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python serve.py      # HTTP and HTTPS, both on :8000
```

**First time only, on the Pi:**

```bash
# Meta Model API key, for speech-to-text. Private to the Pi; never commit it.
umask 077; echo "MODEL_API_KEY=<your key>" > ~/hub/.env
# self-signed certificate for HTTPS on :8000 (phones only allow the mic on HTTPS)
mkdir -p ~/hub/certs && cd ~/hub/certs && openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
  -keyout hub.key -out hub.crt -subj "/CN=raspberrypi.local" \
  -addext "subjectAltName=DNS:raspberrypi.local,IP:192.168.1.99"
```

Set `GRBL_PORT` if the Uno isn't `/dev/ttyACM0`. Nothing else may hold the port, or the camera, while the server runs. `--system-site-packages` lets the venv import picamera2, which comes with Raspberry Pi OS.

**On the Pi it runs as a service** ([`hub.service`](hub.service)) and starts on boot:

```bash
sudo cp ~/hub/hub.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now hub
sudo systemctl restart hub     # after copying new code
journalctl -u hub -f           # logs
```

Stop it (`sudo systemctl stop hub`) before running anything else that opens the serial port, such as a test script.

## Vision and the 3D page

**Find checks SAM's matches.** SAM is fussy and sometimes names the machine: the suction cup as a plate, a wheel as a knife. So Muse Spark sees SAM's matches numbered on the whole picture, with the robot outlined, and keeps only the loose things that fit the first name (a fallback like "white object" must still be the plate). The robot's outlines aren't segmented: they're boxes around the cup, the head's Z extrusion and Mate, where the hub tracks them now, projected into the picture (no API call). A match at least 60% inside them is dropped unless Muse keeps it (a card lying on Mate). If Muse can't answer, that rule alone decides; the check never fails a find. Each item says `robot: {inside, near}`; near the robot it still gets its pick point. Only matches touching or near the robot are checked when SAM found them by the first name (a fallback like "white object" has all its matches checked): Muse took ~25 s over a dozen cards, so a find of cards in the open is ~6 s, ~12 s reading them. The vision page draws the robot boxes dashed.

[`vision.py`](vision.py): where things are, from the cameras, with OpenCV only (no cloud AI). The gantry is the reference: calibration moves the head marker (ArUco ID 10) over a grid at three heights and fits each camera's 3D projection in gantry coordinates (X/Y mm, Z GRBL units, Z+ up). Twice a second it then finds the head (and checks it against GRBL, in mm), Mate (ID 20: position, heading, height), cards on the dark board (center, angle, face up/down) and the board markers (IDs 0–3; if they move in the picture, `camera_moved_px` warns; nothing is corrected automatically, since a moved board looks the same as a moved camera). Marker sizes and offsets are constants at the top.

**Page:** `http://raspberrypi.local:8000/scene`, a live three.js view: board, head and cup, Mate, cards, the cup's bounds, and each camera module posed from its calibration with its picture's footprint on the board; buttons for Calibrate, Zero Z, Re-anchor, Travel height = here.

**Order of use:**
1. Z at its **top** over the middle of the board, Mate not under the 120 mm square around it, GRBL unlocked.
2. **Calibrate** asks how far the cup is above the board (mm), then goes down from there in three passes, never closer than 15 mm. Any reset, pause, alarm or STOP aborts it with no further moves. The start height becomes the **travel height**.
3. Lower the cup until it just touches the board, press **Zero Z**: Z becomes 0 there (G10), so Z is the cup's height above the board. The same button fixes a Z that skipped steps (a lift that stalled): touch the board, press it, raise the cup.
4. After any GRBL reset (or hub restart), unlock, then **Re-anchor**: if the camera agrees with the last saved position (within 3 mm) that position is restored exactly; if it disagrees, X/Y come from the camera and Z from the saved value; if no camera sees the head, the saved position is used (right as long as nobody moved the head by hand). Don't use Work zero on the jog page; it shifts every position.

**The cup isn't under the head marker:** the marker is on the Z extrusion's left face (facing −X); the cup is ~20 mm from the marker's centre in −Y, in line with the extrusion (`TIP_OFFSET` = (−2.4, −19.7): where it lands, measured over chips; the X absorbs some vision error). Head positions (GRBL, `/api/move`) are the marker's; use `/api/tip` to put the cup somewhere. Tested: cup within ~2–3 mm of a card center 110 mm from the calibration grid's center.

**Z limits:** work Z is the cup's height above the board. Moves and `/api/tip` outside −1 to 150 are refused; Z jogs are shortened to stop at them (150 is the top of the Z travel; −1 is the 1 mm squeeze a grip needs). `/api/send` isn't checked.

**Mate rule:** bumping Mate sideways by accident is survivable; pressing down into it isn't. Travel height is 110 (the cup clears Mate's 105 mm caps). Below it, `/api/move` and `/api/tip` go up to travel height before crossing Mate and refuse to end over it; `/api/jog` may go sideways anywhere but won't lower the cup onto Mate. Checks use the cup's position, over Mate's 134 mm footprint plus 40 mm. (`/api/send` is raw G-code and isn't checked.)

| Endpoint | |
|---|---|
| `POST /api/calibrate {room, span=60, steps=3, levels=3, feed=2000}` | Grid of stops at three heights. With bounds set: centred on the board (rises to the travel height and goes there first), refused before any move if the cup would leave the bounds or Mate is under it. `room` = mm between cup and board at the start (left out once the board's been touched: Z). Sideways at 3000 mm/min |
| `POST /api/calibrate/stop` | Ends a calibration after the current move; GRBL keeps its position |
| `GET /api/calibration` | calibrated, per-camera fit, `table_z`, `travel_z`, `needs_reanchor`, head check |
| `POST /api/calibration/table` | the cup is touching the board now |
| `POST /api/calibration/travel {z?}` | set the travel height (cup height safe over Mate); no `z` = the current Z |
| `POST /api/calibration/bounds` | measure the board markers, save the cup's allowed X/Y (inside their inner edges), re-centre 0, 0 on it |
| `POST /api/calibration/reanchor?camera=false` | after a reset: the saved position (or X/Y from the cameras with `camera=true`: triangulated from both, Z kept). Until then `/api/move`, `/api/tip`, `/api/jog` and `/api/mate/goto` refuse (a reset loses the position the limits rely on). A reset counts when GRBL's banner arrives, or when GRBL is found in alarm on connecting (a Pi boot resets the Uno before the hub listens) |
| `POST /api/tip {x, y, z?, feed?}` | put the **cup tip** at board X/Y (and Z mm above the board); same Mate rule as `/api/move` |
| `GET /api/scene?fresh=false` | head (and cup tip), Mate, cards (face-up ones named: `card`, `score`, `by`, from the card cache), `chips` (`[{x, y, height_mm, count, colour, fit}]`), `decks` (`[{x, y, angle, height_mm, cards, fit}]`), board, cameras; also the `scene` WebSocket event. All from cam 1 on the Pi, no API: chips by colour and decks by brightness, each fitted with its known shape (`chips.py`) |
| `GET /api/cards?effort=minimal` | The face-up cards, named: the card cache (`cards/` on the Pi, not in git) in a few ms, or Muse Spark from the card's flattened face (~1–3 s), cached when it's sure (confidence ≥ 0.9). The hub also does this on its own for a face-up card it can't name that lies still (`cards.py`). `DELETE /api/cards` empties the cache (a new deck) |

## Talk page

`https://raspberrypi.local:8000/talk` (or `https://192.168.1.99:8000/talk` on phones that don't resolve `.local`): instructions by voice, from any phone or laptop on the Wi-Fi.

- **Tap the button, talk, tap again.** The page streams the mic to the hub (`/ws/listen`), which relays it to Meta's **Muse Voice Transcribe** realtime endpoint (push-to-talk mode, biased toward table words like "Mate", "call", "raise", "flop"). Your words appear in your bubble as you speak, about 0.3 s behind, on every open page; the final text arrives ~0.1 s after you stop. If the live connection fails, the page falls back to sending the whole recording.
- **It's a chat:** people talk (tap, speak, tap) or type; the agent's spoken lines appear too (labelled with its name), and Mate's gestures as small stage directions ("Mate 👍 thumbs up"). Every page sees every message live, so several phones and the agent share one conversation, kept in `~/hub/chat.jsonl` (not in git) until cleared.
- **The certificate is self-signed:** each device shows a warning once; accept it ("visit this website" / "proceed"). The plain-HTTP page shows transcripts but can't use the mic, and links to the HTTPS one.
- The agent follows the conversation with `GET /api/chat?after=<last id>&wait=30` in a loop (or the `chat` WebSocket events), and answers with `/api/say` (and Mate's gestures).

## Config

A table config file (no game knowledge): size, reach, named spots, named actuators, camera settings, calibration.
