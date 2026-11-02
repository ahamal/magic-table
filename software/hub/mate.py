"""Mate, from the hub: its live status, and driving it to a spot with the camera checking.

Agents can call Mate's own API (http://mate.local, see agent/mate.md) for anything. The hub
adds what needs the overhead camera: `goto` turns and drives Mate, looks, and corrects until
its turning centre is on the target, and `home` sends it to its home spot.

The body numbers below were measured on Nov 1 against the overhead camera (build notes);
another build should measure its own.
"""

import json
import math
import threading
import time
import urllib.request

MATE = "http://mate.local"
MM_PER_HALFSTEP = 0.048          # forward
DEG_PER_HALFSTEP = {"left": 0.0377, "right": 0.0371}
CENTRE = (8.6, 0.5)              # turning centre from the marker centre, Mate's frame (forward, left)
SPEED, ACCEL = 640, 1000         # 80% of the max: full speed drops Mate's Wi-Fi now and then
CLOSE_MM, CLOSE_DEG = 5.0, 3.0   # good enough


class MateLink:
    def __init__(self, url=MATE, every=1.0):
        self.url, self.every = url, every
        self.status = None        # last /status reply, or None while unreachable
        self.seen_at = None
        self.busy = False         # a goto is running
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                with urllib.request.urlopen(f"{self.url}/status", timeout=2) as r:
                    self.status, self.seen_at = json.loads(r.read()), time.time()
            except (OSError, ValueError):
                self.status = None
            time.sleep(self.every)

    # ---- driving ----

    def _post(self, path):
        req = urllib.request.Request(f"{self.url}{path}", method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def _step(self, s1, s2):
        while s1 or s2:                                   # Mate takes at most 4096 per move
            k1, k2 = max(-4096, min(4096, s1)), max(-4096, min(4096, s2))
            self._post(f"/step?s1={k1}&s2={k2}&speed={SPEED}&accel={ACCEL}")
            time.sleep(0.1)
            while True:
                with urllib.request.urlopen(f"{self.url}/status", timeout=5) as r:
                    if not json.loads(r.read())["busy"]:
                        break
                time.sleep(0.1)
            s1, s2 = s1 - k1, s2 - k2

    def turn(self, deg):
        """Turn in place, deg anticlockwise (from above)."""
        n = round(abs(deg) / DEG_PER_HALFSTEP["left" if deg > 0 else "right"])
        self._step(n, n) if deg > 0 else self._step(-n, -n)

    def drive(self, mm):
        """Straight ahead (+) or back (-)."""
        n = round(abs(mm) / MM_PER_HALFSTEP)
        self._step(-n, n) if mm > 0 else self._step(n, -n)

    @staticmethod
    def centre(pose):
        x, y, h = pose
        a = math.radians(h)
        return (x + CENTRE[0] * math.cos(a) - CENTRE[1] * math.sin(a),
                y + CENTRE[0] * math.sin(a) + CENTRE[1] * math.cos(a))

    def goto(self, look, x, y, heading=None, tries=6):
        """Put Mate's turning centre on (x, y), then face `heading` (degrees, None = any).
        `look()` returns Mate's marker pose (x, y, heading) from the camera, or None.
        Turns toward the target (driving backward if that's the shorter turn), drives, looks
        again, and repeats until within CLOSE_MM / CLOSE_DEG."""
        if self.busy:
            return {"ok": False, "error": "Mate is already on its way somewhere"}
        self.busy = True
        moves = []
        try:
            for _ in range(tries):
                p = look()
                if p is None:
                    return {"ok": False, "error": "the camera can't see Mate's marker", "moves": moves}
                cx, cy = self.centre(p)
                dx, dy = x - cx, y - cy
                dist = math.hypot(dx, dy)
                if dist <= CLOSE_MM:
                    break
                bearing = math.degrees(math.atan2(dy, dx))
                t = (bearing - p[2] + 180) % 360 - 180
                back = abs(t) > 90                         # reverse instead of turning around
                if back:
                    t = (t + 360) % 360 - 180
                if abs(t) > 1:
                    self.turn(t)
                self.drive(-dist if back else dist)
                moves.append({"from": [round(cx, 1), round(cy, 1)], "turned": round(t, 1),
                              "drove": round(-dist if back else dist, 1)})
            p = look()
            if p is None:
                return {"ok": False, "error": "lost sight of Mate", "moves": moves}
            if heading is not None:
                for _ in range(3):
                    t = (heading - p[2] + 180) % 360 - 180
                    if abs(t) <= CLOSE_DEG:
                        break
                    self.turn(t)
                    p = look() or p
            cx, cy = self.centre(p)
            return {"ok": True, "centre": [round(cx, 1), round(cy, 1)], "heading": round(p[2], 1),
                    "off_mm": round(math.hypot(x - cx, y - cy), 1), "moves": moves}
        except OSError as e:
            return {"ok": False, "error": f"Mate didn't answer: {e}", "moves": moves}
        finally:
            self.busy = False
