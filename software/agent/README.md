# Agent (the brain)

Muse Spark running the table, through the same hub API people use. The guides it reads (what's available, recipes, how to behave) are in [agent/](../../agent/README.md); this folder is the code that connects it.

| File | What |
|---|---|
| [`mcp_server.py`](mcp_server.py) | MCP server over stdio wrapping the hub (29 tools): look (free scene, `see`, `find`, cards), move the cup, grip, drive Esper and her flipper, gestures, speech, the chat, notes, and `batch` for a whole recipe in one call. No raw G-code, no homing, no direct Esper calls: every move goes through the hub's limits. |
| [`agent_runner.py`](agent_runner.py) | Muse Spark (`muse-spark-1.3`) in a loop over that server. `--instruction "..."` for one task; `--live` to stay at the table and act on what players say on the talk page, until Ctrl-C. |
| [`test_mcp.py`](test_mcp.py) | Checks the server against a fake hub: the tools, the refusals, batching, the move order. |
| [`MCP_README.md`](MCP_README.md) | Deploying, running, and the design notes (what's left out on purpose, vision tiers, the chat). |

Run on the Pi:

```bash
cd ~/hub && export MODEL_API_KEY=$(grep MODEL_API_KEY .env | cut -d= -f2)
.venv/bin/python mcp/agent_runner.py --live --clear-chat
```

## Budget

$150 Meta Model API credits. The guides and notes (~20k tokens) go with every call, so the runner keeps only the last few tasks in the conversation, batches known steps, and doesn't call the model while it waits for players.
