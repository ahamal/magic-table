"""Run on the Pi: cd hub && .venv/bin/python -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np

import eyes
from test_side_height import CAM1, SHAPE, TZ, cylinder

CHIP = 40.0

def fitted(n):
    """How tall cam 1's fit reads a stack of n (the count rule backwards): the height to draw a simulated
    stack at so that counting it tests the counting, not this calibration's sense of height."""
    k = dict(eyes.KNOWN)["chip"]
    return k["unit"] * n - k["short"]



def outline(m):
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return cv2.approxPolyDP(max(cs, key=cv2.contourArea), 1.5, True).reshape(-1, 2)


class Upright(unittest.TestCase):
    def check(self, x, y, h):
        o = outline(cylinder(CAM1, x, y, CHIP / 2, h))
        flat = eyes.to_xy(CAM1, o.astype(float), TZ).mean(axis=0)       # where the flat footprint says
        fx, fy, fh, fit = eyes.upright(CAM1, o, TZ, CHIP, flat)
        self.assertAlmostEqual(fh, h, delta=1.0)
        self.assertLess(np.hypot(fx - x, fy - y), 1.0)
        self.assertGreater(fit, eyes.UPRIGHT_FIT)
        return np.hypot(*(flat - (x, y)))

    def test_single_chip(self):
        self.check(10, -20, 3.3)

    def test_stack_of_eight(self):
        off = self.check(130, -50, 8 * 3.3)
        self.assertGreater(off, 5)        # the flat footprint's centre really is pulled away

    def test_far_side(self):
        self.check(-60, 110, 5 * 3.3)

    def test_two_touching_stacks_fit_badly(self):
        m = cylinder(CAM1, 0, 0, CHIP / 2, 10) | cylinder(CAM1, 38, 0, CHIP / 2, 10)
        o = outline(m)
        *_, fit = eyes.upright(CAM1, o, TZ, CHIP, eyes.to_xy(CAM1, o.astype(float), TZ).mean(axis=0))
        self.assertLess(fit, eyes.UPRIGHT_FIT)


def box(P, x, y, w, l, angle, h):
    """The outline a camera sees of an upright box (a deck) on the board."""
    m = np.zeros(SHAPE, np.uint8)
    cv2.fillConvexPoly(m, np.round(eyes.box_outline(P, x, y, w, l, angle, h, TZ)).astype(np.int32), 1)
    return m


class Known(unittest.TestCase):
    def found(self, what, m):
        o = outline(m)
        it = {"what": what, "outline": o.tolist(), **eyes.describe((0, 0), m, CAM1, TZ)}
        it["outline"] = o.tolist()
        eyes.place(it, CAM1, TZ)
        return it

    def test_deck(self):
        it = self.found("deck of cards", box(CAM1, 100, -40, 63, 88, 30, 16))
        b = it["board"]
        self.assertAlmostEqual(it["height_mm"], 16, delta=1.0)
        self.assertLess(np.hypot(b["x"] - 100, b["y"] + 40), 1.5)
        self.assertLess(abs((b["angle"] - 30 + 90) % 180 - 90), 2)
        self.assertEqual((b["w"], b["h"]), (63, 88))
        self.assertGreater(it["flat"]["h"], 92)            # flat, it looked longer

    def test_chip_stack_counted(self):
        it = self.found("red poker chip", cylinder(CAM1, 60, 30, CHIP / 2, fitted(6)))
        self.assertEqual(it["count"], 6)
        self.assertEqual(it["pick"]["x"], it["board"]["x"])

    def test_card_stays_flat(self):
        it = self.found("playing card", box(CAM1, 0, 0, 63, 88, 90, 0.3))
        self.assertEqual(it["height_mm"], 0.3)
        self.assertNotIn("flat", it)

    def test_unknown_untouched(self):
        it = self.found("coffee mug", cylinder(CAM1, 0, 0, 40, 90))
        self.assertNotIn("height_mm", it)


if __name__ == '__main__':
    unittest.main()
