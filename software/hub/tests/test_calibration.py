"""Run on the Pi: cd hub && .venv/bin/python -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

import vision


def camera(at, look):
    """A pinhole camera at `at` looking toward `look` (work mm), as a 3x4 P."""
    z = np.subtract(look, at) / np.linalg.norm(np.subtract(look, at))
    x = np.cross(z, [0, 0, 1]); x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.array([x, y, z])
    K = np.array([[1000, 0, 800], [0, 1000, 600], [0, 0, 1]])
    return K @ np.c_[R, -R @ at]


class Triangulate(unittest.TestCase):
    def test_two_cameras_find_the_point(self):
        Ps = [camera([-400, -300, 380], [0, 0, 0]), camera([-450, 100, 120], [0, 0, 0])]
        p = np.array([85.9, 43.6, 15.0])
        got = vision.triangulate(Ps, [vision.project(P, p) for P in Ps])
        np.testing.assert_allclose(got, p, atol=1e-6)


class CalibrateRefuses(unittest.TestCase):
    """Nothing may move when the grid wouldn't fit: the call returns before any G-code."""

    def setUp(self):
        self.v = vision.Vision.__new__(vision.Vision)
        self.v.grbl = MagicMock()
        self.v.grbl.status = {"state": "Idle", "WPos": [0.0, 205.0, 72.0]}
        self.v.cal = {"bounds": [-210, 210, -191, 191], "travel_z": 110.0}
        self.v.scene, self.v.needs_reanchor, self.v.busy = {}, False, False

    def test_grid_past_the_board(self):
        r = self.v.calibrate(72.0, span=250)
        self.assertFalse(r["ok"])
        self.v.grbl.send.assert_not_called()

    def test_mate_under_the_grid(self):
        self.v.grbl.status["WPos"] = [0.0, 0.0, 72.0]
        self.v.scene = {"mate": {"x": 0.0, "y": 0.0}}
        r = self.v.calibrate(72.0, span=130)
        self.assertIn("Mate", r["error"])
        self.v.grbl.send.assert_not_called()

    def test_from_zero_needs_the_head_at_zero(self):
        r = self.v.calibrate(0.0, span=110, steps=5, from_zero=True)
        self.assertIn("Work zero", r["error"])
        self.v.grbl.send.assert_not_called()

    def test_after_a_reset(self):
        self.v.needs_reanchor = True
        self.assertFalse(self.v.calibrate(72.0, span=130)["ok"])
        self.v.grbl.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
