"""Run on the Pi: cd hub && .venv/bin/python -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np

import eyes

P = np.array([[1.0, 0, 0, 50], [0, 1.0, 0, 50], [0, 0, 0, 1.0]])   # mm -> px, centred at (50, 50)


class RobotMasks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.img = np.zeros((100, 100, 3), np.uint8)
        self.jpeg = cv2.imencode('.jpg', self.img)[1].tobytes()
        corners = [(x, y, z) for x in (-30, -10) for y in (-30, -10) for z in (0, 10)]
        self.robots = eyes.robot_masks(P, {'mate': corners}, (100, 100))
        self.inside = ((20, 20, 40, 40), np.ones((20, 20), np.uint8))
        self.clear = ((70, 70, 90, 90), np.ones((20, 20), np.uint8))

    def test_mask_from_tracked_box(self):
        m = self.robots['mate']
        self.assertEqual(m[30, 30], 1)
        self.assertEqual(m[80, 80], 0)

    def test_overlap(self):
        self.assertGreater(eyes.robot_overlap(*self.inside, self.robots)['inside'], .9)
        self.assertEqual(eyes.robot_overlap(*self.clear, self.robots), {'inside': 0.0, 'near': []})

    async def test_muse_decides(self):
        with patch.object(eyes, 'ask', AsyncMock(return_value='{"keep": [0]}')):
            kept = await eyes.verify(self.img, [self.inside, self.clear], 'card', robots=self.robots)
        self.assertEqual(kept, [self.inside])   # Muse saw a loose card on Mate

    async def test_no_answer_falls_back_to_robot_rule(self):
        with patch.object(eyes, 'ask', AsyncMock(side_effect=eyes.EyesError('down'))):
            kept = await eyes.verify(self.img, [self.inside, self.clear], 'card', robots=self.robots)
        self.assertEqual(kept, [self.clear])

    async def test_away_from_robot_not_asked(self):
        ask = AsyncMock(return_value='{"keep": []}')
        with patch.object(eyes, 'ask', ask):
            kept = await eyes.verify(self.img, [self.clear], 'card', robots=self.robots, everything=False)
        self.assertEqual(kept, [self.clear])
        ask.assert_not_called()

    async def test_only_the_doubtful_asked_about(self):
        ask = AsyncMock(return_value='{"keep": []}')
        with patch.object(eyes, 'ask', ask):
            kept = await eyes.verify(self.img, [self.inside, self.clear], 'card', robots=self.robots, everything=False)
        self.assertEqual(kept, [self.clear])     # Muse dropped the one on Mate; the clear one wasn't in question
        ask.assert_called_once()

    async def test_fallback_checked_against_first_name(self):
        seg = AsyncMock(side_effect=[[self.inside], [self.clear]])
        ask = AsyncMock(side_effect=['{"keep": []}', '{"keep": [0]}'])
        with patch.object(eyes, 'segment', seg), patch.object(eyes, 'ask', ask):
            got, name = await eyes._first(self.jpeg, self.img, ['plate', 'white object'])
        self.assertEqual((got, name), ([self.clear], 'white object'))
        self.assertIn('plate', ask.call_args.args[1])

    async def test_find_keeps_pick_near_robot(self):
        near = ((40, 20, 60, 40), np.ones((20, 20), np.uint8))
        corners = [(x, y, z) for x in (-30, -10) for y in (-30, -10) for z in (0, 10)]
        with patch.object(eyes, 'segment', AsyncMock(return_value=[near])), \
             patch.object(eyes, 'ask', AsyncMock(return_value='{"keep": [0]}')):
            r = await eyes.find(self.jpeg, ['card'], P, 0, robot={'mate': corners})
        it = r['items'][0]
        self.assertIn('pick', it)
        self.assertEqual(it['robot']['near'], ['mate'])


if __name__ == '__main__':
    unittest.main()
