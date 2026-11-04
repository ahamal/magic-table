"""Esper, from the hub: its live status, and driving it to a spot with the camera checking.

Agents can call Esper's own API (http://esper.local, see agent/esper.md) for anything. The hub
adds what needs the overhead camera: `goto` turns and drives Esper, looks, and corrects until
its turning centre is on the target, and `home` sends it to its home spot. `gesture` plays one
of Esper's gestures (agent/gestures.json): a reaction face, flipper and wheel moves. `move` is
one step of a recipe (the flip, the peek): the flipper and the wheels at once, counted into
where the hub thinks Esper is, which Esper's own /step isn't.

The body numbers below were measured on Nov 1 against the overhead camera (build notes);
another build should measure its own.
"""

import json
import math
import threading
import time
import urllib.request
from pathlib import Path

ESPER = "http://esper.local"
POSE_FILE = Path(__file__).parent / "esper_pose.json"   # where Esper is, kept across restarts
MM_PER_HALFSTEP = 0.048          # forward
DEG_PER_HALFSTEP = {"left": 0.0377, "right": 0.0371}
CENTRE = (8.6, 0.5)              # turning centre from the marker centre, Esper's frame (forward, left)
SPEED, ACCEL = 800, 1000         # full speed: the wheels are fine there (it's the servo that browns out)
CLOSE_MM, CLOSE_DEG = 5.0, 3.0   # good enough
REST, REST_SPEED = 20, 120       # the flipper's rest angle, and how gently a gesture goes back there
FACE_FPS = 10                    # reactions are drawn for 10 fps (software/esper/faces/make.py)


class EsperLink:
    def __init__(self, url=ESPER, every=1.0):
        self.url, self.every = url, every
        self.status = None        # last /status reply, or None while unreachable
        self.seen_at = None
        self.busy = False         # a goto is running
        self.pose = None          # where Esper's marker is (x, y, heading): last seen, plus moves since
        self.assumed = True       # True while that's only worked out from the moves
        legacy_pose = POSE_FILE.with_name("mate_pose.json")
        if not POSE_FILE.exists() and legacy_pose.exists():
            legacy_pose.rename(POSE_FILE)
        try:
            self.pose = tuple(json.loads(POSE_FILE.read_text()))
        except (OSError, ValueError):
            pass
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

    def servo(self, angle, speed):
        self._post(f"/servo?angle={angle}&speed={min(speed, 360)}")   # ≤60% of max: faster browns out

    def screen(self, frames, fps, repeat):
        req = urllib.request.Request(f"{self.url}/screen", data=frames, method="POST", headers={
            "Content-Type": "application/octet-stream", "X-FPS": str(fps), "X-Repeat": str(repeat)})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def _step(self, s1, s2, speed=SPEED):
        while s1 or s2:                                   # Esper takes at most 4096 per move
            k1, k2 = max(-4096, min(4096, s1)), max(-4096, min(4096, s2))
            self._post(f"/step?s1={k1}&s2={k2}&speed={speed}&accel={ACCEL}")
            time.sleep(0.1)
            while True:
                with urllib.request.urlopen(f"{self.url}/status", timeout=5) as r:
                    if not json.loads(r.read())["busy"]:
                        break
                time.sleep(0.1)
            s1, s2 = s1 - k1, s2 - k2

    def turn(self, deg, speed=SPEED):
        """Turn in place, deg anticlockwise (from above)."""
        n = round(abs(deg) / DEG_PER_HALFSTEP["left" if deg > 0 else "right"])
        self._step(n, n, speed) if deg > 0 else self._step(-n, -n, speed)

    def drive(self, mm, speed=SPEED):
        """Straight ahead (+) or back (-)."""
        n = round(abs(mm) / MM_PER_HALFSTEP)
        self._step(-n, n, speed) if mm > 0 else self._step(n, -n, speed)

    def seen(self, pose):
        """The camera saw Esper here: that's where it is now."""
        self._keep(pose, False)

    def _keep(self, pose, assumed):
        moved = self.pose is None or max(abs(a - b) for a, b in zip(pose, self.pose)) > 0.5
        self.pose, self.assumed = tuple(round(v, 1) for v in pose), assumed
        if moved:
            try:
                POSE_FILE.write_text(json.dumps(self.pose))
            except OSError:
                pass

    def _turned(self, deg):
        """Where the marker ends up after turning in place by deg (about the turning centre)."""
        if self.pose:
            cx, cy = self.centre(self.pose)
            h = self.pose[2] + deg
            a = math.radians(h)
            self._keep((cx - CENTRE[0] * math.cos(a) + CENTRE[1] * math.sin(a),
                        cy - CENTRE[0] * math.sin(a) - CENTRE[1] * math.cos(a), (h + 180) % 360 - 180), True)

    def _drove(self, mm):
        if self.pose:
            x, y, h = self.pose
            a = math.radians(h)
            self._keep((x + mm * math.cos(a), y + mm * math.sin(a), h), True)

    @staticmethod
    def centre(pose):
        x, y, h = pose
        a = math.radians(h)
        return (x + CENTRE[0] * math.cos(a) - CENTRE[1] * math.sin(a),
                y + CENTRE[0] * math.sin(a) + CENTRE[1] * math.cos(a))

    def goto(self, look, x, y, heading=None, tries=6):
        """Put Esper's turning centre on (x, y), then face `heading` (degrees, None = any).
        `look()` returns Esper's marker pose (x, y, heading) from the camera, or None.
        Turns toward the target (driving backward if that's the shorter turn), drives, looks
        again, and repeats until within CLOSE_MM / CLOSE_DEG. When the camera can't see Esper
        (glare, a cable over its marker), it carries on from where it last saw it plus the
        moves since (`assumed` in the answer), and stops correcting once it's there."""
        if self.busy:
            return {"ok": False, "error": "Esper is already on its way somewhere"}
        self.busy = True
        moves = []

        def where():
            p = look()
            if p is not None:
                self.seen(p)
            return self.pose

        try:
            for _ in range(tries):
                p = where()
                if p is None:
                    return {"ok": False, "error": "the camera can't see Esper's marker, and hasn't yet", "moves": moves}
                if self.assumed and moves:
                    break                                  # unseen: the moves got it there
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
                    self._turned(t)
                self.drive(-dist if back else dist)
                self._drove(-dist if back else dist)
                moves.append({"from": [round(cx, 1), round(cy, 1)], "turned": round(t, 1),
                              "drove": round(-dist if back else dist, 1)})
            p = where()
            if heading is not None:
                for _ in range(3):
                    t = (heading - p[2] + 180) % 360 - 180
                    if abs(t) <= CLOSE_DEG:
                        break
                    self.turn(t)
                    self._turned(t)
                    p = where()
                    if self.assumed:
                        break
            cx, cy = self.centre(p)
            return {"ok": True, "centre": [round(cx, 1), round(cy, 1)], "heading": round(p[2], 1),
                    "off_mm": round(math.hypot(x - cx, y - cy), 1), "moves": moves, "assumed": self.assumed}
        except OSError as e:
            return {"ok": False, "error": f"Esper didn't answer: {e}", "moves": moves}
        finally:
            self.busy = False

    def move(self, servo=None, servo_speed=None, turn=None, drive=None, wheel_speed=SPEED):
        """One step of a recipe: the flipper to `servo` degrees at `servo_speed` (it starts at once
        and keeps going while the wheels move: the peek lifts the card while Esper creeps forward),
        then turn `turn` degrees, then drive `drive` mm, at `wheel_speed` (half-steps/s; the peek
        creeps at 200). Returns when the wheels and the flipper are done. Wheel moves are counted
        into Esper's assumed place, unlike Esper's own /step."""
        if self.busy:
            return {"ok": False, "error": "Esper is busy"}
        self.busy = True
        try:
            t0, servo_s = time.time(), 0.0
            if servo is not None:
                now = (self.status or {}).get("servo_now", REST)
                self.servo(servo, servo_speed)
                servo_s = abs(servo - now) / max(1, min(servo_speed, 360))
            if turn:
                self.turn(turn, wheel_speed)
                self._turned(turn)
            if drive:
                self.drive(drive, wheel_speed)
                self._drove(drive)
            time.sleep(max(0, servo_s - (time.time() - t0)))
            return {"ok": True, "pose": self.pose, "assumed": self.assumed}
        except OSError as e:
            return {"ok": False, "error": f"Esper didn't answer: {e}"}
        finally:
            self.busy = False

    def gesture(self, g, faces):
        """Play a gesture: show its face (once), run its steps (servo [angle, speed] without
        waiting, drive mm, turn deg, wait s), then bring the flipper back to rest and the eyes
        back. `faces` is the folder with eyes.bin and reactions/."""
        if self.busy:
            return {"ok": False, "error": "Esper is busy"}
        self.busy = True
        moved = False
        try:
            if g.get("face"):
                self.screen((faces / "reactions" / f"{g['face']}.bin").read_bytes(), FACE_FPS, 1)
            for step in g.get("steps", []):
                if "servo" in step:
                    angle, speed = step["servo"]
                    self.servo(max(REST, min(150, angle)), speed)
                    moved = True
                if "drive" in step:
                    self.drive(max(-60, min(60, step["drive"])))
                if "turn" in step:
                    self.turn(max(-360, min(360, step["turn"])))
                if "wait" in step:
                    time.sleep(min(step["wait"], 5))
            if moved:
                with urllib.request.urlopen(f"{self.url}/status", timeout=5) as r:
                    now = json.loads(r.read()).get("servo_now", REST)
                self.servo(REST, REST_SPEED)
                time.sleep(abs(now - REST) / REST_SPEED)
            time.sleep(0.8)
            if g.get("face"):
                self.screen((faces / "eyes.bin").read_bytes(), 12, 0)
            return {"ok": True}
        except (OSError, ValueError, KeyError) as e:
            return {"ok": False, "error": f"Esper didn't answer: {e}"}
        finally:
            self.busy = False
