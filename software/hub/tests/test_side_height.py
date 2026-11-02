"""Run on the Pi: cd hub && .venv/bin/python -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np

import eyes

TZ = -57.0                      # the board, in the head marker's frame
SHAPE = (1232, 1640)


def camera(at, look, f=1600.0):
    """A pinhole camera at `at` looking at `look` (gantry axes, Z up), as P."""
    at, look = np.array(at, float), np.array(look, float)
    fwd = (look - at) / np.linalg.norm(look - at)
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    down = np.cross(fwd, right)
    R = np.array([right, down, fwd])
    K = np.array([[f, 0, SHAPE[1] / 2], [0, f, SHAPE[0] / 2], [0, 0, 1]])
    return K @ np.c_[R, -R @ at]


CAM0 = camera((-386, -323, TZ + 163), (0, 0, TZ))     # like this build's cam 0: low, at the side
CAM1 = camera((-355, -170, TZ + 407), (0, 0, TZ))     # and cam 1: high, at the front left


def cylinder(P, x, y, r, h):
    """The outline a camera sees of an upright cylinder (a chip stack) on the board."""
    a = np.linspace(0, 2 * np.pi, 360, endpoint=False)
    pts = [eyes.project(P, (x + r * np.cos(t), y + r * np.sin(t), TZ + z)) for t in a for z in (0, h)]
    m = np.zeros(SHAPE, np.uint8)
    cv2.fillConvexPoly(m, cv2.convexHull(np.array(pts, np.float32)).astype(np.int32), 1)
    return m


def seen_from_above(x, y, r, h):
    """The footprint find gives: cam 1's outline of it mapped onto the board (stretched by its side)."""
    m = cylinder(CAM1, x, y, r, h)
    c = max(cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0], key=cv2.contourArea)
    return eyes.to_xy(CAM1, c.reshape(-1, 2).astype(float), TZ)


class SideHeight(unittest.TestCase):
    def test_a_chip(self):
        h, slide = eyes.side_height(CAM0, cylinder(CAM0, 68, 109, 20, 3.3), seen_from_above(68, 109, 20, 3.3), TZ, CAM1)
        self.assertAlmostEqual(h, 3.3, delta=0.5)
        self.assertAlmostEqual(slide, 0, delta=1.5)

    def test_a_stack_where_cam_1_is_off(self):
        # cam 1 put it 6 mm short in Y (as on the far side, Nov 2): the slide takes up the part
        # along cam 0's line of sight, and the height still comes out
        m = cylinder(CAM0, -7, -45, 20, 6.6)
        h, slide = eyes.side_height(CAM0, m, seen_from_above(-7, -45, 20, 6.6) - (0, 6), TZ, CAM1)
        self.assertAlmostEqual(h, 6.6, delta=0.8)
        self.assertGreater(abs(slide), 2)

    def test_a_taller_thing(self):
        h, _ = eyes.side_height(CAM0, cylinder(CAM0, 30, 20, 25, 21), seen_from_above(30, 20, 25, 21), TZ, CAM1)
        self.assertAlmostEqual(h, 21, delta=1.0)

    def test_cut_off_by_the_edge(self):
        m = cylinder(CAM0, 0, 0, 20, 10)
        m[:, :int(np.nonzero(m)[1].mean())] = 0          # half of it out of the picture
        m[:, 0] = m[:, 1] = 1
        self.assertIsNone(eyes.side_height(CAM0, m, seen_from_above(0, 0, 20, 10), TZ, CAM1))


class SideMatch(unittest.TestCase):
    def test_each_item_gets_its_own_outline(self):
        polys = [seen_from_above(68, 109, 20, 3.3), seen_from_above(-7, -45, 20, 6.6), None]
        side = [cylinder(CAM0, -7, -45, 20, 6.6), cylinder(CAM0, 68, 109, 20, 3.3)]
        got = eyes.side_match(CAM0, polys, side, TZ)
        self.assertIs(got[0], side[1])
        self.assertIs(got[1], side[0])
        self.assertNotIn(2, got)

    def test_nothing_near(self):
        got = eyes.side_match(CAM0, [seen_from_above(150, -150, 20, 3.3)], [cylinder(CAM0, -7, -45, 20, 3.3)], TZ)
        self.assertEqual(got, {})


if __name__ == "__main__":
    unittest.main()
