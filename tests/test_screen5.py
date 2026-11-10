import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from convert_hellcat import FRAMES, artifacts, convert, pack_pixels, rgb3


class Screen5Tests(unittest.TestCase):
    def test_nibble_order_and_bounds(self):
        self.assertEqual(pack_pixels([1, 15, 0, 8]), b'\x1f\x08')
        for indices in ([1], [16, 0], [-1, 0]):
            with self.assertRaises(ValueError):
                pack_pixels(indices)

    def test_rgb_precision(self):
        self.assertEqual([rgb3(v) for v in (0, 17, 128, 170, 240, 255)], [0, 0, 4, 5, 7, 7])

    def test_committed_artifacts_are_current(self):
        # Use relative paths so provenance stays host-independent.
        import os
        previous = Path.cwd()
        try:
            os.chdir(ROOT)
            for path, expected in artifacts(Path('assets_src/hellcat'), Path('assets_msx/hellcat'), Path('src/generated')).items():
                self.assertEqual(path.read_bytes(), expected, str(path))
        finally:
            os.chdir(previous)

    def test_conversion_preserves_silhouette_and_color_mapping(self):
        sources = [ROOT / f'assets_src/hellcat/{name}.png' for name in FRAMES]
        frames, palette, manifest = convert(sources)
        self.assertEqual(len(palette), 32)
        self.assertEqual(len(manifest['source_index_to_msx_index']), 12)
        for source, packed, meta in zip(sources, frames, manifest['frames']):
            with Image.open(source) as image:
                src = list(image.tobytes())
                out = [n for b in packed for n in (b >> 4, b & 15)]
                offset = meta['canvas_offset'][1] * 48
                self.assertTrue(all(v == 0 for v in out[:offset]))
                source_palette = image.getpalette()
                for old, index in zip(src, out[offset:offset + len(src)]):
                    self.assertEqual(old == 0, index == 0)
                    if old:
                        r, g, b = source_palette[old * 3:old * 3 + 3]
                        self.assertEqual(palette[index * 2:index * 2 + 2], bytes([(rgb3(r) << 4) | rgb3(b), rgb3(g)]))

    def test_nonindexed_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'rgb.png'
            Image.new('RGB', (48, 32)).save(source)
            with self.assertRaisesRegex(ValueError, 'indexed'):
                convert([source])


if __name__ == '__main__':
    unittest.main()
