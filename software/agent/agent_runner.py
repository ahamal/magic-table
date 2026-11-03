#!/usr/bin/env python3
"""Minimal Muse Spark agent loop over the Magic Table MCP server.

Step 4 loop (software/agent/README.md): look -> act -> check, with the
model calling hub tools through MCP, not directly.

Run on the Pi (same machine as hub + MCP server)::

    export MODEL_API_KEY=<key>   # Pi only, never in git; already in ~/hub/.env for STT
    python3 agent_runner.py --instruction "Deal a Texas hold'em hand for two players, then run the flop."
    python3 agent_runner.py --instruction "..." --auto   # no motion gate; rehearsed demo only

1. Spawns mcp_server.py (stdio MCP). 2. Reads guides + notes through MCP
and builds the system prompt from them (not a hardcoded copy). 3. Calls
Muse Spark (muse-spark-1.3) via Meta Model API Responses API, with MCP
tools translated to function tools. 4. Executes each call through MCP,
returns the result, repeats until no more tool calls or --max-turns.

Transcript: chat_poll IS the subscription (final transcripts only, via
Muse Voice Transcribe on the hub). Contribute with say (spoken), chat_post
(typed), mate_gesture (Mate). Track highest chat id, poll after=that id.

Safety: by default asks a human on the Pi console to confirm the FIRST
motion tool call (STOP and unlock never wait). Hub limits still apply
either way. Requires openai package (already in hub requirements.txt).
"""
import argparse
import json
import os
import subprocess
import sys

MODEL = "muse-spark-1.3"
API_URL = "https://api.meta.ai/v1"
# STOP is never gated: an emergency stop mustn't wait for a y/N
MOTION_TOOLS = {"move_tip", "move_head", "jog", "gripper", "mate_goto", "mate_home", "mate_look", "mate_move", "mate_gesture"}


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
    ap.add_argument("--instruction", required=True)
    ap.add_argument("--mcp", default=None)
    ap.add_argument("--hub-url", default=os.environ.get("MAGIC_TABLE_HUB_URL", "http://localhost:8000"))
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--api-url", default=API_URL)
    ap.add_argument("--max-turns", type=int, default=40)
    ap.add_argument("--by", default="Muse")
    ap.add_argument("--effort", default="low", choices=("minimal", "low", "medium", "high"),
                    help="the agent's own reasoning (vision calls choose theirs per tool)")
    ap.add_argument("--auto", action="store_true", help="skip first-motion human gate (rehearsed demo only)")
    args = ap.parse_args(argv)
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
        tools = client.tools()
        print(f"MCP tools: {len(tools)}", file=sys.stderr)
        parts = []
        for name in ("guide", "table", "mate", "poker"):
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
                   "Before any motion, read get_scene and get_calibration; if needs_reanchor, unlock then reanchor. "
                   "Park the gantry head before see/find. Keep your own game state; verify picks with find_check. "
                   "Ask humans with say when stuck, then wait with chat_poll. Transcript: chat_poll IS your "
                   "subscription to player speech (final transcripts only, via Muse Voice Transcribe on the hub -- "
                   "do not act on partials, there are none in chat_poll). Contribute with say for spoken lines "
                   "(never by='player' or 'mate'), chat_post for typed notes, and mate_gesture for Mate. Track the "
                   "highest chat id you have seen and poll with after=that id, wait=30, in a loop while waiting "
                   "for players -- an empty poll is not the end of the game.")
        fn_tools = [{"type": "function", "name": t["name"], "description": t.get("description", ""), "parameters": t["inputSchema"]} for t in tools]
        api = OpenAI(base_url=args.api_url, api_key=key)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": args.instruction}]
        gated = False
        for turn in range(args.max_turns):
            resp = api.responses.create(model=args.model, reasoning={"effort": args.effort}, tools=fn_tools, input=messages)
            calls = [o for o in resp.output if getattr(o, "type", None) == "function_call"]
            if resp.output_text:
                print(f"[turn {turn}] {resp.output_text}")
            if not calls:
                print("Done (no more tool calls).")
                return 0
            messages += resp.output   # the model's own items (reasoning, calls) go back as they came
            for call in calls:
                try:
                    call_args = json.loads(call.arguments or "{}")
                except ValueError:
                    call_args = {}
                if call.name in MOTION_TOOLS and not args.auto and not gated:
                    ok = input(f"Allow first motion: {call.name} {call_args}? [y/N] ").strip().lower()
                    if ok != "y":
                        print("Stopped by human gate.")
                        return 1
                    gated = True
                print(f"[turn {turn}] tool {call.name} {call_args}")
                try:
                    out = content_text(client.call(call.name, call_args))
                except Exception as e:
                    out = f"error: {e}"
                messages.append({"type": "function_call_output", "call_id": call.call_id, "output": out})
        print("Stopped: max turns reached.")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
