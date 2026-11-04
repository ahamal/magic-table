# Poker guide

How to run a hand of Texas hold'em at the Magic Table: what's poker-only lives here; the tools it uses are generic and in [table](table.md) and [esper](esper.md). Served at `GET /api/guide/poker`. Read the [README](README.md), table and esper first.

## The pieces

| | Size | Find it with |
|---|---|---|
| Card | 63 × 88 mm, ~0.3 mm thick | `what=playing card`, `ask=Which card is this? Answer like K♠, or face down.` |
| Deck | 63 × 88 mm, a full deck ~16 mm tall | `what=deck of cards` |
| Chip | **40 mm across, 3.3 mm thick**; red 5s, white 1s | `what=red poker chip\|red object,white poker chip\|white object` |

Park the head before every look (the notes say where): the Z bar hides chips behind it.

## Looking: fastest first

You know what's on a poker table, so never start with `/api/see` (Muse naming things, 5-7 s):

1. **`/api/scene`, free, every half-second.** Cards (face-up ones named from the card cache), chip stacks (`count`, `count_raw`, `sure`, `pick_z`, `place_z`, `colour`) and decks. Most of a hand needs nothing else.
2. **In doubt, `find` with the names above, straight away** (SAM, ~2-4 s): a stack that's `sure: false`, one that's missing (stacks touching, or next to Esper or the crane), a card the scene doesn't show (overlapping cards), or before a pick that matters. Ask only for what you're unsure of, one name a call (`what=white poker chip|white object`): fewer names, fewer things found, faster.
3. **Still unsure:** Esper's high-effort count (below), or ask the people.

## The camera makes mistakes: keep your own count

What you see is a good guess, not the truth. **Keep your own record of the game** (what you dealt and where, each player's chips, what you moved into the pot) and use the scene to check it, not to replace it. **When cards seem strange** (one missing, a deck you didn't put there, a wrong face, cards touching), **check with SAM**: park the head, then `find?what=playing card|white object` (add `ask=` to read them); it's slower but a second opinion. When they disagree, look again with `find` for just that thing, then ask the people ("Is that one card or a few?"). Never act on one surprising reading. Mistakes seen so far:

- **A single card read as a small deck** (Nov 3: the card at the far left came out "deck ~10", 5.2 mm, just past the 5 mm a deck needs; curled cards and the board's edges do this). A deck you didn't put there is a card.
- **A deck of fewer than ~10 cards read as a card.**
- **Deck size is ±3 cards**: use it for "about how many are left", never to deal by.
- **A stack ±1 chip** when `count_raw` is near x.5 (`sure: false`), and more often near cam 1 (front left) and at the board's edges.
- **Things vanish**: touching stacks, face-up cards touching each other (face-down ones are found by their backs), anything under the crane or Esper or a hand. Park the head and keep hands off before looking.
- **Glare** (a lamp reflecting off the mat) can hide cards or join them up.
- **A new face-up card** has no name for a second or two, until Muse reads it.

## Chips: where and how many, from cam 1

`find` knows a chip is 40 × 3.3 mm and a deck 63 × 88: each stack and the deck come back with `board` where they really stand, `height_mm`, and for a stack **`count`**, the number of chips (it assumes they're stacked straight). Use `board` and `pick` as they are: no maths needed.

- **Count stacks far from cam 1.** Cam 1 is at the front left (about -312, -125, 440 mm up): the nearer a stack is to it, the more steeply it looks down and the less of the stack's side it sees, so a chip more or less hardly changes the outline (Nov 3: a 2-stack near the middle read as 1). Keep the stacks that matter (bets, the pot) toward the back right, and trust the crane's own record of what it stacked over a count from near the front left.
- **One colour a stack, ~1 cm apart.** Never put a white chip on a red stack (or the other way): from cam 1 the top colour and the side don't join up, and the scene reads only the top as a short stack (Nov 3: a white on 2 red read as one white). Touching stacks drop out of the scene. Change a bet by building a separate stack.
- **`fit` under 0.85**: `board` is only the flat footprint and there's no `count`: two stacks touching seen as one, a stack cut off by Esper or the crane, or a toppled one. Look with Esper (below), or ask.

## Counting a stack with Esper

When cam 1's count is doubtful or the stack matters (the pot, an all-in), send Esper:

1. Say it ("Let me ask my helper to count that."), `on_it`.
2. `POST hub/api/esper/look {x, y, distance: 170}`: Esper's camera ~150 mm from the stack's near edge (`distance` is to its centre, 20 mm further).
3. `counting`, then `GET hub/api/find?cam=esper&what=red poker chip stack|red object&effort=high&ask=How many poker chips are in this stack? Count the edges one by one. Reply with JSON only: {"count": 4, "confidence": 0.9}`. One count and how sure Muse is (0–1). `high` effort is slower (several s) but counts edges; `minimal` and `low` miscounted.
4. If `confidence` is under ~0.7, or Esper and cam 1 disagree: ask the people at the table.

Tested Nov 2 (4 red chips): at 120 mm with a crop and `effort=low`, 4, right; from 300 mm or the whole picture, 3. At 80 mm the stack's bottom is out of view. 150 mm with `high` effort: not tried yet; write the result in the notes.

## Moving chips

- **Heights come with each stack** in `/api/scene` `chips`: `pick_z` (press there to lift the top chip) and `place_z` (let go of a held chip there), from 3.3 mm a chip. When `sure` is false the count is borderline (`count_raw` near x.5) and they're planned for the taller stack: the cup stops short rather than pressing in; if the pick misses, try 3.3 mm lower. A chip lying alone may need Z 1.0 (Nov 3: one on a low spot didn't seal at 1.5).
- **Pick:** cup over the stack's `x, y`, down slowly (F600) to `pick_z`, `grip` with the pump left on, peel at F1500 to 5 mm above, lift. Check it came up (`find/check`, or the stack's count dropped).
- **Place:** G1 to the target stack's `place_z` at F1200, `drop`, Z 40. On the bare board: 3.9.
- **Push the pot:** Esper with `check: false` is a fine bulldozer (see esper). Say it as you do it.

## Esper's three tricks

Esper does the three things the crane can't: see a face-down card's face, turn a card, and flip one. Before any of them, **keep ~30 mm in front of Esper clear** (very important: the flipper arm sticks out and sweeps there; nothing but the card being worked on). And **find Esper room**: with the scene (or `find` with the pieces' names if it's crowded), pick an empty spot with ~30 cm clear in front of Esper and ~15 cm behind, and drive Esper there (`/api/esper/goto`). Esper backs up after a peek or a flip, and a card or stack in the way gets pushed. Say what you're doing as you do it, and never say your own cards out loud.

### 1. Seeing a card (your hole cards)

No camera above sees a face-down card's face. Two ways, cheapest first:

1. **Hold it up to Esper.** Pick the card (face down: its face now points down), carry it at Z 110 to ~160 mm in front of Esper's camera, lower to ~Z 65 (Nov 2: there the whole face shows; at Z 120 it's out of view), and `GET hub/api/see?cam=esper&effort=high&ask=Which playing card is this? Reply with JSON only: {"card": "5♣", "confidence": 0.9}`. `high` effort: at low effort it was too small to read. If the confidence is 0.8 or more, that's the card; put it back. **Not reliable (Nov 3):** five holds from 160 down to 80 mm and Z 65 to 50 gave 9♦ 0.7, 5♦ 0.85, 3♦ 0.65, 5♦ 0.8, 3♦ 0.7 for a 5♦: Esper's camera is too weak for a card held flat above it. Muse says 0.8 and is wrong, so a single hold proves nothing: go straight to the peek unless two holds agree.
2. **Not sure: the peek.** Esper in an empty spot, **flipper down first** (20, slowly): a raised flipper once got a card pushed under Esper and run over.
   - Place the card face down in front of Esper's face, long side along Esper's heading, ~130 mm ahead of Esper's marker. Carry it at Z 110 near Esper and lower only in front of it: a card hangs up to 44 mm past the cup, and **must not push Esper** (it has). Its near edge lands on the flipper's bent part, which sits a few mm up: don't press it into the flipper (Nov 3, lowered to Z 2: too hard). Come down slowly and drop it from just above that, ~Z 6.
   - **Read Esper's place from the scene first**, three times after it has stopped, not `assumed` (Nov 3: a stale reading put the card 30 mm short and Esper peeked at nothing; Esper's own `/step` moves aren't counted in the assumed place, so after a peek it's wrong until the camera sees Esper again). Flipper up **gently** to **~77°** (user's tuning Nov 3: 70° read 5♦ at 0.85–0.9 but once 7♦; 80° read 5♦ 0.9 twice but was cutting close to the drop at ~90°) while Esper creeps **~28 mm** forward: the card rides up the flipper and leans its face toward the camera. **Tested Nov 3: `servo?angle=70&speed=30` and, at the same moment, forward 18 mm (375 half-steps, wheels at speed 200; now 28 mm): read 5♦ at 0.9 twice, right.** Through the hub: `POST /api/esper/move {servo: 77, servo_speed: 30, drive: 28, wheel_speed: 200}` (counted into Esper's place, unlike `/step`). (Speed 60 looked too sudden; a 5 mm creep too little.) The combined move tripped Esper twice before working (it restarts: wait for it, check the flipper, retry): it doesn't happen every time. (Nov 2 read the corner at 50°; at 40° only the middle shows. Nov 3, 70° even with those faults: 5♦ read right twice, 0.95 and 0.9.)
   - `see?cam=esper&effort=high&ask=...` as above. Muse once misread a 5♣ as 6♣ from a poor view: if it's not sure, peek again a little higher, or read the corner index yourself.
   - **Drop the card off: flipper on up to ~90° (speed 30).** At about upright the card falls off flat, face down, in front of Esper (Nov 3: landed ~17 mm short of where it was placed, angle unchanged, and the scene saw it at once).
   - Flipper back to 20 **slowly** (speed 30) **while** Esper backs up ~60 mm (more than it crept: the lowered arm sticks out in front and lies over the dropped card otherwise; 18 and 40 mm were both too little, Nov 3), both at once (the user's rule; one after the other leaves the card lying awkwardly). The card may come along (Nov 2: dragged 45 mm and turned 15°): look with the scene and pick it where it is, then put it back in its place.

### 2. Straightening a card on Esper's head

The cup can't turn a card; Esper can. When a card is off by more than **~10°** (after a flip, or dealt crooked):

1. Pick the card. Bring it over Esper **centred exactly on Esper's marker**, long side along Esper's heading, at Z 110 (`/api/tip`). Then down slowly with `/api/send` `G1 Z104.2 F600` (the hub's own moves go straight down over Esper at full speed): Esper's top is Z 103, so that's 1.2 above, as for any card. `drop`, up to Z 110.
2. Turn Esper in place by the card's error (`/api/esper/goto` with Esper's own x, y and the new heading), slowly. The card turns with Esper.
3. The card now hides Esper's marker, so the camera can't see Esper: the hub works the turn out from the wheel steps (Nov 1: within 0.3°). The card is still on the marker, which moved a little: the marker is 8.6 mm behind Esper's turning centre, so it swings round it. Take Esper's position from the scene (`esper`, `assumed: true`) and pick the card there: cup over the marker's x, y at Z 110, then `G1 Z101.5 F600` (the lowest the hub allows over Esper: a 1.5 mm press on its top), `grip`, up.
4. Put the card back where it belongs. Its angle is the old one plus Esper's turn.

### 3. The flip (the flop, turn and river)

**Same as the peek, but Esper keeps going instead of reading** (Nov 3, the user's recipe; first run worked, 27 s for all of it):
1. Park the head at **(120, 230), Z 110**: at (190, 150) the gantry's wiring hangs over Esper's marker and cam 1 loses Esper; at (190, 230) the head hides the back-right board marker and goto refuses. Start from Esper's home (`/api/esper/home`). Read Esper's place from the scene, three times after it has stopped, not `assumed`.
2. Pick the card (across at Z 110, straight down) and drop it from Z 6, 130 mm ahead of Esper's marker, long side along Esper's heading. Park again.
3. At once: flipper to **~77°** (speed 30) and creep **28 mm** forward (wheel speed 200).
4. Then drive on **67 mm** at full speed (800): 95 mm in all. The card stands up and tips over.
5. At once: flipper to 20 (speed 30) and back up **60 mm**.
6. **Esper home, then the card to its proper spot** (its place in the row, or wherever the game needs it): it lands ~100 mm past where it was placed. A flipped card may need the cup pressed to Z −2 to lift (−1.5 left it behind, Nov 3).

Nov 3: the 5♦ landed face up ~100 mm past where it was placed, turned 2°, and the cache named it at once. Esper ends ~35 mm further forward than it started. Esper may drive over cards (it doesn't pick them up); the crane must mind the flipper sticking out in front.

(The older Nov 2 flip, 14 for 14: card 114 mm ahead, flipper 20 -> 65 at speed 60 and drive 95 mm at wheel speed 640 together, back 50, flipper down.)

Each flip turns the card 3-5° clockwise (seen from above). Past ~10°, straighten it on Esper's head (trick 2) before it goes in the row. Plan the board so a card lands where it'll be read, with the lane clear.
