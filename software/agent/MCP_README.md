# Magic Table MCP integration (via the Pi hub)

One MCP server, on the Raspberry Pi, wrapping the hub. Esper is controlled
only through the hub -- there is no separate Esper MCP server, and no
direct `esper.local` tool. That is the architecture rule in
docs/architecture.md ("Only the hub calls Esper once the table is assembled")
and it keeps the safety layer between the model and the hardware.

Files in software/agent/:
- mcp_server.py -- stdlib-only MCP server over stdio, 28 tools. Run on the Pi: `python3 mcp_server.py` (hub at http://localhost:8000). MAGIC_TABLE_HUB_URL overrides it. --list-tools prints tools without a hub.
- agent_runner.py -- minimal Muse Spark loop over that MCP server. Needs MODEL_API_KEY (Pi only, already in ~/hub/.env for STT) and openai (already in hub requirements).
- test_mcp.py -- smoke test against a mock hub, no Pi/robot. Run: `python3 test_mcp.py`.
- mcp_config.example.json -- example stdio MCP client config.

## Deploy to the Pi

```bash
rsync -a software/agent/ ash@raspberrypi.local:hub/mcp/   # not hub/agent/: that's the guides, and README.md would collide
ssh ash@raspberrypi.local
cd ~/hub && python3 mcp/mcp_server.py --list-tools | head
python3 mcp/test_mcp.py
```

Then, human watching, STOP in reach:

```bash
export MODEL_API_KEY=$(grep MODEL_API_KEY ~/hub/.env | cut -d= -f2)
python3 mcp/agent_runner.py --instruction "Deal a Texas hold'em hand for two players, then run the flop."
# no confirmation prompt: the hub's limits apply to every move; keep STOP (jog page) in reach.
```

## What is NOT exposed, on purpose

send_gcode / raw G-code, homing ($H), direct Esper /step / /servo / /screen,
GRBL settings, full recalibration, delete_chat. All would bypass board bounds,
Z limits, travel height, Esper no-go zone, or Esper pose tracking. The MCP
server refuses them before any hub call.

- **No homing:** this build has no limit switches; `$H` would drive the axes
  into the frame looking for them. After a reset or alarm: `unlock` (sends
  exactly `$X`, nothing else), then `reanchor`.
- **Esper's flipper and wheels** go through the hub's `/api/esper/move`
  (`esper_move`): a servo speed is required and capped at 360, drives are at
  most 200 mm, and the hub counts the move into Esper's assumed place, which
  Esper's own `/step` doesn't. That's what the flip and the peek use.
- **Card picks:** the hub allows Z down to -2 (the recipes pick at -1.5, -2
  for a stubborn card), with straight up/down moves at a feed through
  `move_head` (z only).
- **No diagonals:** `move_tip` with a z rises to the travel height if it's
  lower, crosses, then goes straight down (`direct=true` for a nudge of a few
  mm at the current height).
- **chat_post** posts under the agent's own name; it refuses `player` and
  `esper`, so the agent can't read its own notes back as players' words.

## Transcript: keep it, poll it, do not build a second subscription

Verdict: do not drop the transcript. Do not build a WebSocket subscription
for v1. chat_poll IS the subscription.

How it works: players talk on the talk page (https://raspberrypi.local:8000/talk,
any phone). The page streams mic to the hub (/ws/listen), the hub relays to
Muse Voice Transcribe realtime (muse-voice-transcribe-1.0, keyword-biased to
Esper, fold, check, call, raise, flop...), pages show partials ~0.3 s behind,
final text lands in chat ~0.1 s after they stop. The chat (talk.py, ~/hub/chat.jsonl,
not in git) is one ordered log: player voice/typed lines, agent spoken lines
(via /api/say), Esper gestures (via /api/esper/gesture). The agent subscribes by
long-polling GET /api/chat?after=<id>&wait=30 (max 60 s); hub returns as soon
as something new arrives. Tested: answered ~2 s after a message.

Why polling beats WebSocket for MCP: MCP tools are request/response over stdio.
A WS subscription would need a background bridge, reconnect, buffering -- a
second system to debug before submission, for no game benefit. Polling gives
final transcripts only. Pages also get chat_partial events on /ws, but partials
are not in chat.jsonl and must not drive game decisions ("I'll call" once came
out as "alcohol" without keyword biasing). Token cost is bounded: pass the
highest chat id you have seen, not after=0 every time. An empty poll is not
the end of the game -- keep polling while waiting for players.

How Muse contributes (do not mix them up):
- say -- spoken on Pi speaker (Piper, local) AND a chat line under the agent's
  own name (by="Muse"). Hub rejects by="player" and by="esper".
- chat_post -- typed only, no speech. Silent notes, not announcements.
- esper_gesture -- a chat line as Esper, plus face/flipper/wheels. Esper never speaks.

## Should Muse run on the Pi later? Yes.

Hub at localhost:8000, no mDNS, no Wi-Fi flakiness, no self-signed cert dance
(phones need HTTPS for mic; a localhost agent does not). MODEL_API_KEY already
lives in ~/hub/.env on the Pi for STT; the runner reuses it, no key on a laptop,
no key in git. Latency: scene is local OpenCV, chat_poll is local, only Muse
Spark / SAM / Voice calls go to Meta's cloud -- exactly as hub already does in
eyes.py and talk.py. The agent does NOT need its own mic or STT: player voice
already arrives as final chat items through the hub. Later, if you want direct
voice (no phones), hub already has /ws/listen realtime and one-shot
/api/transcribe -- that is v2, not a prerequisite.

Later latency option (not v1): a single WS client inside the MCP server staying
connected to /ws, caching latest chat/speaking/scene events, with chat_poll
reading from that cache. Do not let the model see partials, and do not let two
subscriptions diverge -- one source of truth, the hub's final chat list.

## SAM / Muse Spark audit (Nov 3) -- summary

Yes, on point, tiered and cost-aware. Tiers, cheapest first:
1. No cloud -- get_scene (OpenCV/ArUco/geometry), free, ~0.5 s. Limits: touching
   cards merge/vanish, deck +/-3, chip counts +/-1 near x.5. Keep your own state.
2. see -- Muse Spark whole picture, ~2 s, names kinds + counts + fallback
   "<colour> object". Default effort minimal validated: same card answers in
   0.5-2 s vs ~15 s / 2,100 reasoning tokens at default effort.
3. find -- SAM 3.1 segmentation, ~3-6 s. SAM has no confidence scores and is fussy
   about names ("king of spades" finds nothing, "face card" finds every card).
   So see's fallbacks are tried in order, and Muse Spark verifies numbered
   outlines (first 12 only) against the first name, dropping robot parts (cup as
   plate, wheel as knife). Matches >60% inside tracked robot boxes are dropped
   unless Muse keeps them (a card on Esper). If Muse cannot answer, robot rule alone decides.
4. ask per item -- Muse Spark on crops, ~1 s each at minimal, up to 24, parallel.
5. Cards -- cache first (ms, score>=0.75 margin>=0.08, 4 faces/card), Muse only for
   unknowns, cached only at confidence >= 0.9. Face-down never named here.
6. Shapes -- Muse Spark low-poly, demo garnish only, never for picking.
7. Esper camera -- 640x480 GC0308, ~1 s, pixels only. Weak for card reading (Nov 3:
   five holds gave 9♦/5♦/3♦ for a 5♦, confidence 0.65-0.85 misleading). Correct
   escalation is the flipper peek (poker.md), never pick from Esper pixels.
8. Voice -- Muse Voice Transcribe for STT, Piper locally for TTS. Meta API has
   STT but no TTS, so this split is correct. Keyword biasing is essential.

Effort: minimal is right default for board pictures, wrong if blindly applied to
Esper close-ups. Guides get this right: Esper counts/peeks use high (low/minimal
miscounted a 4-stack as 3), board work uses minimal. MCP tools expose effort.

Gaps to mind in demo: park the head before see/find (Z bar hides items, no warning);
verify caps at 12 matches; Muse confidence is self-reported, not calibrated (0.8 has
been wrong -- require two agreeing reads or ask people if <~0.7 or sources disagree);
cam 0 height is off by default (~18 mm board-level error, Nov 2) -- known-thing fits
from cam 1 alone (white chips 3.20n-1.83, red 3.45n-1.83, SAM outlines 3.38n-1.38)
are the working path; dark things/glare/cable can hide Esper -- re-read Esper from
scene three times after it stops before precise Esper work; pictures go to cloud on
every see/find, history keeps last 100 actions' pictures on Pi only (not in git).
