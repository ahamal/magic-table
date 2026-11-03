"""Run on the Pi: cd hub && .venv/bin/python -m unittest discover -s tests"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np

import cards
import chips
import eyes
from test_side_height import CAM1, SHAPE, TZ, cylinder
from vision import CARD, project

MARKERS = {str(i): {"x": x, "y": y} for i, (x, y) in enumerate([(-250, 260), (245, 265), (-245, -180), (245, -170)])}


def fitted(n):
    """How tall cam 1's fit reads a stack of n (the count rule backwards): the height to draw a simulated
    stack at so that counting it tests the counting, not this calibration's sense of height."""
    k = dict(eyes.KNOWN)["chip"]
    return k["red"] * n - k["short"]          # the stacks drawn here are red


def face(seed):
    """A made-up card face: white with a few coloured blobs, CARD at cards.PX px/mm."""
    rng = np.random.default_rng(seed)
    f = np.full((int(CARD[1] * cards.PX), int(CARD[0] * cards.PX), 3), 245, np.uint8)
    for _ in range(6):
        c = tuple(int(v) for v in rng.integers(0, 200, 3))
        cv2.circle(f, (int(rng.integers(30, f.shape[1] - 30)), int(rng.integers(30, f.shape[0] - 30))), 18, c, -1)
    return f


def lay(img, f, c):
    """Draws face f into cam 1's picture as a card lying at c (x, y, angle)."""
    src = np.array([(0, 0), (f.shape[1], 0), (f.shape[1], f.shape[0]), (0, f.shape[0])], np.float32)
    dst = np.array([project(CAM1, p) for p in cards.corners(c, TZ)], np.float32)
    H = cv2.getPerspectiveTransform(src, dst)
    w = cv2.warpPerspective(f, H, (SHAPE[1], SHAPE[0]))
    m = cv2.warpPerspective(np.ones(f.shape[:2], np.uint8), H, (SHAPE[1], SHAPE[0]))
    img[m > 0] = w[m > 0]


class CardCache(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = patch.object(cards, "LIB", Path(d.name))
        p.start()
        self.addCleanup(p.stop)
        self.cc = cards.Cards()

    def test_moved_card_named_from_cache(self):
        a, b = face(1), face(2)
        img = np.full((*SHAPE, 3), 30, np.uint8)
        lay(img, a, {"x": -40, "y": 20, "angle": 80})
        self.cc.learn("5♣", cards.flatten(img, CAM1, TZ, {"x": -40, "y": 20, "angle": 80}))
        img2 = np.full((*SHAPE, 3), 30, np.uint8)
        lay(img2, b, {"x": -40, "y": 20, "angle": 80})
        self.cc.learn("5♦", cards.flatten(img2, CAM1, TZ, {"x": -40, "y": 20, "angle": 80}))
        moved = {"x": 60, "y": -50, "angle": 10}       # a person moved the 5♣ and turned it
        img3 = np.full((*SHAPE, 3), 30, np.uint8)
        lay(img3, a, moved)
        name, score, margin = self.cc.match(cards.flatten(img3, CAM1, TZ, moved))
        self.assertEqual(name, "5♣")
        self.assertGreater(margin, cards.MARGIN)

    def test_unknown_not_named(self):
        img = np.full((*SHAPE, 3), 30, np.uint8)
        lay(img, face(1), {"x": 0, "y": 0, "angle": 90})
        self.cc.learn("5♣", cards.flatten(img, CAM1, TZ, {"x": 0, "y": 0, "angle": 90}))
        img2 = np.full((*SHAPE, 3), 30, np.uint8)
        lay(img2, face(3), {"x": 0, "y": 0, "angle": 90})
        self.assertIsNone(self.cc.match(cards.flatten(img2, CAM1, TZ, {"x": 0, "y": 0, "angle": 90}))[0])

    def test_still_card_keeps_its_name(self):
        c = [{"x": 10, "y": 10, "angle": 90, "face": "up"}]
        self.cc.remember(c[0], "Q♣", 0.9, "muse")
        self.cc.label(np.zeros((*SHAPE, 3), np.uint8), CAM1, TZ, c)
        self.assertEqual(c[0]["card"], "Q♣")


class ChipsAndDecks(unittest.TestCase):
    def picture(self):
        return np.full((*SHAPE, 3), 30, np.uint8)       # the dark mat

    def test_red_stack_counted(self):
        img = self.picture()
        img[cylinder(CAM1, 60, 30, 20, fitted(7)) > 0] = (40, 40, 200)
        got = chips.Chips().find(img, CAM1, TZ, MARKERS, [])
        self.assertEqual(len(got), 1)
        self.assertEqual((got[0]["count"], got[0]["colour"]), (7, "red"))
        self.assertLess(np.hypot(got[0]["x"] - 60 - chips.SHIFT[0], got[0]["y"] - 30 - chips.SHIFT[1]), 1.5)

    def test_a_hidden_marker_doesnt_hide_the_chips(self):
        img = self.picture()
        img[cylinder(CAM1, 150, -100, 20, fitted(4)) > 0] = (40, 40, 200)   # near the hidden corner
        three = {k: v for k, v in MARKERS.items() if k != "3"}
        self.assertEqual([c["count"] for c in chips.Chips().find(img, CAM1, TZ, three, [])], [4])

    def test_cup_heights(self):
        self.assertEqual(eyes.cup_heights(7.1), {"sure": True, "pick_z": 21.3, "place_z": 27.0})
        borderline = eyes.cup_heights(7.5)            # could be 8: planned as 8, never pressing into it
        self.assertFalse(borderline["sure"])
        self.assertEqual(borderline["pick_z"], round(3.3 * 8 - 1.8, 1))

    def test_deck_from_a_tall_box(self):
        img = self.picture()
        o = eyes.box_outline(CAM1, 100, -60, CARD[0], CARD[1], 20, 16, TZ)
        cv2.fillConvexPoly(img, np.round(o).astype(np.int32), (200, 120, 60))
        got = chips.Chips().decks(img, CAM1, TZ, MARKERS, [])
        self.assertEqual(len(got), 1)
        self.assertAlmostEqual(got[0]["height_mm"], 16, delta=1.0)

    def test_a_card_stays_a_card(self):
        img = self.picture()
        o = eyes.box_outline(CAM1, 0, 0, CARD[0], CARD[1], 90, 0.3, TZ)
        cv2.fillConvexPoly(img, np.round(o).astype(np.int32), (200, 120, 60))
        card = {"x": 0.0, "y": 0.0, "angle": 90, "face": "down"}
        found = [card]
        self.assertEqual(chips.Chips().decks(img, CAM1, TZ, MARKERS, found), [])
        self.assertEqual(found, [card])


if __name__ == '__main__':
    unittest.main()
