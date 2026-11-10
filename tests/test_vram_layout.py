"""Guard the atlas/clean-strip memory contract used by the VDP renderer."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class VramLayoutTests(unittest.TestCase):
    def test_atlas_rectangles_are_byte_aligned_disjoint_and_above_clean_strips(self):
        frames = json.loads((ROOT / 'assets_msx/hellcat/manifest.json').read_text())['animation']['frames']
        occupied = set()
        for frame in frames:
            x, y = frame['atlas_x'], frame['atlas_y']
            width, height = frame['width'], frame['height']
            self.assertIn(y // 256, (2, 3))
            self.assertEqual(x % 2, 0)
            self.assertEqual(width % 2, 0)
            self.assertLessEqual(x + width, 256)
            self.assertLessEqual(y % 256 + height, 180)
            addresses = {row * 128 + column for row in range(y, y + height)
                         for column in range(x // 2, (x + width) // 2)}
            self.assertTrue(occupied.isdisjoint(addresses), frame['name'])
            occupied.update(addresses)
        self.assertEqual(len(occupied), 21370)
