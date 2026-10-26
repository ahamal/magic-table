# Agent (the brain)

Everything clever. Step 4. Uses the body API — the same one humans use.

## Parts

- **MCP server:** wraps the body API as tools for Muse Spark.
- **Labeler:** SAM 3.1 + ArUco → objects with gantry coordinates. Called only when needed.
- **Body model:** learned calibration for the Frame and Mate (steps per mm, steps per degree, sign conventions, servo angles). Learned by experiment — move, look, compare — then saved and reused.
- **Macros:** deal, peek (pick → hover over Mate → `capture("mate")`), flip.
- **Verification:** predict, act, check; report mismatches (e.g. double picks).
- **Turn loop:** look → act → look again. Model calls only on a command or at the end of a turn.
- **Game knowledge:** prompts and notes per game (poker first). Rules are taught in plain English.
- **Engines (optional):** KataGo (Go), Stockfish (chess).

## Budget

$150 Meta Model API credits. Images cost roughly 1–2k tokens each — capture only when needed.
