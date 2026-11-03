# Poker guide

How to run a hand of Texas hold'em at the Magic Table: what's poker-only lives here; the tools it uses are generic and in [table](table.md) and [mate](mate.md). Served at `GET /api/guide/poker`. Read the [README](README.md), table and mate first.

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
2. **In doubt, `find` with the names above, straight away** (SAM, ~2-4 s): a stack that's `sure: false`, one that's missing (stacks touching, or next to Mate or the crane), a card the scene doesn't show (overlapping cards), or before a pick that matters. Ask only for what you're unsure of, one name a call (`what=white poker chip|white object`): fewer names, fewer things found, faster.
3. **Still unsure:** Mate's high-effort count (below), or ask the people.

## The camera makes mistakes: keep your own count

What you see is a good guess, not the truth. **Keep your own record of the game** (what you dealt and where, each player's chips, what you moved into the pot) and use the scene to check it, not to replace it. When they disagree, look again with `find` for just that thing, then ask the people ("Is that one card or a few?"). Never act on one surprising reading. Mistakes seen so far:

- **A single card read as a small deck** (Nov 3: the card at the far left came out "deck ~10", 5.2 mm, just past the 5 mm a deck needs; curled cards and the board's edges do this). A deck you didn't put there is a card.
- **A deck of fewer than ~10 cards read as a card.**
- **Deck size is ±3 cards**: use it for "about how many are left", never to deal by.
- **A stack ±1 chip** when `count_raw` is near x.5 (`sure: false`), and more often near cam 1 (front left) and at the board's edges.
- **Things vanish**: touching stacks, face-up cards touching each other (face-down ones are found by their backs), anything under the crane or Mate or a hand. Park the head and keep hands off before looking.
- **Glare** (a lamp reflecting off the mat) can hide cards or join them up.
- **A new face-up card** has no name for a second or two, until Muse reads it.

## Chips: where and how many, from cam 1

`find` knows a chip is 40 × 3.3 mm and a deck 63 × 88: each stack and the deck come back with `board` where they really stand, `height_mm`, and for a stack **`count`**, the number of chips (it assumes they're stacked straight). Use `board` and `pick` as they are: no maths needed.

- **Count stacks far from cam 1.** Cam 1 is at the front left (about -312, -125, 440 mm up): the nearer a stack is to it, the more steeply it looks down and the less of the stack's side it sees, so a chip more or less hardly changes the outline (Nov 3: a 2-stack near the middle read as 1). Keep the stacks that matter (bets, the pot) toward the back right, and trust the crane's own record of what it stacked over a count from near the front left.
- **One colour a stack, ~1 cm apart.** Never put a white chip on a red stack (or the other way): from cam 1 the top colour and the side don't join up, and the scene reads only the top as a short stack (Nov 3: a white on 2 red read as one white). Touching stacks drop out of the scene. Change a bet by building a separate stack.
- **`fit` under 0.85**: `board` is only the flat footprint and there's no `count`: two stacks touching seen as one, a stack cut off by Mate or the crane, or a toppled one. Look with Mate (below), or ask.

## Counting a stack with Mate

When cam 1's count is doubtful or the stack matters (the pot, an all-in), send Mate:

1. Say it ("Let me ask my helper to count that."), `on_it`.
2. `POST hub/api/mate/look {x, y, distance: 170}`: Mate's camera ~150 mm from the stack's near edge (`distance` is to its centre, 20 mm further).
3. `counting`, then `GET hub/api/find?cam=mate&what=red poker chip stack|red object&effort=high&ask=How many poker chips are in this stack? Count the edges one by one. Reply with JSON only: {"count": 4, "confidence": 0.9}`. One count and how sure Muse is (0–1). `high` effort is slower (several s) but counts edges; `minimal` and `low` miscounted.
4. If `confidence` is under ~0.7, or Mate and cam 1 disagree: ask the people at the table.

Tested Nov 2 (4 red chips): at 120 mm with a crop and `effort=low`, 4, right; from 300 mm or the whole picture, 3. At 80 mm the stack's bottom is out of view. 150 mm with `high` effort: not tried yet; write the result in the notes.

## Moving chips

- **Heights come with each stack** in `/api/scene` `chips`: `pick_z` (press there to lift the top chip) and `place_z` (let go of a held chip there), from 3.3 mm a chip. When `sure` is false the count is borderline (`count_raw` near x.5) and they're planned for the taller stack: the cup stops short rather than pressing in; if the pick misses, try 3.3 mm lower. A chip lying alone may need Z 1.0 (Nov 3: one on a low spot didn't seal at 1.5).
- **Pick:** cup over the stack's `x, y`, down slowly (F600) to `pick_z`, `grip` with the pump left on, peel at F1500 to 5 mm above, lift. Check it came up (`find/check`, or the stack's count dropped).
- **Place:** G1 to the target stack's `place_z` at F1200, `drop`, Z 40. On the bare board: 3.9.
- **Push the pot:** Mate with `check: false` is a fine bulldozer (see mate). Say it as you do it.

## Peeking at your own cards

Your hole cards lie face down, and no camera sees a face-down card's face. Mate peeks for you, the way a player lifts a corner:

1. Mate square to the card's spot, flipper down (20). The crane puts the card face down in front of Mate's face, its long side along Mate's heading, ~130-135 mm ahead of Mate's marker (114, as for flipping, is too close: the camera sees one pip). Drop it from 2 mm.
2. Flipper up **slowly** (`speed=60`) to ~50-60°: the card's near edge lifts toward Mate's camera. At 40° only the middle shows; at 50° the corner index shows (Nov 2: a 5♣, upside down, the flipper blade across the middle).
3. `GET hub/api/see?cam=mate&effort=low&ask=...` and **read the corner index yourself if you can**: Muse misread 5♣ as 6♣ twice from this view (low light, upside down).
4. Flipper back to 20 slowly. The card stays on the flipper; Mate backing up drags it along (Nov 2: 45 mm, turned 15°), so look with cam 1 and pick it where it is, then put it back in its place.
5. Never say your cards out loud.

Holding the card above Mate's camera with the cup instead: at Z 120 it's out of view; at Z 65 about 160 mm in front the whole face shows but too small to read reliably.

## Turning cards face up

The flop, turn and river: Mate's flip ([mate](mate.md), "Flipping cards over"). It needs ~30 cm of clear lane ahead of Mate: plan the board so the cards land where they'll be read.
