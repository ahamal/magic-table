# The Desk Duo — Three-Minute Shooting Script
## Magic Table — 2026 Meta Global AI Developer Hackathon entry, by Ashwin

Runtime target: 3:00 exactly. Film order is not edit order.
Film the poker hand first, in one wide iPhone shot with live sound. That gives you Muse's actual decision, your genuine reaction, and a truthful spine for the edit. Then move the phone for close-ups of the hardware, the rotation, and the rescue. Use Esper's onboard camera for the private peek.

Cast: Crane — the gantry / suction-cup robot, he/his. Esper — the small wheeled companion robot (formerly called Mate in code and guides), she/her. Internal code and hub endpoints stay /api/mate/* for now; Esper is the demo character name.

Rules for the edit: Keep Muse's real decision, your real reaction, and the real Talk-page transcript. If Muse folds, keep the fold. Do not re-record Muse's voice, do not fake a transcript, do not fake a peek. Cut long travel, never cut the moment a decision lands. Caption Muse's spoken lines. Caption staged recovery as "Recovery demonstration".

## Edit order

### 0:00–1:12 · Meet the Desk Duo

- 0:00–0:06 — First frame: suction cup already descending. It picks something up, carries it a short distance, sets it down. Close enough to see the cup compress. You: "This is Crane. His job is to lift things up and put them down." Let the release make its little sound.
- 0:06–0:12 — Cut to Esper at eye level. She looks toward you and waves the plastic arm. Title THE DESK DUO appears over the two robots. You: "This is Esper. Her job is to be cute and personable." Give her a moment to finish waving.
- 0:12–0:24 — Three tight shots: belt traveling, aluminum frame, gripper making contact. Show pump or solenoid as we hear it work. You: "Crane started as my hobby CNC gantry. Aluminum, timing belts, some hacked-up metal. A vacuum pump and a solenoid run the suction gripper."
- 0:24–0:32 — Esper's wheels turn. Cut to arm in profile so audience can see exactly what it is. You: "Esper runs on cheap stepper motors. And yes, her arm is a bent plastic knife."
- 0:32–0:51 — From above, Crane picks up a visibly crooked card and puts it on Esper's head. Esper turns. Crane takes the card back and places it square against a row of cards. Keep handoff in one shot. You: "Crane can put this card almost anywhere on the table. But he can't turn his wrist." Let Esper rotate in silence. Once card lands straight: "That's also Esper's job."
- 0:51–1:06 — Follow one red chip through four views: real chip, Pi camera frame, SAM's outline, then Crane picking it up. Keep chip in roughly same part of screen across cuts. You: "Here's what they see. The cameras feed the Raspberry Pi. Meta's SAM finds the chip in the image. The board markers help turn that into a spot Crane can reach."
- 1:06–1:12 — Widen. You're sitting across from robots with cards in front of you. A few chips already in pot. You: "For this hackathon, I wanted to see whether Muse could use both of them to play a hand against me."

Production notes: Straighten shot is the tested recipe — place on Esper's marker at Z 110, down to Z 104.2, turn Esper, pick at Z 101.5 — only when angle error is over ~10°. Chip/SAM shot: record Pi vision page / find output as screen capture at same time as real chip shot, so views match. SAM is Meta SAM 3.1 via hub find.

### 1:12–2:15 · Play the hand

Start at the turn with four community cards visible. Viewer only needs to understand you're betting and Muse has a decision to make.

- 1:12–1:17 — You look at Esper. She does her excited gesture. You, to Esper: "Now, let's play poker."
- 1:17–1:23 — Your hand slides a red chip into pot. Briefly show finalized Talk-page transcript over footage. You, through Talk page: "I bet five." Keep chip hitting mat.
- 1:23–1:29 — Both robots and Muse's face-down cards in frame. Crane starts toward a card. When Muse requests peek, small caption: "Muse asks for a private look." Table sound. Let audience notice Crane moving in response to bet.
- 1:29–1:43 — Crane delivers card to Esper. Cut past long travel, then hold from moment cup lets go through moment Esper's knife lifts corner. No narration. We've met the knife. Let us see it work.
- 1:43–1:48 — Cut to actual card face from Esper's camera, labeled "Esper's view." Then cut to you waiting across table. A beat of quiet. Audience now knows something human opponent doesn't.
- 1:48–1:56 — Stay on your face for first words of Muse's decision. If Muse calls, cut to Crane moving matching chip. Muse's actual response, through table speaker. Caption it. Keep genuine reaction.
- 1:56–2:06 — If hand continues, shoot river flip from table height. Crane feeds card to Esper. Her flipper lifts it, it tips past vertical, lands face up. Let card slap mat. Small "River" caption is enough.
- 2:06–2:15 — Cut forward to real showdown. Show winning cards, then Esper raking pot toward winner. Use real winner announcement. Let scrape of chips carry you into next scene.

Branches: If Muse folds, keep the fold. Esper pushing your chips toward you after a careful private peek is a good poker ending. You can use a river flip from another hand as separate teamwork shot earlier. Most important exchange to preserve is your bet, private look, and Muse's real decision. Peek camera must be actual onboard frame from that peek, not a re-staged close-up.

### 2:15–3:00 · The question, the sign-off, the nephew

- 2:15–2:24 — Wide shot after hand. Cards and chips still scattered. Both robots visible. You, voiceover: "Playing poker got me thinking about what I'd actually want a robot in my house to look like."
- 2:24–2:38 — Esper is stuck. Frame rescue from low enough we'll see daylight under her wheels. Crane lowers cup and lifts her. If you set this up for camera, caption it "Recovery demonstration." You: "Would I want one big humanoid that could do everything? Or would I want a little crew that could help each other out?" Time "help each other out" to lift. Hold long enough to let it land.
- 2:38–2:50 — You at table, both robots beside you. Look into lens. Leave shot still. You: "My name is Ashwin, and the Magic Table is my entry for the 2026 Meta Global AI Developer Hackathon."
- 2:50–3:00 — Brief cut to black. Come back on a SHRUNK, small inset glimpse of the existing wave clip — B-roll only. Your nephew goes closer to Esper and waves at her, and Esper's picture/face waves back at him. An emoji covers your nephew's face throughout the inset. No drawing, no picture-taking sequence. No narration. Let the wave exchange carry it. End on Esper being personable, not on a close-up reaction.

Production notes: Rescue lift is NOT a documented tested recipe in the repo — test it before filming, caption it as staged, keep lift low/short, hand ready to catch Esper. Nephew ending, CORRECTED: this is NOT a drawing. The clip is your nephew going closer to Esper and waving at her, and Esper's picture/face waving back at him. Use only a shrunk, small inset glimpse of that wave exchange (roughly a third of frame, in a corner), with an emoji covering your nephew's face for the whole inset — track it to his face as he moves closer, keep it over the face only so his wave and Esper waving back stay visible. Drop the "It just drew you." / "That doesn't even look like me." lines — they belonged to the incorrect drawing description. Emoji + shrunk inset together mean his face is not identifiable in the film; a quick check with his parent is still good practice before submitting.

## Shoot order

1. Poker hand, wide iPhone, live sound — first. Start at turn, four community cards, pot started. Phone locked off wide for both robots, Muse's cards, and you. Talk page open for "I bet five." Muse runner via MCP on Pi, or hub page if runner not live — decide before rolling, do not switch mid-hand. Keep rolling through decision, even if fold.
2. Close-ups, second. Cup compressing, belt, frame, gripper + pump/solenoid sound, Esper wheels, knife arm in profile, straighten handoff in one overhead shot, red chip in four views.
3. Rescue, third. Low camera, daylight under wheels, Crane lift, caption "Recovery demonstration." Test lift off-camera first.
4. Intro / sign-off, last. Title shot with Esper waving, 1:06–1:12 setup line, still 2:38–2:50 sign-off to lens.
5. Nephew, only if footage exists.

## On-set checklist

- iPhone wide locked, live sound on. Table speaker, chip hits, cup release are part of film.
- Table: pot started, four community cards at turn, Muse cards face-down in frame, red chips ready for bet and call.
- Esper: charged, flipper free, camera clean, home spot known. Park Crane head before any see/find shot — Z bar hides board items.
- Pi/hub: hub running, Talk page open, Muse Voice Transcribe working, screen capture ready for Pi camera + SAM outline.
- Captions, verbatim: "Muse asks for a private look." / "Esper's view." / "River" / "Recovery demonstration." / Muse's spoken decision, word-for-word.
- Safety: human watching, STOP in reach, travel height 110 over Esper, never lower first and cross at slant. After any reset, reanchor before moving again.

## Edit checklist

- Total 3:00 or under (2:50 without nephew beat is acceptable)
- First frame is cup descending, not title card or setup
- Muse decision is real, unreplaced audio, captioned
- Bet → private look → decision intact, in order, even if Muse folds
- SAM chip shot uses same chip, same hand, same position across four views
- Rescue captioned "Recovery demonstration" if staged
- Nephew beat is a shrunk inset glimpse only — nephew waves at Esper, Esper waves back, emoji covers nephew's face throughout, no drawing sequence
- Final line names Ashwin and 2026 Meta Global AI Developer Hackathon, Magic Table as entry name
