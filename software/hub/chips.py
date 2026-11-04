"""Chip stacks and decks for free: on the dark mat a red or white chip is a patch of its colour; each patch's
outline in cam 1 is fitted with an upright 40 mm cylinder (eyes.upright), which gives where the
stack really stands and how tall it is: how many chips. No API. A patch that doesn't fit a
cylinder well isn't a stack (Esper, the deck's edge) or is two stacks touching: left out.

A deck is the same with a box: a light patch the card finder turned down (too big: its side
shows), fitted with an upright 63 x 88 box (eyes.upright_box), or one it took for a card: a thin deck
looks like one from above. 5 mm or more is a deck (Nov 3: flat single cards fit 0-1.8 mm, a
curled one 4.1: a deck of fewer than ~10 cards still shows as a card).

A patch that's where it was (same place and size in the picture) keeps its answer: the fit is
only done for a new or moved one."""
import cv2
import numpy as np

import eyes
from vision import CARD, project, to_xy

RED_S, RED_V = 100, 60     # red: this saturated (0-255) and not darker than this
WHITE_V, WHITE_S = 110, 60 # white: brighter than this, and less coloured
MIN_PX = 800               # smaller patches aren't a chip (a single chip is ~2000 px in cam 1)
MARGIN_MM = 25             # beyond a marker's centre, out to its outer edge: chips there count
LEAN_MM = 60               # how far past the board a stack's outline may reach in the picture (its height leans away)
MARKER_MM = 30             # around a board marker's centre: its white border, not a chip
CARD_GROW = 3              # mm around a card that's the card, not a chip
SHIFT = (0.0, 2.3)         # mm added to a stack's fitted x, y: the cup centred over flat cards but landed 0-4 mm
                           # toward the front of six stacks (Nov 3, mean 2.3), so it's the stack fit, not the cup
FIT = 0.80                 # a stack fits 0.86-0.96; Esper, the deck's edge, touching stacks 0.5 or less
SAME_PX, SAME_AREA = 3, 0.04   # a patch this close to one already fitted is the same stack
DECK_V = 90                # a deck's back and edges: brighter than this (as the card finder)
DECK_MIN_MM = 5.0          # a box this tall is a deck, not a card (a curled card fits ~4)
DECK_FLAT = (0.8, 1.6)     # its flat footprint: this much of a card's, each side (a big patch isn't one)
CARD_MM = 0.5              # how much one card adds to a deck: this deck's old cards are curled, so they stack loose
                           # (Nov 3: 33 cards fit 15.8-16.8 mm; cam 0 saw 16.3). A new, flat deck: ~0.3


def _same(known, c):
    """The earlier answer for this patch if it's where it was (same centre and size), else "new"."""
    area, mo = cv2.contourArea(c), cv2.moments(c)
    at = np.array([mo["m10"] / mo["m00"], mo["m01"] / mo["m00"]])
    was = next((r for p, a, r in known if np.hypot(*(p - at)) < SAME_PX and abs(a - area) < SAME_AREA * area), "new")
    return at, area, was


def mat_corners(markers, grow=None):
    """The board markers' centres, all four: a hidden one (the deck, the crane in front of it)
    is where the other three put it, the board being a rectangle. None with fewer than three."""
    pts = [np.array([c["x"], c["y"]]) for c in markers.values()]
    if len(pts) == 3:
        d = [(np.hypot(*(pts[i] - pts[j])), i, j) for i in range(3) for j in range(i + 1, 3)]
        _, i, j = max(d)                                   # the diagonal; the third is the corner between
        k = 3 - i - j
        pts.append(pts[i] + pts[j] - pts[k])
    if len(pts) < 4:
        return None
    mid = np.mean(pts, axis=0)                             # out to the markers' outer edges: the margin is play area too
    grow = MARGIN_MM if grow is None else grow
    return [p + (p - mid) / np.linalg.norm(p - mid) * grow for p in pts]


class Chips:
    def __init__(self):
        self.known = []            # [(centre px, area px, result or None)]
        self.known_decks = []

    def decks(self, img, P, tz, markers, cards):
        """The decks: [{x, y, angle, height_mm, cards, fit}], where they really stand. A card of
        `cards` that's really a deck is taken out of it."""
        m = (cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 2] > DECK_V).astype(np.uint8)
        pix = lambda pts, z=tz: np.array([project(P, (x, y, z)) for x, y in pts], np.float32)
        ring = np.linspace(0, 2 * np.pi, 24, endpoint=False)
        for c in markers.values():
            cv2.fillConvexPoly(m, pix(np.c_[c["x"] + MARKER_MM * np.cos(ring), c["y"] + MARKER_MM * np.sin(ring)]).astype(np.int32), 0)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        known, out = [], []
        for c in cs:
            if cv2.contourArea(c) < 4 * MIN_PX:
                continue
            o = cv2.approxPolyDP(c, 1.5, True).reshape(-1, 2)
            q = to_xy(P, o.astype(float), tz).astype(np.float32)
            (cx, cy), (w, h), a = cv2.minAreaRect(q)
            if w < h:
                a += 90
            w, h = sorted((w, h))
            if not (DECK_FLAT[0] * CARD[0] < w < DECK_FLAT[1] * CARD[0] and DECK_FLAT[0] * CARD[1] < h < DECK_FLAT[1] * CARD[1]):
                continue
            # a deck's top is a card back too: the card finder takes it for a card, near its flat middle
            card = next((k for k in cards if abs(cx - k["x"]) < 25 and abs(cy - k["y"]) < 25), None)
            at, area, was = _same(self.known_decks, c)
            if was == "new":
                x, y, ang, hh, fit = eyes.upright_box(P, o, tz, CARD[0], CARD[1], (cx, cy), a % 180)
                was = {"x": round(x, 1), "y": round(y, 1), "angle": round(ang, 1), "height_mm": round(hh, 1),
                       "cards": round(hh / CARD_MM), "fit": round(fit, 2)} if fit >= FIT and hh >= DECK_MIN_MM else None
            known.append((at, area, was))
            if was:
                out.append(was)
                if card is not None:
                    cards.remove(card)
        self.known_decks = known
        return out

    def find(self, img, P, tz, markers, cards):
        """The stacks on the mat: [{x, y, height_mm, count, count_raw, sure, pick_z, place_z, colour, fit}]
        (count_raw: before rounding, so a borderline one shows; pick_z, place_z: see eyes.cup_heights). One colour a stack: a
        white chip on red splits into its white top and a scrap of red side (a pale seam between),
        and the top alone fits as a short stack. markers: the board markers' {id: {x, y}}; cards:
        the scene's cards (cut out first)."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h, s, v = (hsv[..., k].astype(np.int16) for k in range(3))
        red = ((h < 10) | (h > 165)) & (s > RED_S) & (v > RED_V)
        m = (red | ((v > WHITE_V) & (s < WHITE_S))).astype(np.uint8)
        pix = lambda pts, z=tz: np.array([project(P, (x, y, z)) for x, y in pts], np.float32)
        corners = mat_corners(markers)
        if corners is None:
            return []
        # look a little past the board (an edge stack's outline leans out over it), but keep only
        # stacks that stand on it (checked on the fitted centre below)
        mat = np.zeros(m.shape, np.uint8)
        cv2.fillConvexPoly(mat, cv2.convexHull(pix(mat_corners(markers, MARGIN_MM + LEAN_MM))).astype(np.int32), 1)
        board = cv2.convexHull(np.array(corners, np.float32))
        m &= mat
        ring = np.linspace(0, 2 * np.pi, 24, endpoint=False)
        for c in markers.values():
            cv2.fillConvexPoly(m, pix(np.c_[c["x"] + MARKER_MM * np.cos(ring), c["y"] + MARKER_MM * np.sin(ring)]).astype(np.int32), 0)
        for c in cards:
            a = np.radians(c["angle"])
            u = np.array([np.cos(a), np.sin(a)]) * (CARD[1] / 2 + CARD_GROW)
            w = np.array([-np.sin(a), np.cos(a)]) * (CARD[0] / 2 + CARD_GROW)
            q = [np.array([c["x"], c["y"]]) + su * u + sw * w for su, sw in ((1, 1), (1, -1), (-1, -1), (-1, 1))]
            cv2.fillConvexPoly(m, pix(q, tz + 1).astype(np.int32), 0)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        known, out = [], []
        for c in cs:
            if cv2.contourArea(c) < MIN_PX:
                continue
            at, area, was = _same(self.known, c)
            if was == "new":
                o = cv2.approxPolyDP(c, 1.5, True).reshape(-1, 2)
                x, y, hh, fit = eyes.upright(P, o, tz, 40, to_xy(P, o.astype(float), tz).mean(axis=0))
                was = None
                if fit >= FIT and cv2.pointPolygonTest(board, (float(x), float(y)), False) >= 0:
                    blob = np.zeros(m.shape, np.uint8)
                    cv2.drawContours(blob, [c], -1, 1, -1)
                    r = float((red & (blob > 0)).sum()) / blob.sum()
                    colour = "red" if r > .6 else "white" if r < .2 else "mixed"
                    k = dict(eyes.KNOWN)["chip"]
                    k = {**k, "unit": k["red"] if colour == "red" else k["unit"]}   # red sides show in full
                    raw = eyes.count_raw(hh, k)
                    was = {"x": round(x + SHIFT[0], 1), "y": round(y + SHIFT[1], 1), "height_mm": round(hh, 1),
                           "count": eyes.count(hh, k), "count_raw": raw, **eyes.cup_heights(raw),
                           "colour": colour, "fit": round(fit, 2)}
            known.append((at, area, was))
            if was:
                out.append(was)
        self.known = known
        return out
