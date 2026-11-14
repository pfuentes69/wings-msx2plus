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
            if frame.get('streamed'):continue
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
        self.assertEqual(len(occupied), sum(f['bytes'] for f in frames if not f.get('streamed')))

    def test_wheel_pieces_use_free_atlas_gaps(self):
        import sys
        sys.path.insert(0, str(ROOT / 'tools'))
        from convert_dashboard import atlas_slots
        meta = json.loads((ROOT / 'assets_msx/hellcat/manifest.json').read_text())['animation']
        taken = set()
        for group, (w, h) in zip(atlas_slots(27, True, True, True, True, frames=meta['frames']),
                                 [(48, 24), (256, 4), (16, 14), (96, 2), (8, 8), (22, 7), (8, 8)]):
            for x, y in group:
                taken |= {(xx, yy) for yy in range(y, y + h) for xx in range(x, x + w)}
        for f in meta['frames']:
            if not f.get('streamed'):
                taken |= {(xx, yy) for yy in range(f['atlas_y'], f['atlas_y'] + f['height'])
                          for xx in range(f['atlas_x'], f['atlas_x'] + f['width'])}
        tiles = json.loads((ROOT / 'assets_msx/mission_a/manifest.json').read_text())['selected']['tile_count']
        for t in range(tiles):   # terrain tile atlas below the clean strips
            x, y = t % 288 // 9 * 8, 512 + t // 288 * 256 + 180 + t % 9 * 8
            taken |= {(xx, yy) for yy in range(y, y + 8) for xx in range(x, x + 8)}
        pieces = {}
        for r in meta['wheels']:
            pieces[(r['atlas_x'], r['atlas_y'])] = (r['width'], r['height'])
        for x, y in meta['rope_backups']:   # arresting-rope strip backups
            pieces[(x, y)] = (128, 2)
        for (x, y), (w, h) in pieces.items():
            self.assertEqual(x % 2, 0)
            self.assertIn(y // 256, (2, 3))
            area = {(xx, yy) for yy in range(y, y + h) for xx in range(x, x + w)}
            self.assertTrue(taken.isdisjoint(area), (x, y))
            taken |= area

    def test_streamed_ground_turns_share_only_the_reserved_scratch_rectangle(self):
        meta=json.loads((ROOT/'assets_msx/hellcat/manifest.json').read_text())['animation']
        cache=meta['taxi_cache']
        for frame in meta['frames']:
            if not frame.get('streamed'):continue
            self.assertEqual((frame['atlas_x'],frame['atlas_y']),(cache['x'],cache['y']))
            self.assertLessEqual(frame['width'],cache['width'])
            self.assertLessEqual(frame['height'],cache['height'])
        self.assertEqual(len(meta['taxi_turn']),11)
        self.assertEqual(meta['frames'][meta['taxi_turn'][5]]['name'],'hc1b')


class HiddenRowTests(unittest.TestCase):
    """Rows 212..255 of display pages 0/1 are never shown, but are full.

    Aircraft backups use x=0..47 (src/world_flight.c Background), water frames
    x=48..239 on page 0 and x=48..143 on page 1 (src/msx/dashboard.c), other
    caches page 1 x=144..245, and carrier heave scrolls rows 254/255 into view.
    """
    def setUp(self):
        self.meta = json.loads((ROOT / 'assets_msx/hellcat/manifest.json').read_text())['animation']

    def test_gun_flash_slots_use_only_the_free_page0_strip(self):
        slots = {tuple(s) for s in self.meta['gun_flash_slots']}
        width, height = self.meta['gun_flash_slot_size']
        self.assertEqual(len(slots), 2)
        for x, y in slots:
            self.assertGreaterEqual(x, 240)
            self.assertLessEqual(x + width, 256)
            self.assertGreaterEqual(y, 212)
            self.assertLessEqual(y + height, 252)
        (x0, y0), (x1, y1) = sorted(slots)
        self.assertTrue(y0 + height <= y1 or x0 + width <= x1, 'slots overlap')
        for index, record in enumerate(self.meta['gun_flash']):
            self.assertEqual((record['atlas_x'], record['atlas_y']), tuple(self.meta['gun_flash_slots'][index // 20]))
            self.assertLessEqual(record['width'], width)
            self.assertLessEqual(record['height'], height)
            self.assertEqual(record['width'] % 2, 0)

    def test_aircraft_and_flash_backup_never_reaches_the_water_cache(self):
        frames = self.meta['frames']
        for side, table in ((0, self.meta['pitch_right']), (10, self.meta['pitch_left'])):
            for pose, frame in enumerate(table):
                shape = frames[frame]
                for variant in range(2):
                    flash = self.meta['gun_flash'][variant * 20 + side + pose]
                    for world in (1000, 1001):
                        left = min(world + shape['dx'], world + flash['dx']) - 25
                        right = max(world + shape['dx'] + shape['width'], world + flash['dx'] + flash['width']) - 25
                        backup = ((right + 1) & ~1) - (left & ~1)
                        self.assertLessEqual(backup, 48, (frame, variant, world))
