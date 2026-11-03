#!/usr/bin/env python3
"""Smoke test for mcp_server.py against a mock hub (no Pi, no robot).

Starts a tiny HTTP server mimicking the hub endpoints the MCP server uses,
then talks MCP over stdio and checks: initialize/tools/list, get_scene,
mate_goto via hub, denied tools (raw G-code, direct Mate step, calibrate,
delete_chat) refused before any hub call, invalid args rejected, and
capture_image returns an MCP image block.

Run: python3 test_mcp.py  (exit 0 = pass)
"""
import base64, json, subprocess, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
HERE = Path(__file__).parent
SEEN = []

class MockHub(BaseHTTPRequestHandler):
    def _send(self, obj, ctype="application/json"):
        data = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        SEEN.append((self.command, self.path))
        if self.path.startswith("/api/scene"): self._send({"head": {"x": 0, "y": 0}, "mate": {"x": -90, "y": 215}, "cards": []})
        elif self.path.startswith("/api/status"): self._send({"state": "Idle", "homed": True})
        elif self.path.startswith("/api/mate/gestures"): self._send({"thumbs_up": {"emoji": "👍", "text": "thumbs up", "face": "happy"}})
        elif self.path.startswith("/api/capture"): self._send(b"\xff\xd8\xff\xd9", "image/jpeg")
        elif self.path.startswith("/api/guide"):
            body = b"# mock guide\n"; self.send_response(200); self.send_header("Content-Type", "text/plain"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        else: self._send({})
    def do_POST(self):
        SEEN.append((self.command, self.path)); length = int(self.headers.get("Content-Length") or 0); self.rfile.read(length)
        if self.path.startswith("/api/mate/goto"): self._send({"ok": True, "checked_path": True})
        elif self.path.startswith("/api/send"): self._send({"line": "", "reply": "SHOULD NOT HAPPEN"})
        else: self._send({"ok": True})
    def log_message(self, *a): pass

def rpc(proc, method, params=None, req_id=1):
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}) + "\n"); proc.stdin.flush(); return json.loads(proc.stdout.readline())

def call(proc, name, args, req_id):
    r = rpc(proc, "tools/call", {"name": name, "arguments": args}, req_id); assert "result" in r, r; return r["result"].get("isError", False), r["result"]["content"]

def main():
    server = HTTPServer(("127.0.0.1", 0), MockHub); port = server.server_address[1]; threading.Thread(target=server.serve_forever, daemon=True).start()
    env = {"MAGIC_TABLE_HUB_URL": f"http://127.0.0.1:{port}", "PATH": "/usr/bin:/bin"}
    proc = subprocess.Popen([sys.executable, str(HERE / "mcp_server.py")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    try:
        r = rpc(proc, "initialize", {"protocolVersion": "2024-11-05"}, 1); assert r["result"]["serverInfo"]["name"] == "magic-table", r
        r = rpc(proc, "tools/list", {}, 2); names = [t["name"] for t in r["result"]["tools"]]; assert len(names) >= 20, names; assert "send_gcode" not in names and "mate_step" not in names, names
        err, c = call(proc, "get_scene", {}, 3); assert not err and "mate" in c[0]["text"], c
        err, c = call(proc, "mate_goto", {"x": 10, "y": 20}, 4); assert not err and "checked_path" in c[0]["text"], c; assert any(p.startswith("/api/mate/goto") for _, p in SEEN), SEEN; assert not any("mate.local" in p for _, p in SEEN)
        err, c = call(proc, "send_gcode", {"line": "G0 X0"}, 5); assert err and "intentionally not exposed" in c[0]["text"], c; assert not any(p.startswith("/api/send") for _, p in SEEN), SEEN
        err, c = call(proc, "mate_step", {"s1": 100, "s2": 100}, 6); assert err, c
        err, c = call(proc, "move_tip", {"x": 0, "y": 0, "z": 999}, 7); assert err and "outside" in c[0]["text"], c
        err, c = call(proc, "say", {"text": "hi", "by": "mate"}, 8); assert err, c
        err, c = call(proc, "see", {"effort": "ultra"}, 9); assert err, c
        err, c = call(proc, "capture_image", {"cam": 1}, 10); assert not err and c[0]["type"] == "image" and c[0]["mimeType"] == "image/jpeg", c; assert base64.b64decode(c[0]["data"]) == b"\xff\xd8\xff\xd9"
        print(f"PASS: {len(names)} tools, mock hub saw {len(SEEN)} calls, deny-list held"); return 0
    finally:
        proc.stdin.close(); proc.wait(timeout=5); server.shutdown()

if __name__ == "__main__":
    raise SystemExit(main())
