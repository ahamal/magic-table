"""Where things are on the table, from the cameras, with no external AI.

The gantry is the reference. Calibration moves the head marker (ArUco ID 10)
over a grid at several heights; every stop pairs a known gantry position with where
each camera sees the marker, and a DLT fit gives each camera's full projection
in gantry coordinates (X/Y in mm, Z in GRBL units, Z+ up). After that:

- the head is where GRBL says, and the camera checks it (error in mm);
- a pixel plus a height gives a gantry X/Y, so cards on the board, Mate's
  marker and the board markers all come out in gantry coordinates;
- the board markers (IDs 0-3) were recorded at calibration, so a camera that
  got bumped is noticed and corrected from them;
- after a GRBL reset (no limit switches), re-anchoring puts the work
  coordinates back where they were, from where the camera sees the head.

Coordinates are GRBL work coordinates at calibration time. Don't use the jog
page's Work zero afterwards: re-anchor or recalibrate instead. Z is in GRBL
units, Z+ up ($3=4 inverts the Z motor so that GRBL's Z+ is up, as on any CNC);
the board's Z comes from touching it with the cup.
"""

import json
import math
import threading
import time
from pathlib import Path

import cv2
import numpy as np

CAL_FILE = Path(__file__).parent / "calibration.json"
POS_FILE = Path(__file__).parent / "last_position.json"   # for re-anchoring after a GRBL reset

DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
BOARD_IDS, HEAD_ID, MATE_ID = (0, 1, 2, 3), 10, 20
# black-square size of the markers as printed now (mm, the Nov 1 sheet); the board and
# Mate ones also give their height, by finding where the camera would see them at that
# size. The head plate stands upright, so its size says nothing about height.
SIZE = {"board": 30.0, "head": 25.0, "mate": 30.0}
TIP_BELOW_MARKER = 57.0   # cup tip is this far below the head marker's centre (mm)
CLEARANCE = 15.0          # calibration keeps the cup at least this far above the board (mm)
MATE_MARGIN = 40.0        # mm around Mate's footprint that counts as "over Mate"
TABLE_CAM = 1             # the camera that looks down on the board (cam 0 is too low for it)
MATE_SIZE = (130.0, 130.0, 107.0)  # mm; the marker is on its top
CARD = (63.0, 88.0)       # poker card, mm
BUMP_PX = 2.0             # board markers moved more than this: the camera moved


def detector():
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    return cv2.aruco.ArucoDetector(DICT, params)


def detect(det, img):
    """{id: 4x2 corners (TL, TR, BR, BL as printed)}"""
    corners, ids, _ = det.detectMarkers(img)
    if ids is None:
        return {}
    return {int(i): c.reshape(4, 2).astype(np.float64) for c, i in zip(corners, ids.flatten())}


def centre(c):
    """Projection of the square's centre: where the diagonals cross."""
    p1, p2, p3, p4 = c[0], c[2], c[1], c[3]
    d1, d2 = p2 - p1, p4 - p3
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < 1e-9:
        return c.mean(axis=0)
    t = ((p3[0] - p1[0]) * d2[1] - (p3[1] - p1[1]) * d2[0]) / den
    return p1 + t * d1


# ---- camera model ----

def fit_dlt(world, pix):
    """3x4 projection from >= 6 non-coplanar world<->pixel pairs (normalised DLT)."""
    world, pix = np.asarray(world, float), np.asarray(pix, float)

    def norm(pts):
        m = pts.mean(axis=0)
        s = math.sqrt(pts.shape[1]) / np.mean(np.linalg.norm(pts - m, axis=1))
        T = np.eye(pts.shape[1] + 1)
        T[:-1, :-1] *= s
        T[:-1, -1] = -s * m
        return T

    Tw, Tp = norm(world), norm(pix)
    W = (Tw @ np.c_[world, np.ones(len(world))].T).T
    U = (Tp @ np.c_[pix, np.ones(len(pix))].T).T
    rows = []
    for (X, Y, Z, w), (u, v, s) in zip(W, U):
        rows.append([X, Y, Z, w, 0, 0, 0, 0, -u * X, -u * Y, -u * Z, -u * w])
        rows.append([0, 0, 0, 0, X, Y, Z, w, -v * X, -v * Y, -v * Z, -v * w])
    P = np.linalg.svd(np.array(rows))[2][-1].reshape(3, 4)
    P = np.linalg.inv(Tp) @ P @ Tw
    return P / np.linalg.norm(P[2, :3])


def project(P, xyz):
    x = P @ np.r_[xyz, 1.0]
    return x[:2] / x[2]


def to_xy(P, pix, z):
    """Pixels -> gantry X/Y on the plane Z = z."""
    H = np.c_[P[:, 0], P[:, 1], P[:, 2] * z + P[:, 3]]
    pts = cv2.perspectiveTransform(np.asarray(pix, float).reshape(-1, 1, 2), np.linalg.inv(H))
    return pts.reshape(-1, 2)


def camera_position(P):
    c = np.linalg.svd(P)[2][-1]
    return c[:3] / c[3]


def height_from_size(P, corners, size):
    """Z at which this marker would appear the size it does (side length = size mm).
    Searched below the camera, where the apparent size grows steadily with depth."""
    cz = camera_position(P)[2]
    lo, hi = cz - 3000, cz - 5            # Z+ is up: from far below the camera to just under it

    def side(z):
        q = to_xy(P, corners, z)
        return np.mean([np.linalg.norm(q[i] - q[(i + 1) % 4]) for i in range(4)])

    flo, fhi = side(lo) - size, side(hi) - size
    if flo * fhi > 0:
        return None
    for _ in range(50):
        mid = (lo + hi) / 2
        fm = side(mid) - size
        if fm * flo > 0:
            lo, flo = mid, fm
        else:
            hi = mid
    return (lo + hi) / 2


# ---- the vision service ----

class Aborted(Exception):
    pass


class Vision:
    def __init__(self, cameras, grbl, emit):
        self.cameras, self.grbl, self.emit = cameras, grbl, emit
        self.cal = json.loads(CAL_FILE.read_text()) if CAL_FILE.exists() else None
        self.scene = {"calibrated": bool(self.cal)}
        self.busy = False
        self._abort = None
        # GRBL reset since the last known position. A starting hub always means one:
        # opening the serial port resets the Uno.
        self.needs_reanchor = CAL_FILE.exists()
        self.last_pos = json.loads(POS_FILE.read_text()) if POS_FILE.exists() else None
        grbl.listeners.append(self._on_grbl)
        self._dets = {}
        self._lock = threading.Lock()

    def _det(self, cam):
        if cam not in self._dets:
            self._dets[cam] = detector()
        return self._dets[cam]

    def _frame(self, cam):
        c = self.cameras[cam]
        img = c.image() if c.cam is not None else None
        return None if img is None else cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)

    def _wpos(self):
        return list(self.grbl.status.get("WPos") or [0.0, 0.0, 0.0])

    def _move(self, line):
        """One calibration move, then wait for it. Any sign of trouble (a reset, a pause, an
        alarm, a refused line, STOP) aborts the whole calibration with no further moves:
        without limit switches, a count can't be trusted after any of those."""
        if self._abort:
            raise Aborted(self._abort)
        reply = self.grbl.send(line, 120)
        if reply != "ok":
            raise Aborted(f"GRBL answered {reply} to {line}")
        if self.grbl.send("G4 P0", 120) != "ok":
            raise Aborted("GRBL stopped answering")
        t = time.time()
        while time.time() - t < 120:
            st = self.grbl.status.get("state", "")
            if self._abort:
                raise Aborted(self._abort)
            if st == "Idle":
                return
            if not st.startswith(("Run", "Jog")):
                raise Aborted(f"GRBL went to {st}")
            time.sleep(0.05)
        raise Aborted("move took too long")

    def stop(self):
        """Abort a running calibration (STOP on any page calls this)."""
        if self.busy:
            self._abort = "stopped"

    # ---- calibration ----

    def calibrate(self, room, span=60.0, steps=3, levels=3, feed=1500, settle=0.4):
        """Move the head over a steps x steps grid (+-span mm) at its current height and at
        levels-1 lower heights, see the head marker at every stop, fit each camera.

        Start high, with the cup over the middle of the board. `room` is how far (mm) the
        cup is above the board there: the passes go down from the start but stay CLEARANCE
        above the board, and the head goes back up before moving sideways home. Moves are
        slow (feed mm/min) and any trouble aborts with no further moves."""
        if self.grbl.status.get("state") != "Idle":
            return {"ok": False, "error": f"GRBL is {self.grbl.status.get('state')}; unlock it and try again"}
        if room - CLEARANCE < 20:
            return {"ok": False, "error": f"need at least {CLEARANCE + 20:.0f} mm between the cup and the board"}
        dz = (room - CLEARANCE) / (levels - 1)
        self.busy, self._abort = True, None
        try:
            x0, y0, z0 = self._wpos()
            offs = np.linspace(-span, span, steps)
            pts = {i: {"world": [], "pix": []} for i in range(len(self.cameras))}
            last = {}
            for z in [z0 - k * dz for k in range(levels)]:   # Z+ is up: each pass is lower
                self._move(f"G90 G1 Z{z:.3f} F{feed / 2:.0f}")
                for j, dy in enumerate(offs):
                    row = offs if j % 2 == 0 else offs[::-1]
                    for dx in row:
                        self._move(f"G90 G1 X{x0 + dx:.3f} Y{y0 + dy:.3f} F{feed:.0f}")
                        time.sleep(settle)
                        w = self._wpos()
                        for cam in pts:
                            img = self._frame(cam)
                            if img is None:
                                continue
                            found = detect(self._det(cam), img)
                            last[cam] = found
                            if HEAD_ID in found:
                                pts[cam]["world"].append(w)
                                pts[cam]["pix"].append(centre(found[HEAD_ID]).tolist())
            self._move(f"G90 G1 Z{z0:.3f} F{feed / 2:.0f}")      # up first, then home
            self._move(f"G90 G1 X{x0:.3f} Y{y0:.3f} F{feed:.0f}")

            # the board's Z from marker size until the cup touches it (set_table)
            cal = {"at": time.time(), "cams": {}, "table_source": "marker size",
                   "travel_z": z0,   # the start is Z's top: the only height allowed over Mate
                   "grid": {"span": span, "steps": steps, "room": room, "dz": dz, "levels": levels,
                            "start": [x0, y0, z0]}}
            for cam, d in pts.items():
                world, pix = np.array(d["world"]), np.array(d["pix"])
                info = {"seen": len(world), "of": steps * steps * levels}
                if len(world) < 8 or len(set(np.round(world[:, 2], 2))) < 2:
                    info["error"] = "head marker not seen often enough at two or more heights"
                    cal["cams"][str(cam)] = info
                    continue
                P = fit_dlt(world, pix)
                err = [np.linalg.norm(project(P, w) - p) for w, p in zip(world, pix)]
                info.update(P=P.tolist(), rms_px=float(np.sqrt(np.mean(np.square(err)))),
                            camera=camera_position(P).tolist(),
                            board={str(k): v.tolist() for k, v in last.get(cam, {}).items() if k in BOARD_IDS})
                if cam == TABLE_CAM:
                    info["table_z"] = self._table_z(P, last.get(cam, {}))
                cal["cams"][str(cam)] = info
            if not any("P" in c for c in cal["cams"].values()):
                return {"ok": False, "error": "no camera saw the head marker at enough points", "cams": cal["cams"]}
            tz = [c["table_z"] for c in cal["cams"].values() if c.get("table_z") is not None]
            cal["table_z"] = float(np.median(tz)) if tz else None
            CAL_FILE.write_text(json.dumps(cal))
            self.needs_reanchor = False
            with self._lock:
                self.cal = cal
            return {"ok": True, **self.summary()}
        except Aborted as e:
            return {"ok": False, "error": f"calibration stopped: {e}. Nothing else was moved; check the head "
                                          "before going on (the position may be off if it hit something)"}
        finally:
            self.busy = False

    def _table_z(self, P, found):
        """The board's Z, from how big the board markers look."""
        zs = [height_from_size(P, found[i], SIZE["board"]) for i in BOARD_IDS if i in found]
        zs = [z for z in zs if z is not None]
        return float(np.median(zs)) if zs else None

    def summary(self):
        if not self.cal:
            return {"calibrated": False}
        cams = {k: {key: v.get(key) for key in ("seen", "of", "rms_px", "error")} for k, v in self.cal["cams"].items()}
        return {"calibrated": True, "at": self.cal["at"], "table_z": self.cal.get("table_z"),
                "travel_z": self.cal.get("travel_z"),
                "table_source": self.cal.get("table_source"), "needs_reanchor": self.needs_reanchor, "cams": cams,
                "head_error_mm": self.scene.get("head", {}).get("error_mm"),
                "camera_moved_px": self.scene.get("camera_moved_px")}

    def set_table(self):
        """The cup is touching the board now: that's the board's height."""
        if not self.cal:
            return {"ok": False, "error": "calibrate first"}
        if self.grbl.status.get("state") != "Idle":
            return {"ok": False, "error": f"GRBL is {self.grbl.status.get('state')}"}
        z = self._wpos()[2] - TIP_BELOW_MARKER
        with self._lock:
            self.cal["table_z"], self.cal["table_source"] = z, "touch"
            CAL_FILE.write_text(json.dumps(self.cal))
        return {"ok": True, "table_z": z}

    def set_travel(self):
        """Use the current Z as the travel height (the only height allowed over Mate)."""
        if not self.cal:
            return {"ok": False, "error": "calibrate first"}
        z = self._wpos()[2]
        with self._lock:
            self.cal["travel_z"] = z
            CAL_FILE.write_text(json.dumps(self.cal))
        return {"ok": True, "travel_z": z}

    # ---- keeping the head off Mate ----

    def over_mate(self, x0, y0, x1, y1):
        """Does the straight XY path from (x0, y0) to (x1, y1) pass over Mate (plus a margin)?
        False when Mate isn't known (not calibrated, or not in view)."""
        m = self.scene.get("mate") if self.cal else None
        if not m:
            return False
        a = math.radians(m["heading"])
        ux, uy = math.cos(a), math.sin(a)                       # Mate's forward direction
        half = max(MATE_SIZE[0], MATE_SIZE[1]) / 2 + MATE_MARGIN
        n = max(2, int(math.hypot(x1 - x0, y1 - y0) / 5) + 1)  # every 5 mm along the path
        for i in range(n + 1):
            px, py = x0 + (x1 - x0) * i / n - m["x"], y0 + (y1 - y0) * i / n - m["y"]
            if abs(px * ux + py * uy) <= half and abs(-px * uy + py * ux) <= half:
                return True
        return False

    def plan_move(self, x, y, z):
        """Lines for an absolute move to (x, y, z), any of them None = stay. Below travel
        height, a path over Mate first goes up to travel height; ending over Mate below it
        is refused. Returns (lines, None) or (None, why)."""
        w = self._wpos()
        tx, ty, tz = (w[0] if x is None else x), (w[1] if y is None else y), (w[2] if z is None else z)
        travel = (self.cal or {}).get("travel_z")
        if travel is None or self.needs_reanchor or not self.over_mate(w[0], w[1], tx, ty):
            return None, None                                   # nothing to do: move as asked
        if self.over_mate(tx, ty, tx, ty) and tz < travel - 0.5:
            return None, f"that ends over Mate below travel height (Z {travel:.1f})"
        lines = []
        if w[2] < travel - 0.5:
            lines.append(f"G90 G0 Z{travel:.3f}")
        lines.append(f"G90 G0 X{tx:.3f} Y{ty:.3f}")
        if tz < travel - 0.5:
            lines.append(f"G90 G0 Z{tz:.3f}")
        return lines, None

    def jog_ok(self, dx, dy):
        """A relative XY jog below travel height may not pass over Mate."""
        travel = (self.cal or {}).get("travel_z")
        w = self._wpos()
        if travel is None or self.needs_reanchor or w[2] >= travel - 0.5 or (not dx and not dy):
            return True
        return not self.over_mate(w[0], w[1], w[0] + dx, w[1] + dy)

    def _on_grbl(self, ev):
        # a reset makes GRBL forget where it is; until re-anchored, its numbers aren't ours
        text = ev.get("text", "") if ev.get("type") == "log" else ""
        if text.startswith("Grbl "):
            self.needs_reanchor = bool(self.cal)
        if self.busy and (text.startswith(("Grbl ", "ALARM")) or text.startswith("error")):
            self._abort = text

    def _remember(self):
        """Keep the last trustworthy position on disk, for re-anchoring after a reset."""
        if self.needs_reanchor or self.grbl.status.get("state") != "Idle":
            return
        w = [round(v, 3) for v in self._wpos()]
        if w != self.last_pos:
            self.last_pos = w
            POS_FILE.write_text(json.dumps(w))

    # ---- live scene ----

    def _cam(self, cam):
        c = self.cal["cams"].get(str(cam)) if self.cal else None
        return (np.array(c["P"]), c) if c and "P" in c else (None, None)

    def _unbump(self, cal_cam, found):
        """Homography that maps this frame's pixels back to calibration-time pixels, from
        the board markers both frames see. Returns (H or None, max shift in px)."""
        ref = cal_cam.get("board", {})
        a, b = [], []
        for k, v in ref.items():
            if int(k) in found:
                a.extend(found[int(k)])
                b.extend(v)
        if len(a) < 4:
            return None, None
        a, b = np.array(a), np.array(b)
        shift = float(np.max(np.linalg.norm(a - b, axis=1)))
        if shift < BUMP_PX:
            return None, shift
        if len(a) >= 8:
            H, _ = cv2.findHomography(a, b)
        else:
            H = cv2.getPerspectiveTransform(a[:4].astype(np.float32), b[:4].astype(np.float32))
        return H, shift

    def update(self):
        """One pass: look with every calibrated camera, work out the scene."""
        if not self.cal or self.busy:
            return self.scene
        w = self._wpos()
        tz = self.cal.get("table_z")
        scene = {"at": time.time(), "calibrated": True, "table_z": tz, "table_source": self.cal.get("table_source"),
                 "travel_z": self.cal.get("travel_z"),
                 "needs_reanchor": self.needs_reanchor,
                 "head": {"x": w[0], "y": w[1], "z": w[2], "tip_z": w[2] - TIP_BELOW_MARKER, "seen_by": []},
                 "mate": None, "cards": [], "board": {}, "cameras": {}}
        errs = []
        for cam in range(len(self.cameras)):
            P, cc = self._cam(cam)
            if P is None:
                continue
            img = self._frame(cam)
            if img is None:
                continue
            found = detect(self._det(cam), img)
            H, shift = self._unbump(cc, found)
            fix = (lambda pts: cv2.perspectiveTransform(np.asarray(pts, float).reshape(-1, 1, 2), H).reshape(-1, 2)) \
                if H is not None else (lambda pts: np.asarray(pts, float).reshape(-1, 2))
            scene["cameras"][str(cam)] = {"position": cc["camera"], "moved_px": shift,
                                          "markers": sorted(found)}
            if shift is not None:
                scene["camera_moved_px"] = max(scene.get("camera_moved_px") or 0, shift)

            if HEAD_ID in found and self.grbl.status.get("state") == "Idle":
                seen = to_xy(P, fix([centre(found[HEAD_ID])]), w[2])[0]
                e = float(np.hypot(seen[0] - w[0], seen[1] - w[1]))
                errs.append(e)
                scene["head"]["seen_by"].append(cam)
            if tz is None or cam != TABLE_CAM:
                continue
            for i in BOARD_IDS:
                if i in found and str(i) not in scene["board"]:
                    q = to_xy(P, fix(found[i]), tz)
                    scene["board"][str(i)] = {"x": float(q[:, 0].mean()), "y": float(q[:, 1].mean())}
            if MATE_ID in found and scene["mate"] is None:
                c = fix(found[MATE_ID])
                # its height from how big the marker looks: doesn't depend on Z's steps/mm,
                # which isn't measured yet (so MATE_SIZE's height would be in the wrong units)
                z = height_from_size(P, c, SIZE["mate"])
                if z is not None:
                    q = to_xy(P, c, z)
                    top, bottom = (q[0] + q[1]) / 2, (q[2] + q[3]) / 2
                    d = top - bottom
                    scene["mate"] = {"x": float(q[:, 0].mean()), "y": float(q[:, 1].mean()),
                                     "heading": float(math.degrees(math.atan2(d[1], d[0]))),
                                     "height": float(z - tz), "cam": cam}
            scene["cards"] = find_cards(img, P, tz, found, fix, cam)
        if errs:
            scene["head"]["error_mm"] = float(min(errs))
        with self._lock:
            self.scene = scene
        return scene

    def reanchor(self):
        """After a GRBL reset: put the work coordinates back. Z is taken as where it was
        last (a reset doesn't move the head; the upright head plate can't measure height),
        X/Y from where the camera sees the head at that height."""
        if not self.cal:
            return {"ok": False, "error": "not calibrated"}
        if not self.last_pos:
            return {"ok": False, "error": "no last position saved; recalibrate"}
        z = self.last_pos[2]
        for cam in range(len(self.cameras)):
            P, cc = self._cam(cam)
            img = self._frame(cam) if P is not None else None
            if img is None:
                continue
            found = detect(self._det(cam), img)
            if HEAD_ID not in found:
                continue
            H, _ = self._unbump(cc, found)
            c = found[HEAD_ID] if H is None else cv2.perspectiveTransform(
                found[HEAD_ID].reshape(-1, 1, 2), H).reshape(-1, 2)
            x, y = to_xy(P, [centre(c)], z)[0]
            reply = self.grbl.send(f"G10 L20 P1 X{x:.3f} Y{y:.3f} Z{z:.3f}")
            if reply == "ok":
                self.needs_reanchor = False
            return {"ok": reply == "ok", "x": float(x), "y": float(y), "z": float(z), "cam": cam,
                    "was": self.last_pos, "reply": reply}
        return {"ok": False, "error": "no calibrated camera sees the head marker"}

    def run(self, hz=2.0):
        def loop():
            while True:
                t = time.time()
                try:
                    if self.cal and not self.busy:
                        self._remember()
                        self.emit({"type": "scene", **self.update()})
                except Exception as e:  # keep looking even if one frame goes wrong
                    self.emit({"type": "log", "dir": "sys", "text": f"vision: {e}"})
                time.sleep(max(0.05, 1 / hz - (time.time() - t)))
        threading.Thread(target=loop, daemon=True).start()


# ---- cards ----

def find_cards(img, P, tz, markers, fix, cam):
    """Card-sized light rectangles on the dark board, in gantry mm."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = (hsv[:, :, 2] > 90).astype(np.uint8) * 255
    for c in markers.values():   # markers have white borders: blank them out, generously
        m = c.mean(axis=0)
        cv2.fillConvexPoly(mask, ((c - m) * 1.6 + m).astype(np.int32), 0)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cards = []
    for cnt in contours:
        if cv2.contourArea(cnt) < 400:
            continue
        q = to_xy(P, fix(cnt.reshape(-1, 2)), tz).astype(np.float32)
        (cx, cy), (w, h), ang = cv2.minAreaRect(q)
        short, long_ = sorted((w, h))
        if not (0.75 * CARD[0] < short < 1.3 * CARD[0] and 0.75 * CARD[1] < long_ < 1.3 * CARD[1]):
            continue
        # fill ratio: a card is a solid rectangle, a cable loop or a hand isn't
        if cv2.contourArea(q) / (w * h) < 0.8:
            continue
        inner = np.zeros(mask.shape, np.uint8)
        cv2.drawContours(inner, [cnt], -1, 255, -1)
        inner = cv2.erode(inner, np.ones((9, 9), np.uint8))
        hue, sat = hsv[:, :, 0][inner > 0], hsv[:, :, 1][inner > 0]
        blue = float(np.mean((hue > 95) & (hue < 135) & (sat > 70))) if len(hue) else 0.0
        if w < h:
            ang += 90  # angle of the long side
        cards.append({"x": float(cx), "y": float(cy), "angle": float(ang % 180), "w": float(short),
                      "h": float(long_), "face": "down" if blue > 0.25 else "up", "cam": cam})
    return cards
