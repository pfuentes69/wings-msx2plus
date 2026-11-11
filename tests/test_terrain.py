"""Validate terrain provenance, palette contracts, lossless tiling and cache layout."""
import json
from pathlib import Path
import sys
import unittest
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from convert_terrain import artifacts, tile_scene, WIDTH, HEIGHT, TOP
from decode_shapes import decode_record


class TerrainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files, _, _, cls.pixels, _, cls.palette, cls.metadata = artifacts()

    def test_all_generated_outputs_match_sources(self):
        for path, data in self.files.items():
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertEqual(path.read_bytes(), data)

    def test_both_tile_sizes_round_trip_visible_pixels(self):
        for size in (8, 16):
            stats, tiles, tile_map = tile_scene(self.pixels, size)
            reconstructed = bytearray(WIDTH * HEIGHT)
            for col in range(stats['columns']):
                for row in range(stats['rows']):
                    index = tile_map[col * stats['rows'] + row]
                    packed = tiles[index * size * size // 2:(index + 1) * size * size // 2]
                    unpacked = bytes(v for byte in packed for v in (byte >> 4, byte & 15))
                    for sy in range(size):
                        y = TOP + row * size + sy
                        if y < HEIGHT:
                            start = y * WIDTH + col * size
                            reconstructed[start:start + size] = unpacked[sy * size:(sy + 1) * size]
            self.assertEqual(bytes(reconstructed), self.pixels)

    def test_palette_preserves_aircraft_and_uniform_band_contract(self):
        plane = json.loads((ROOT / 'assets_msx/hellcat/manifest.json').read_text())
        self.assertEqual(self.palette[:12], plane['palette_rgb3'][:12])
        self.assertEqual(set(self.pixels[128 * WIDTH:144 * WIDTH]), {0})
        self.assertEqual(set(self.pixels[208 * WIDTH:]), {1})
        self.assertTrue(set(self.pixels) <= set(range(16)))

    def test_tile_cache_is_disjoint_from_aircraft_and_footprints(self):
        frames = json.loads((ROOT / 'assets_msx/hellcat/manifest.json').read_text())['animation']['frames']
        aircraft = {row * 128 + x for shape in frames
                    for row in range(shape['atlas_y'], shape['atlas_y'] + shape['height'])
                    for x in range(shape['atlas_x'] // 2, (shape['atlas_x'] + shape['width']) // 2)}
        occupied = set()
        for tile in range(self.metadata['selected']['tile_count']):
            y = (tile // 64 + 2) * 256 + 180 + (tile % 64 // 16) * 16
            x = tile % 16 * 8
            self.assertLessEqual(y % 256 + 16, 244)
            addresses = {row * 128 + col for row in range(y, y + 16) for col in range(x, x + 8)}
            self.assertTrue(occupied.isdisjoint(addresses))
            self.assertTrue(aircraft.isdisjoint(addresses))
            self.assertGreaterEqual(min(addresses), 65536)
            self.assertLess(max(addresses), 131072)
            occupied.update(addresses)

    def test_nonzero_base_shorelines_are_exact_reflections(self):
        left, lm = decode_record((ROOT / 'reference_assets/unpacked_shapes/world/005_bchl.bin').read_bytes())
        right, rm = decode_record((ROOT / 'reference_assets/unpacked_shapes/world/006_bchr.bin').read_bytes())
        self.assertEqual((lm['base_color_candidate'], rm['base_color_candidate']), (14, 14))
        self.assertEqual(set(left), {14, 30, 31})
        self.assertEqual(ImageOps.mirror(Image.frombytes('P', (32, 6), left)).tobytes(), right)

    def test_tiles_reject_bad_dimensions_or_color_indices(self):
        with self.assertRaises(ValueError):
            tile_scene(b'', 16)
        with self.assertRaises(ValueError):
            tile_scene(self.pixels, 12)
        invalid = bytearray(self.pixels)
        invalid[TOP * WIDTH] = 16
        with self.assertRaises(ValueError):
            tile_scene(invalid, 16)
