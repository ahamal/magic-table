#!/usr/bin/env python3
"""Minimal Muse Spark agent loop over the Magic Table MCP server.

Step 4 loop (software/agent/README.md): look -> act -> check, with the
model calling hub tools through MCP, not directly.

Run on the Pi (same machine as hub + MCP server)::

    export MODEL_API_KEY=<key>   # Pi only, never in git; already in ~/hub/.env for STT
    python3 agent_runner.py --instruction "Deal a Texas hold'em hand for two players, then run the flop."
    python3 agent_runner.py --live                      # stay at the table: act on what players say
    python3 agent_runner.py --live --clear-chat         # ...on a fresh talk page (the old chat is kept on the Pi)

--live: after each task the runner waits on the chat (no model calls while
waiting) and hands the next thing players say to Muse as the next task,
until Ctrl-C. Messages Muse already read with chat_poll during a task
aren't handed over twice. Only the last few tasks are kept in the
conversation, so each call stays about the same size.

1. Spawns mcp_server.py (stdio MCP). 2. Reads guides + notes through MCP
and builds the system prompt from them (not a hardcoded copy). 3. Calls
Muse Spark (muse-spark-1.3) via Meta Model API Responses API, with MCP
tools translated to function tools. 4. Executes each call through MCP,
returns the result, repeats until no more tool calls or --max-turns.

Transcript: chat_poll IS the subscription (final transcripts only, via
Muse Voice Transcribe on the hub). Contribute with say (spoken), chat_post
(typed), esper_gesture (Esper). Track highest chat id, poll after=that id.

Safety: there's no confirmation prompt (the user, Nov 3: it got in the
way); the hub's limits apply to every move, and STOP is on the jog page.
Requires openai package (already in hub requirements.txt).
"""
import argparse
import json
import os
import subprocess
import sys

MODEL = "muse-spark-1.3"
API_URL = "https://api.meta.ai/v1"
KEEP_TASKS = 3   # --live: earlier tasks drop out of the conversation (cost stays flat)


class MCPClient:
    def __init__(self, command):
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, text=True)
        self._id = 0
        self._rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "magic-table-runner", "version": "1.0"}})
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        self.proc.stdin.flush()

    def _rpc(self, method, params):
        self._id += 1
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("MCP server closed stdout")
        resp = json.loads(line)
        if "error" in resp:
            raise RuntimeError(f"MCP {method} error: {resp['error']}")
        return resp["result"]

    def tools(self):
        return self._rpc("tools/list", {})["tools"]

    def call(self, name, args):
        res = self._rpc("tools/call", {"name": name, "arguments": args})
        if res.get("isError"):
            raise RuntimeError(" | ".join(c.get("text", "") for c in res.get("content", [])))
        return res["content"]

    def close(self):
        try:
            self.proc.stdin.close()
        except BrokenPipeError:
            pass
        self.proc.wait(timeout=5)


def content_text(content):
    return "\n".join(c.get("text", "") for c in content if c.get("type") == "text")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Muse Spark loop over Magic Table MCP")
    ap.add_argument("--instruction", help="the task (with --live: the first one; default: a short greeting)")
    ap.add_argument("--live", action="store_true", help="stay at the table: act on what players say, until Ctrl-C")
    ap.add_argument("--clear-chat", action="store_true",
                    help="start on a fresh chat; the hub keeps the old one in ~/hub/chats/")
    ap.add_argument("--mcp", default=None)
    ap.add_argument("--hub-url", default=os.environ.get("MAGIC_TABLE_HUB_URL", "http://localhost:8000"))
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--api-url", default=API_URL)
    ap.add_argument("--max-turns", type=int, default=40, help="model rounds per task")
    ap.add_argument("--by", default="Muse")
    ap.add_argument("--esper-name", default="Esper", help="what Esper is called at the table (the code says Esper)")
    ap.add_argument("--effort", default="low", choices=("minimal", "low", "medium", "high"),
                    help="the agent's own reasoning (vision calls choose theirs per tool)")
    ap.add_argument("--auto", action="store_true", help=argparse.SUPPRESS)   # no prompt any more; kept so old commands run
    args = ap.parse_args(argv)
    if not args.instruction and not args.live:
        ap.error("give --instruction, or --live to stay at the table")
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        print("MODEL_API_KEY is not set (Pi only, never in git).", file=sys.stderr)
        return 2
    try:
        from openai import OpenAI
    except ImportError:
        print("openai package is required (hub requirements.txt).", file=sys.stderr)
        return 2
    mcp_path = args.mcp or os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")
    os.environ["MAGIC_TABLE_HUB_URL"] = args.hub_url
    client = MCPClient([sys.executable, mcp_path])
    try:
        if args.clear_chat:
            print(f"Chat cleared: {clear_chat(args.hub_url)}", file=sys.stderr)
        # capture_image returns a picture, and this loop passes only text back: Muse would be blind to it
        tools = [t for t in client.tools() if t["name"] != "capture_image"]
        print(f"MCP tools: {len(tools)}", file=sys.stderr)
        parts = []
        for name in ("guide", "table", "esper", "poker"):
            try:
                parts.append(content_text(client.call("get_guide", {"name": name})))
            except Exception as e:
                print(f"warning: could not read guide {name}: {e}", file=sys.stderr)
        try:
            parts.append("## Build notes\n" + content_text(client.call("get_notes", {})))
        except Exception as e:
            print(f"warning: could not read notes: {e}", file=sys.stderr)
        system = "\n\n".join(parts)
        system += (f"\n\nYou speak as {args.by}: pass by='{args.by}' to say, chat_post, see and find. "
                   "Speak in one or two short sentences (under about 20 words): say what matters, not everything "
                   "you saw; people can see the table. When a task is done, say so in one short line. "
                   "Be quick: every round with you takes seconds, so use as few rounds as you can. Use batch for "
                   "any run of steps you already know (a whole pick: across high, down, grip, peel, up; a whole "
                   "place; say together with esper_gesture), and only look again when you need the answer. "
                   f"Esper (the robot the guides call Esper) is called {args.esper_name} at the table: use that name "
                   f"out loud. {args.esper_name} is part of the show: greet with her, and give her one gesture a task "
                   "when it fits (a reaction to the players, on_it before an errand, celebrate after a good move), in "
                   "the same batch as your line. "
                   "Before any motion, read get_scene and get_calibration; if needs_reanchor, unlock then reanchor. "
                   "Park the gantry head before see/find. Keep your own game state; verify picks with find_check. "
                   "Ask humans with say when stuck, then wait with chat_poll. Transcript: chat_poll IS your "
                   "subscription to player speech (final transcripts only, via Muse Voice Transcribe on the hub -- "
                   "do not act on partials, there are none in chat_poll). Contribute with say for spoken lines "
                   "(never by='player' or 'esper'), chat_post for typed notes, and esper_gesture for Esper. Track the "
                   "highest chat id you have seen and poll with after=that id, wait=30, in a loop while waiting "
                   "for players -- an empty poll is not the end of the game.")
        if args.live:
            system += ("\n\nYou are live at the table. Each task is what the players just said (with their "
                       "chat ids). Do it, answer out loud, then stop calling tools: the runner waits for the "
                       "players and hands you what they say next. Don't poll the chat just to wait for the "
                       "next request.")
        fn_tools = [{"type": "function", "name": t["name"], "description": t.get("description", ""), "parameters": t["inputSchema"]} for t in tools]
        api = OpenAI(base_url=args.api_url, api_key=key)
        state = {"seen": set()}   # chat ids Muse read itself (chat_poll)
        tasks = []                                # one list of conversation items per task

        def run_task(text):
            items = [{"role": "user", "content": text}]
            tasks.append(items)
            del tasks[:-KEEP_TASKS]
            for turn in range(args.max_turns):
                convo = [{"role": "system", "content": system}] + [i for t in tasks for i in t]
                resp = api.responses.create(model=args.model, reasoning={"effort": args.effort}, tools=fn_tools, input=convo)
                calls = [o for o in resp.output if getattr(o, "type", None) == "function_call"]
                if resp.output_text:
                    print(f"[turn {turn}] {resp.output_text}", flush=True)
                # the calls (and any text) go back as they came; reasoning items don't: Meta's API doesn't
                # keep them, so on a later task it refuses them ("was not found or has expired")
                items += [o for o in resp.output if getattr(o, "type", None) != "reasoning"]
                if not calls:
                    return True
                for call in calls:
                    try:
                        call_args = json.loads(call.arguments or "{}")
                    except ValueError:
                        call_args = {}
                    print(f"[turn {turn}] tool {call.name} {call_args}", flush=True)
                    try:
                        out = content_text(client.call(call.name, call_args))
                    except Exception as e:
                        out = f"error: {e}"
                    if call.name == "chat_poll":
                        state["seen"].update(m.get("id") for m in chat_items(out))
                    items.append({"type": "function_call_output", "call_id": call.call_id, "output": out})
            print(f"Stopped this task: {args.max_turns} rounds.", flush=True)
            return False

        if not args.live:
            return 0 if run_task(args.instruction) else 1

        # live: start after whatever is already in the chat, so old requests aren't replayed
        last = max([m.get("id", 0) for m in chat_items(content_text(client.call("chat_poll", {"after": 0})))] or [0])
        def live_task(text):
            """A task in live mode: an API error drops that task and keeps listening, not the whole run."""
            try:
                run_task(text)
            except Exception as e:
                if tasks:
                    tasks.pop()     # don't send a broken task again with the next one
                print(f"This task failed ({type(e).__name__}): {str(e)[:300]}. Still listening.", flush=True)

        live_task(args.instruction or f"You've just sat down at the table. In one batch: greet the players in one "
                 f"short sentence (introduce {args.esper_name}) and have {args.esper_name} wave (esper_gesture hello).")
        print("Live: waiting for the players (Ctrl-C to stop).", flush=True)
        while True:
            new = chat_items(content_text(client.call("chat_poll", {"after": last, "wait": 60, "by": "player"})))
            if not new:
                continue
            last = max(m.get("id", 0) for m in new)
            new = [m for m in new if m.get("id") not in state["seen"]]
            if not new:
                continue
            said = "\n".join(f"[chat {m.get('id')}] {m.get('text', '')}" for m in new)
            print(f"Players: {said}", flush=True)
            live_task(f"The players said:\n{said}")
    except KeyboardInterrupt:
        print("\nStopped (Ctrl-C). Anything GRBL already queued keeps going: STOP is on the jog page.")
        return 0
    finally:
        client.close()


def clear_chat(hub_url):
    """Fresh chat on the talk page. Straight to the hub: the MCP server doesn't offer this to the
    model (an agent shouldn't wipe what people said); this is the person starting the runner."""
    import urllib.request
    req = urllib.request.Request(hub_url.rstrip("/") + "/api/chat", method="DELETE")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read()).get("archived") or "it was empty"


def chat_items(text):
    """chat_poll's answer (a JSON list) -> the messages; [] if it isn't one."""
    try:
        items = json.loads(text)
    except ValueError:
        return []
    return [m for m in items if isinstance(m, dict)] if isinstance(items, list) else []


if __name__ == "__main__":
    raise SystemExit(main())
