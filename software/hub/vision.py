"""Where things are on the table, from the cameras, with no external AI.

The gantry is the reference. Calibration moves the head marker (ArUco ID 10)
over a grid at several heights; every stop pairs a known gantry position with where
each camera sees the marker, and a DLT fit gives each camera's full projection
in gantry coordinates (X/Y in mm, Z in GRBL units, Z+ up). After that:

- the head is where GRBL says, and the camera checks it (error in mm);
- a pixel plus a height gives a gantry X/Y, so cards on the board, Esper's
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
RESET_FILE = Path(__file__).parent / "needs_reanchor"      # there while a reset is unresolved, across hub restarts

DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
BOARD_IDS, HEAD_ID, ESPER_ID = (0, 1, 2, 3), 10, 20
# black-square size of the markers as printed now (mm, the Nov 1 sheet); the board and
# Esper ones also give their height, by finding where the camera would see them at that
# size. The head plate stands upright, so its size says nothing about height.
SIZE = {"board": 30.0, "head": 25.0, "esper": 30.0}
# The cup tip is this far below the head marker's centre, in the cameras' frame. A ruler says 77
# (Nov 2), but with 77 the board came out ~7% too big against a tape measure, so something else
# is off too (likely the gantry's steps/mm). 57 is what the board, the cup offset and the picks
# were all tuned with: keep them together, or redo all three.
TIP_BELOW_MARKER = 57.0
PARK = (190.0, 150.0)  # head X/Y out of cam 1's way: the back right (Nov 2; the notes say why)
KEEPOUT = 10.0     # mm around a board marker's square the cup keeps off (its own radius is 7.5)
# Every head position is the marker's centre: calibration fits the cameras to it, GRBL's work
# X/Y/Z are it. The marker is on thin card on the Z extrusion's left face (facing -X, ~1 mm out),
# so the extrusion's centre is ~11.5 mm to its +X. The cup is found from the marker, not the
# extrusion: tip X/Y = head X/Y + this, in vision's frame. Measured Nov 2 by centring the cup over
# two chips 90 mm apart by eye (both needed the same +3 X, -5 Y on the old (0.6, -24.7)); the Y
# matches a ruler (20 mm). The X isn't physical (the cup is in line with the extrusion, ~11 mm +X
# of the card): it's what lands, so it absorbs some of vision's error. Re-measure after calibrating.
# Nov 3 evening, after the head marker was replaced and the cameras recalibrated: centring the cup
# by eye over a chip from 2 mm up said X 2.1, but picks then landed 3 mm left, so -0.9 (+1.5 on the
# old -2.4, what the first look said). Y stays: what looked off in Y was the chip fit's bias (chips.SHIFT).
TIP_OFFSET = (-0.9, -19.7)
CLEARANCE = 15.0          # calibration keeps the cup at least this far above the board (mm)
ESPER_MARGIN = 40.0        # mm around Esper's footprint that counts as "over Esper"
ESPER_TOP = 103.0          # cup height that touches Esper's plywood top (where a card lies; the corner caps stand 2 mm above it)
ESPER_SQUEEZE = 1.5        # how far the cup may press into what's on Esper's top (a card): gentle
TABLE_CAM = 1             # the camera that looks down on the board (cam 0 is too low for it)
ESPER_SIZE = (134.0, 134.0, 105.0)  # mm, over the corner caps: 130 x 130 x 100 box, 3 mm off the ground, caps 2 mm proud
CARD = (63.0, 88.0)       # poker card, mm


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


def triangulate(Ps, pix):
    """One point seen by two or more cameras -> its X, Y, Z (least squares)."""
    A = []
    for P, (u, v) in zip(Ps, pix):
        A += [u * P[2] - P[0], v * P[2] - P[1]]
    X = np.linalg.svd(np.array(A))[2][-1]
    return X[:3] / X[3]


def to_xy(P, pix, z):
    """Pixels -> gantry X/Y on the plane Z = z."""
    H = np.c_[P[:, 0], P[:, 1], P[:, 2] * z + P[:, 3]]
    pts = cv2.perspectiveTransform(np.asarray(pix, float).reshape(-1, 1, 2), np.linalg.inv(H))
    return pts.reshape(-1, 2)


def camera_view(P, size):
    """Where a camera looks, from its projection: forward and up (unit vectors, gantry axes)
    and the rays through the picture's four corners, for drawing it."""
    M = P[:, :3]
    s = np.sign(np.linalg.det(M)) or 1.0
    unit = lambda v: (v / np.linalg.norm(v)).tolist()
    w, h = size
    Minv = np.linalg.inv(M)
    rays = [unit(s * (Minv @ np.array([u, v, 1.0]))) for u, v in ((0, 0), (w, 0), (w, h), (0, h))]
    return {"forward": unit(s * M[2]), "up": unit(-s * M[1]), "rays": rays}


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
    def __init__(self, cameras, grbl, emit, esper=None):
        self.cameras, self.grbl, self.emit, self.esper = cameras, grbl, emit, esper
        self.cal = json.loads(CAL_FILE.read_text()) if CAL_FILE.exists() else None
        if self.cal and "mate_home" in self.cal:
            self.cal.setdefault("esper_home", self.cal.pop("mate_home"))
            CAL_FILE.write_text(json.dumps(self.cal))
        self._reset_flag = False
        self.scene = {"calibrated": bool(self.cal)}
        self.busy = False
        self._abort = None
        self.cards = None    # cards.Cards: names face-up cards from its cache
        self.chips = None    # chips.Chips: chip stacks by colour
        # GRBL reset since the last known position: a banner seen, or GRBL found in alarm on
        # connecting (see grbl.py). Kept on disk so a hub restart doesn't forget it. Opening the
        # port doesn't reset the Uno (`stty -hupcl` in hub.service).
        self.needs_reanchor = CAL_FILE.exists() and (grbl.resets > 0 or RESET_FILE.exists())
        self.last_pos = json.loads(POS_FILE.read_text()) if POS_FILE.exists() else None
        grbl.listeners.append(self._on_grbl)
        self._dets = {}
        self._lock = threading.Lock()

    @property
    def needs_reanchor(self):
        return self._reset_flag

    @needs_reanchor.setter
    def needs_reanchor(self, v):
        self._reset_flag = bool(v)
        try:
            RESET_FILE.touch() if v else RESET_FILE.unlink(missing_ok=True)
        except OSError:
            pass

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

    def calibrate(self, room, span=60.0, steps=3, levels=3, feed=2000, settle=0.25, from_zero=False):
        """Move the head over a steps x steps grid (+-span mm) around where it is, at its current
        height and at levels-1 lower heights, see the head marker at every stop, fit each camera,
        then measure the board markers (set_bounds): the bounds, and X/Y 0, 0 at their middle.
        One press does it all; it works after the camera, the board or Work zero moved.

        Start with the head roughly over the middle of the board and the cup high. With bounds
        known, the head first rises to the travel height (if lower) and the grid shrinks to keep
        the cup inside them (refused below 40 mm: move the head toward the middle). Esper under
        the grid refuses it, when the camera can still tell where Esper is. `room` is how far (mm)
        the cup is above the board at the start: the passes go down but stay CLEARANCE above it,
        and the head goes back up before moving sideways. Sideways moves are rapids (GRBL's top
        speed and acceleration, $110-$121), going down a level at feed (mm/min). Any trouble
        aborts with no further moves.

        from_zero: the person has just touched the cup to the board in the middle and set Work
        zero there (X, Y, Z all 0; refused otherwise). That fixes the board's height (as Zero Z)
        and the grid's middle, whatever was saved before: old bounds are ignored, new ones measured
        without moving X/Y 0, 0. The head rises to the travel height (110 if none) first."""
        if self.grbl.status.get("state") != "Idle":
            return {"ok": False, "error": f"GRBL is {self.grbl.status.get('state')}; unlock it and try again"}
        if self.needs_reanchor:
            return {"ok": False, "error": "GRBL was reset: re-anchor first"}
        x0, y0, z0 = self._wpos()
        b = (self.cal or {}).get("bounds")
        lift = None
        travel = (self.cal or {}).get("travel_z")
        if from_zero:
            if max(abs(x0), abs(y0), abs(z0)) > 0.05:
                return {"ok": False, "error": f"the head is at {x0:.1f}, {y0:.1f}, {z0:.1f}: jog the cup down until it "
                                              "just touches the board in the middle, Work zero X, Y and Z there, then calibrate"}
            b, room, travel = None, 0.0, travel if travel is not None else 110.0
        if travel is not None and z0 < travel:
            lift, room = travel, room + travel - z0
            z0 = travel
        if b:
            cx, cy = x0 + TIP_OFFSET[0], y0 + TIP_OFFSET[1]       # the cup, over the grid's middle
            fit = min(cx - b[0], b[1] - cx, cy - b[2], b[3] - cy)
            if fit < 40:
                return {"ok": False, "error": f"the head is too near the board's edge for a grid ({fit:.0f} mm "
                                              "of room): move it toward the middle"}
            span = min(span, fit)
        moved = (self.scene or {}).get("camera_moved_px") or 0
        m = self.scene.get("esper") if moved < 30 else None    # a moved camera puts Esper in the wrong place
        if m and not m.get("assumed"):
            half = max(ESPER_SIZE[:2]) / 2 + ESPER_MARGIN
            cx, cy = x0 + TIP_OFFSET[0], y0 + TIP_OFFSET[1]
            if abs(m["x"] - cx) < span + half and abs(m["y"] - cy) < span + half:
                return {"ok": False, "error": "Esper is under the grid: drive it home first"}
        if room - CLEARANCE < 20:
            return {"ok": False, "error": f"need at least {CLEARANCE + 20:.0f} mm between the cup and the board"}
        dz = (room - CLEARANCE) / (levels - 1)
        self.busy, self._abort = True, None
        try:
            if lift is not None:
                self._move(f"G90 G1 Z{lift:.3f} F{feed:.0f}")
            self._move(f"G90 G0 X{x0:.3f} Y{y0:.3f}")
            offs = np.linspace(-span, span, steps)
            pts = {i: {"world": [], "pix": []} for i in range(len(self.cameras))}
            done, total = 0, steps * steps * levels
            self.emit({"type": "calibrate", "stop": 0, "of": total})
            seen = {}    # board markers at every stop: the head hides one now and then
            for z in [z0 - k * dz for k in range(levels)]:   # Z+ is up: each pass is lower
                self._move(f"G90 G1 Z{z:.3f} F{feed:.0f}")
                for j, dy in enumerate(offs):
                    row = offs if j % 2 == 0 else offs[::-1]
                    for dx in row:
                        self._move(f"G90 G0 X{x0 + dx:.3f} Y{y0 + dy:.3f}")   # rapid: GRBL's top speed, its acceleration
                        time.sleep(settle)
                        w = self._wpos()
                        for cam in pts:
                            img = self._frame(cam)
                            if img is None:
                                continue
                            found = detect(self._det(cam), img)
                            for k in found.keys() & set(BOARD_IDS):
                                seen.setdefault(cam, {}).setdefault(k, []).append(np.asarray(found[k], float))
                            if HEAD_ID in found:
                                pts[cam]["world"].append(w)
                                pts[cam]["pix"].append(centre(found[HEAD_ID]).tolist())
                        done += 1
                        self.emit({"type": "calibrate", "stop": done, "of": total,
                                   "seen": {str(k): len(v["world"]) for k, v in pts.items()}})
            # each board marker where it usually was (median of its corners over the stops)
            last = {cam: {k: np.median(v, axis=0) for k, v in ms.items() if len(v) * 2 >= steps * steps * levels}
                    for cam, ms in seen.items()}
            self._move(f"G90 G1 Z{z0:.3f} F{feed:.0f}")      # up first, then back to the middle
            self._move(f"G90 G0 X{x0:.3f} Y{y0:.3f}")

            # the board's Z from marker size until the cup touches it (set_table)
            cal = {"at": time.time(), "cams": {}, "table_source": "marker size",
                   "travel_z": z0,   # the start is Z's top: the only height allowed over Esper
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
            # a board touch-off is in GRBL's Z, which recalibrating the cameras doesn't change
            # (only Work zero would; don't use it after calibrating): keep it, and the bounds
            if from_zero:                                       # the cup touched the board at Z 0
                cal["table_z"], cal["table_source"] = -TIP_BELOW_MARKER, "touch"
            elif self.cal and self.cal.get("table_source") == "touch":
                cal["table_z"], cal["table_source"] = self.cal["table_z"], "touch"
            if self.cal and self.cal.get("travel_z") is not None:   # a chosen travel height stays
                cal["travel_z"] = self.cal["travel_z"]
            if self.cal and self.cal.get("esper_home") and not from_zero:   # after a new zero it's in the old X/Y
                cal["esper_home"] = self.cal["esper_home"]
            CAL_FILE.write_text(json.dumps(cal))
            self.needs_reanchor = False
            with self._lock:
                self.cal = cal
            # the head out of cam 1's way (over the middle it hides markers, and a half-hidden one is
            # recorded off: bad bounds, and a "camera moved" warning that never goes away), then the board
            self._move(f"G90 G0 X{PARK[0]:.3f} Y{PARK[1]:.3f}")
            time.sleep(0.5)
            bounds = self.set_bounds(center=not from_zero)   # the board's edges (from zero: 0, 0 stays where it was set)
            return {"ok": True, **self.summary(), "grid_span": span, "bounds_measured": bounds}
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
                "travel_z": self.cal.get("travel_z"), "bounds": self.cal.get("bounds"),
                "table_source": self.cal.get("table_source"), "needs_reanchor": self.needs_reanchor, "cams": cams,
                "head_error_mm": self.scene.get("head", {}).get("error_mm"),
                "camera_moved_px": self.scene.get("camera_moved_px")}

    def save(self):
        with self._lock:
            CAL_FILE.write_text(json.dumps(self.cal))

    def set_table(self):
        """The cup is touching the board now: make that Z 0 (G10). Z is the cup's height above
        the board everywhere (limits, travel height, picks).
        Board already touched off: the cameras were fitted with Z 0 at the board, so this is the
        fix for a Z that skipped steps (a lift that stalled), and they stay as they are.
        Not yet (a fresh calibration, board height from marker size): the cameras were fitted
        in the old Z, so they're shifted to the new one along with the travel height."""
        if not self.cal:
            return {"ok": False, "error": "calibrate first"}
        if self.grbl.status.get("state") != "Idle":
            return {"ok": False, "error": f"GRBL is {self.grbl.status.get('state')}"}
        was = self._wpos()[2]
        reply = self.grbl.send("G10 L20 P1 Z0")
        if reply != "ok":
            return {"ok": False, "error": f"GRBL said {reply}"}
        with self._lock:
            if self.cal.get("table_source") != "touch":
                shift = np.eye(4)
                shift[2, 3] = was                      # old Z = new Z + was
                for c in self.cal["cams"].values():
                    if "P" in c:
                        c["P"] = (np.array(c["P"]) @ shift).tolist()
                        c["camera"] = [c["camera"][0], c["camera"][1], c["camera"][2] - was]
                if self.cal.get("travel_z") is not None:
                    self.cal["travel_z"] -= was
            self.cal["table_z"], self.cal["table_source"] = -TIP_BELOW_MARKER, "touch"
            CAL_FILE.write_text(json.dumps(self.cal))
        return {"ok": True, "table_z": self.cal["table_z"], "z_was": round(was, 2)}

    def set_travel(self, z=None):
        """Set the travel height: the cup height (work Z) that's safe over Esper. Default: here."""
        if not self.cal:
            return {"ok": False, "error": "calibrate first"}
        z = self._wpos()[2] if z is None else float(z)
        with self._lock:
            self.cal["travel_z"] = z
            CAL_FILE.write_text(json.dumps(self.cal))
        return {"ok": True, "travel_z": z}

    # ---- where the cup may go ----

    def set_bounds(self, border=5.0, center=True):
        """Measure the board markers now and save the cup's allowed X/Y: out to the markers' outer
        edges, the whole margin, less a keep-out around each marker (the cup never goes over one). Needs
        markers on opposite sides; two diagonal corners are enough. center: also move X/Y 0, 0
        to the middle of that rectangle (see shift_origin)."""
        if not self.cal or self.cal.get("table_z") is None:
            return {"ok": False, "error": "calibrate and touch off the board first"}
        P, _ = self._cam(TABLE_CAM)
        img = self._frame(TABLE_CAM) if P is not None else None
        if img is None:
            return {"ok": False, "error": f"camera {TABLE_CAM} isn't calibrated"}
        found = {i: c for i, c in detect(self._det(TABLE_CAM), img).items() if i in BOARD_IDS}
        quads = {i: to_xy(P, c, self.cal["table_z"]) for i, c in found.items()}
        if len(quads) < 2:
            return {"ok": False, "error": f"camera {TABLE_CAM} sees {len(quads)} board marker(s); need two opposite corners"}
        mid = np.mean([q.mean(axis=0) for q in quads.values()], axis=0)
        left = [q for q in quads.values() if q.mean(axis=0)[0] < mid[0]]
        right = [q for q in quads.values() if q.mean(axis=0)[0] >= mid[0]]
        low = [q for q in quads.values() if q.mean(axis=0)[1] < mid[1]]
        high = [q for q in quads.values() if q.mean(axis=0)[1] >= mid[1]]
        if not (left and right and low and high):
            return {"ok": False, "error": "the markers it sees aren't on opposite corners"}
        # the play area runs out to the markers' outer edges (the whole margin); the cup keeps off
        # the markers themselves (KEEPOUT around each square)
        b = [min(q[:, 0].min() for q in left), max(q[:, 0].max() for q in right),
             min(q[:, 1].min() for q in low), max(q[:, 1].max() for q in high)]
        b = [round(float(v), 1) for v in b]
        if b[1] - b[0] < 200 or b[3] - b[2] < 200:          # two markers on one side aren't opposite corners
            return {"ok": False, "error": f"the markers it sees ({', '.join(map(str, sorted(quads)))}) don't span the board: "
                                          "park the head out of the way and measure again"}
        keep = [[round(float(q[:, 0].min()) - KEEPOUT, 1), round(float(q[:, 0].max()) + KEEPOUT, 1),
                 round(float(q[:, 1].min()) - KEEPOUT, 1), round(float(q[:, 1].max()) + KEEPOUT, 1)] for q in quads.values()]
        with self._lock:
            self.cal["bounds"], self.cal["keepout"] = b, keep
            # the markers are where they are now: that's the new reference for "camera moved"
            self.cal["cams"][str(TABLE_CAM)]["board"] = {str(i): c.tolist() for i, c in found.items()}
            CAL_FILE.write_text(json.dumps(self.cal))
        shift = None
        if center:
            shift = self.shift_origin((b[0] + b[1]) / 2, (b[2] + b[3]) / 2)
            if not shift.get("ok"):
                return shift
            b = self.cal["bounds"]
        return {"ok": True, "bounds": {"x": b[:2], "y": b[2:]}, "markers": sorted(quads),
                "origin_moved_by": shift and shift["moved_by"]}

    def shift_origin(self, cx, cy):
        """Make the point (cx, cy) the new X/Y 0, 0. A pure shift: GRBL's work coordinates, the
        camera models, the bounds, the saved position and the calibration grid all move together,
        so nothing needs recalibrating. Z isn't touched."""
        if self.grbl.status.get("state") != "Idle" or self.needs_reanchor:
            return {"ok": False, "error": "GRBL must be idle and anchored"}
        w = self._wpos()
        reply = self.grbl.send(f"G10 L20 P1 X{w[0] - cx:.3f} Y{w[1] - cy:.3f}")
        if reply != "ok":
            return {"ok": False, "error": f"GRBL answered {reply}"}
        T = np.eye(4)
        T[0, 3], T[1, 3] = cx, cy                    # new coords + (cx, cy) = old coords
        with self._lock:
            for c in self.cal["cams"].values():
                if "P" in c:
                    c["P"] = (np.array(c["P"]) @ T).tolist()
                    c["camera"] = camera_position(np.array(c["P"])).tolist()
            if self.cal.get("esper_home"):
                h = self.cal["esper_home"]
                self.cal["esper_home"] = [round(h[0] - cx, 1), round(h[1] - cy, 1), h[2]]
            if self.cal.get("bounds"):
                b = self.cal["bounds"]
                self.cal["bounds"] = [round(b[0] - cx, 1), round(b[1] - cx, 1), round(b[2] - cy, 1), round(b[3] - cy, 1)]
            self.cal["keepout"] = [[round(k[0] - cx, 1), round(k[1] - cx, 1), round(k[2] - cy, 1), round(k[3] - cy, 1)]
                                   for k in self.cal.get("keepout", [])]
            g = self.cal.get("grid", {}).get("start")
            if g:
                g[0], g[1] = g[0] - cx, g[1] - cy
            CAL_FILE.write_text(json.dumps(self.cal))
            if self.last_pos:
                self.last_pos = [round(self.last_pos[0] - cx, 3), round(self.last_pos[1] - cy, 3), self.last_pos[2]]
                POS_FILE.write_text(json.dumps(self.last_pos))
        return {"ok": True, "moved_by": [round(cx, 1), round(cy, 1)]}

    def cup_in_bounds(self, hx, hy):
        """Is the cup inside the board bounds when the head is at (hx, hy)? True if none are set."""
        b = (self.cal or {}).get("bounds")
        if not b:
            return True
        cx, cy = hx + TIP_OFFSET[0], hy + TIP_OFFSET[1]
        return b[0] <= cx <= b[1] and b[2] <= cy <= b[3] and \
            not any(k[0] <= cx <= k[1] and k[2] <= cy <= k[3] for k in self.cal.get("keepout", []))

    def clip_jog(self, dx, dy):
        """Shorten an X/Y jog so the cup stops at the board bounds. Returns (dx, dy)."""
        b = (self.cal or {}).get("bounds")
        if not b or (not dx and not dy) or self.needs_reanchor:
            return dx, dy
        w = self._wpos()
        cx, cy = w[0] + TIP_OFFSET[0], w[1] + TIP_OFFSET[1]
        t = 1.0
        for c, d, lo, hi in ((cx, dx, b[0], b[1]), (cy, dy, b[2], b[3])):
            if d > 0:
                t = min(t, max(0.0, (hi - c) / d))
            elif d < 0:
                t = min(t, max(0.0, (lo - c) / d))
        if t and any(k[0] <= cx + dx * t <= k[1] and k[2] <= cy + dy * t <= k[3] for k in self.cal.get("keepout", [])):
            return 0.0, 0.0                              # it would end on a marker
        return dx * t, dy * t

    # ---- keeping the head off Esper ----

    def over_esper(self, x0, y0, x1, y1):
        """Does the cup's straight XY path from (x0, y0) to (x1, y1) pass over Esper (plus a
        margin)? Head coordinates in; the cup's offset is added here. False when Esper isn't
        known (not calibrated, or not in view)."""
        m = self.scene.get("esper") if self.cal else None
        if not m:
            return False
        a = math.radians(m["heading"])
        ux, uy = math.cos(a), math.sin(a)                       # Esper's forward direction
        half = max(ESPER_SIZE[0], ESPER_SIZE[1]) / 2 + ESPER_MARGIN
        n = max(2, int(math.hypot(x1 - x0, y1 - y0) / 5) + 1)  # every 5 mm along the path
        for i in range(n + 1):
            px = x0 + (x1 - x0) * i / n + TIP_OFFSET[0] - m["x"]
            py = y0 + (y1 - y0) * i / n + TIP_OFFSET[1] - m["y"]
            if abs(px * ux + py * uy) <= half and abs(-px * uy + py * ux) <= half:
                return True
        return False

    # Esper may get nudged sideways by accident; what must never happen is the cup pressing
    # down into it. So the cup never goes lower over Esper than its top minus a gentle squeeze
    # (enough to put a card on it and pick one off), and moves that cross Esper below travel
    # height go up first (no reason to bump it on purpose).

    def plan_move(self, x, y, z):
        """Lines for an absolute move to (x, y, z), any of them None = stay. A path that crosses
        Esper below travel height goes up to travel height first, then across, then down; ending
        over Esper lower than its top minus ESPER_SQUEEZE is refused. Returns (lines, None) or
        (None, why)."""
        w = self._wpos()
        tx, ty, tz = (w[0] if x is None else x), (w[1] if y is None else y), (w[2] if z is None else z)
        travel = (self.cal or {}).get("travel_z")
        if travel is None or self.needs_reanchor or not self.over_esper(w[0], w[1], tx, ty):
            return None, None                                   # nothing to do: move as asked
        floor = ESPER_TOP - ESPER_SQUEEZE
        if self.over_esper(tx, ty, tx, ty) and tz < floor:
            return None, f"that would press into Esper (lowest over Esper: Z {floor:.1f})"
        if abs(tx - w[0]) < 0.01 and abs(ty - w[1]) < 0.01:      # straight up or down over Esper
            return [f"G90 G0 Z{tz:.3f}"], None
        lines = []
        if w[2] < travel - 0.5:
            lines.append(f"G90 G0 Z{travel:.3f}")
        lines.append(f"G90 G0 X{tx:.3f} Y{ty:.3f}")
        if abs(tz - max(w[2], travel)) > 0.01:
            lines.append(f"G90 G0 Z{tz:.3f}")
        return lines, None

    def head_for_tip(self, x, y):
        """Head X/Y that puts the cup tip at (x, y)."""
        return x - TIP_OFFSET[0], y - TIP_OFFSET[1]

    def jog_ok(self, dx, dy, dz):
        """Jogs may go sideways anywhere (bumping Esper is survivable); a jog that lowers the cup
        over Esper below its top minus ESPER_SQUEEZE is refused."""
        w = self._wpos()
        if not self.cal or self.needs_reanchor or dz >= 0 or w[2] + dz >= ESPER_TOP - ESPER_SQUEEZE:
            return True
        return not self.over_esper(w[0] + dx, w[1] + dy, w[0] + dx, w[1] + dy)

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
        """How far the board markers have moved in the picture since they were last recorded
        (calibration or bounds). Returns (H, max shift in px); H is always None now.

        This used to also return a correction (a homography back to the recorded pixels), on
        the idea that only a bumped camera moves the markers in the picture. But a moved board
        or marker does too, and then the "correction" warps everything (Nov 1: marker 1 read
        as 667, 600). So it only reports; a big shift means recalibrate, or re-measure the
        bounds if the markers were moved on purpose."""
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
        return None, shift

    def update(self):
        """One pass: look with every calibrated camera, work out the scene."""
        if not self.cal or self.busy:
            return self.scene
        w = self._wpos()
        tz = self.cal.get("table_z")
        scene = {"at": time.time(), "calibrated": True, "table_z": tz, "table_source": self.cal.get("table_source"),
                 "travel_z": self.cal.get("travel_z"), "bounds": self.cal.get("bounds"),
                 "esper_home": self.cal.get("esper_home"), "needs_reanchor": self.needs_reanchor,
                 "saved_position": self.last_pos if self.needs_reanchor else None,
                 "head": {"x": w[0], "y": w[1], "z": w[2], "tip_x": w[0] + TIP_OFFSET[0], "tip_y": w[1] + TIP_OFFSET[1],
                          "tip_z": w[2] - TIP_BELOW_MARKER, "seen_by": []},
                 "esper": None, "cards": [], "chips": [], "decks": [], "board": {}, "cameras": {}}
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
            ih, iw = img.shape[:2]          # not h, w: w is the head's position
            scene["cameras"][str(cam)] = {"position": cc["camera"], "moved_px": shift, "markers": sorted(found),
                                          "model": self.cameras[cam].model, **camera_view(P, (iw, ih))}
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
            if ESPER_ID in found and scene["esper"] is None:
                c = fix(found[ESPER_ID])
                # its height from how big the marker looks: doesn't depend on Z's steps/mm,
                # which isn't measured yet (so ESPER_SIZE's height would be in the wrong units)
                z = height_from_size(P, c, SIZE["esper"])
                if z is not None:
                    q = to_xy(P, c, z)
                    top, bottom = (q[0] + q[1]) / 2, (q[2] + q[3]) / 2
                    d = top - bottom
                    st = self.esper.status if self.esper else None
                    scene["esper"] = {"x": float(q[:, 0].mean()), "y": float(q[:, 1].mean()),
                                     "heading": float(math.degrees(math.atan2(d[1], d[0]))),
                                     "height": float(z - tz), "cam": cam,
                                     "flipper": st.get("servo_now") if st else None,
                                     "moving": st.get("busy") if st else None}
            scene["cards"] = self._steady(find_cards(img, P, tz, found, fix, cam))
            if self.cards:
                unfix = None if H is None else (lambda pts, Hi=np.linalg.inv(H): cv2.perspectiveTransform(
                    np.asarray(pts, float).reshape(-1, 1, 2), Hi).reshape(-1, 2))
                self.cards.label(img, P, tz, scene["cards"], unfix)
            if self.chips:
                scene["chips"] = self.chips.find(img, P, tz, scene["board"], scene["cards"])
                scene["decks"] = self.chips.decks(img, P, tz, scene["board"], scene["cards"])   # takes out cards that are decks
        if self.esper:
            m = scene["esper"]
            if m:
                self.esper.seen((m["x"], m["y"], m["heading"]))
            elif self.esper.pose:                          # unseen: where it was, plus moves since
                x, y, h = self.esper.pose
                scene["esper"] = {"x": x, "y": y, "heading": h, "assumed": True}
        if errs:
            scene["head"]["error_mm"] = float(min(errs))
        with self._lock:
            self.scene = scene
        return scene

    CARD_HOLD_S = 1.0   # a card missed for up to this long is still there: one bad frame doesn't make it vanish

    def _steady(self, cards):
        """Cards over a few frames (2 a second): one missed for a moment is kept (held: true), and one
        that was face down a moment ago stays face down through a one-frame "face up"."""
        now, mem = time.time(), getattr(self, "_card_mem", [])
        near = lambda a, b: math.hypot(a["x"] - b["x"], a["y"] - b["y"]) < 15
        out, keep = [], []
        for c in cards:
            was = next((m for m in mem if near(m["card"], c)), None)
            if was and c["face"] == "up" and now - was["down_at"] < self.CARD_HOLD_S:
                c["face"] = "down"
            keep.append({"card": c, "at": now, "down_at": now if c["face"] == "down" else (was or {}).get("down_at", 0)})
            out.append(c)
        for m in mem:
            if now - m["at"] < self.CARD_HOLD_S and not any(near(m["card"], c) for c in cards):
                out.append({**m["card"], "held": True})
                keep.append(m)
        self._card_mem = keep
        return out

    def reanchor(self, use_camera=False):
        """After a GRBL reset: put the work coordinates back.

        By default the saved position: a reset or hub restart doesn't move the head, so it's
        exact. The camera's view is reported alongside as a check, but at the edges of the
        calibration (high up, far out) it can be centimetres off, so it never overrides on
        its own. use_camera=True is for when the head really moved (skipped steps, moved by
        hand): X/Y from the cameras, triangulated when two or more see the marker (one alone
        reads it at GRBL's current Z), and Z stays GRBL's current count (Z rarely skips; the
        triangulated Z is reported as a check)."""
        if not self.cal:
            return {"ok": False, "error": "not calibrated"}
        if not self.last_pos:
            return {"ok": False, "error": "no saved position; recalibrate"}
        x, y, z = self.last_pos
        if use_camera:
            z = self._wpos()[2]
        seen, cam_used, views = None, None, []
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
            views.append((P, centre(c)))
            if seen is None:
                seen, cam_used = to_xy(P, [centre(c)], z)[0], cam
        seen_z = None
        if len(views) >= 2:
            seen_x, seen_y, seen_z = triangulate(*zip(*views))
            seen, cam_used = (seen_x, seen_y), "all"
        off = None if seen is None else float(np.hypot(seen[0] - x, seen[1] - y))
        if use_camera:
            if seen is None:
                return {"ok": False, "error": "no calibrated camera sees the head marker"}
            x, y = float(seen[0]), float(seen[1])
        reply = self.grbl.send(f"G10 L20 P1 X{x:.3f} Y{y:.3f} Z{z:.3f}")
        if reply == "ok":
            self.needs_reanchor = False
        return {"ok": reply == "ok", "x": x, "y": y, "z": z, "used": "camera" if use_camera else "saved position",
                "saved": self.last_pos, "camera_off_mm": off, "cam": cam_used,
                "camera_z": None if seen_z is None else round(float(seen_z), 1), "reply": reply}

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

BACK_HSV = ((95, 135), 35, 140)  # a card back's blue panel: hue, saturation over, brightness over (cam 1, Nov 3: backs read ~200; glare on the mat is bluish and ~97)
BACK_MM = ((40, 70), (62, 92))   # its panel's size inside the white border (a card is 63 x 88; it reads 52 x 76, up to 64 x 84 when glare joins in)


def _card_px(P, tz, c, grow=0.0):
    """A lying card's outline in the picture (pixels), grown by `grow` mm."""
    a = np.radians(c["angle"])
    u = np.array([np.cos(a), np.sin(a)]) * (CARD[1] / 2 + grow)
    v = np.array([-np.sin(a), np.cos(a)]) * (CARD[0] / 2 + grow)
    m = np.array([c["x"], c["y"]])
    return np.array([project(P, (*p, tz)) for p in (m - u - v, m - u + v, m + u + v, m + u - v)]).astype(np.int32)


def _backs(hsv, P, tz, fix, cam):
    """Face-down cards: each blue back panel of a card's size, even where cards touch."""
    (h0, h1), smin, vmin = BACK_HSV
    h, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    m = ((h > h0) & (h < h1) & (sat > smin) & (val > vmin)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))   # the back's printed pattern splits it
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    out = []
    for cnt in cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        if cv2.contourArea(cnt) < 400:
            continue
        q = to_xy(P, fix(cnt.reshape(-1, 2)), tz).astype(np.float32)
        (cx, cy), (w, hh), ang = cv2.minAreaRect(q)
        short, long_ = sorted((w, hh))
        if not (BACK_MM[0][0] < short < BACK_MM[0][1] and BACK_MM[1][0] < long_ < BACK_MM[1][1]):
            continue
        if cv2.contourArea(q) / (w * hh) < 0.7:
            continue
        if w < hh:
            ang += 90
        out.append({"x": float(cx), "y": float(cy), "angle": float(ang % 180), "w": CARD[0], "h": CARD[1],
                    "face": "down", "blue": 1.0, "cam": cam})
    return out


def _split(cnt, shape, P, tz, fix):
    """A bright patch much bigger than a card is cards touching (a row dealt close): cut it where it's
    narrowest (watershed on the distance to its edge) into pieces; a card-sized patch stays whole."""
    q = to_xy(P, fix(cnt.reshape(-1, 2)), tz).astype(np.float32)
    (_, _), (w, h), _ = cv2.minAreaRect(q)
    if max(w, h) < 1.4 * CARD[1] and min(w, h) < 1.4 * CARD[0]:
        return [cnt]
    x, y, bw, bh = cv2.boundingRect(cnt)
    m = np.zeros((bh + 2, bw + 2), np.uint8)
    cv2.drawContours(m, [cnt - (x - 1, y - 1)], -1, 255, -1)
    d = cv2.distanceTransform(m, cv2.DIST_L2, 5)
    sure = (d > 0.6 * d.max()).astype(np.uint8)               # each card's middle, apart from the others
    n, markers = cv2.connectedComponents(sure)
    if n <= 2:
        return [cnt]
    markers = markers + 1
    markers[(m > 0) & (sure == 0)] = 0
    markers = cv2.watershed(cv2.cvtColor(m, cv2.COLOR_GRAY2BGR), markers)
    out = []
    for k in range(2, n + 1):
        cs, _ = cv2.findContours((markers == k).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if cs:
            out.append(max(cs, key=cv2.contourArea) + (x - 1, y - 1))
    return out


def find_cards(img, P, tz, markers, fix, cam):
    """Card-sized light rectangles on the dark board, in gantry mm."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = (hsv[:, :, 2] > 90).astype(np.uint8) * 255
    for c in markers.values():   # markers have white borders: blank them out, generously
        m = c.mean(axis=0)
        cv2.fillConvexPoly(mask, ((c - m) * 1.6 + m).astype(np.int32), 0)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    # face-down cards first: a back is a blue panel inside a white border; touching cards' borders run
    # together, but each panel stays apart. Then cut them out, and what's left is the face-up cards.
    cards = _backs(hsv, P, tz, fix, cam)
    for c in cards:
        cv2.fillConvexPoly(mask, _card_px(P, tz, c, 3.0), 0)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = [p for c in contours for p in _split(c, mask.shape, P, tz, fix)]
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
                      "h": float(long_), "face": "down" if blue > 0.25 else "up", "blue": round(blue, 2), "cam": cam})
    return cards
