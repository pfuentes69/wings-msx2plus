"""Malformed-input tests plus integration against preserved reference bytes."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from unpack_shapes import unpack_rpck, read_ppkc
from decode_shapes import decode_record, read_palette
from extract_iff import unpack_br1, iff_chunks, iff_img


class RpckTests(unittest.TestCase):
    def test_literal_repeat_and_zero(self):
        self.assertEqual(unpack_rpck(b'Rpck' + struct.pack('>I', 6) + b'\xfeAB\x02C\x00D'), b'ABCCCD')

    def test_rejects_malformed(self):
        for data in (b'Rpck', b'Rpck\x00\x00\x00\x01',
                     b'Rpck\x00\x00\x00\x03\xfdAB',
                     b'Rpck\x00\x00\x00\x01\x02X',
                     b'Rpck\xff\xff\xff\xff', b'Rpck\x00\x00\x00\x00junk'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                unpack_rpck(data)

    def test_known_trailer_is_reported(self):
        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter('always')
            self.assertEqual(unpack_rpck(b'Rpck\x00\x00\x00\x01\x00A\xff\x00'), b'A')
            self.assertEqual(len(observed), 1)


class IndexTests(unittest.TestCase):
    def test_two_records(self):
        data = b'PPkc\x00\x02one two ' + struct.pack('>II', 0, 2) + b'abxyz'
        self.assertEqual(read_ppkc(data), [('one ', 0, b'ab'), ('two ', 2, b'xyz')])

    def test_bad_indexes_and_names(self):
        for name, offsets in ((b'one two ', (1, 2)), (b'one two ', (0, 9)),
                              (b'one two ', (0, 0)), (b'one one ', (0, 2)),
                              (b'../ two ', (0, 2))):
            with self.subTest(name=name, offsets=offsets), self.assertRaises(ValueError):
                read_ppkc(b'PPkc\x00\x02' + name + struct.pack('>II', *offsets) + b'abc')
        with self.assertRaises(ValueError):
            read_ppkc(b'PPkc\x00\x02tiny')


class PixelTests(unittest.TestCase):
    @staticmethod
    def shape():
        # Two rows, two planes; plane 1 writes both index bits 0 and 1.
        return struct.pack('>HHhhhh', 2, 2, -3, 4, 64, 147) + bytes([0, 0, 3, 4, 0, 0, 0, 0]) + b'\x80\x00\x40\x00\x40\x00\x80\x00'

    def test_planes_msb_first_combined_maps(self):
        pixels, meta = decode_record(self.shape())
        self.assertEqual(pixels[:3], bytes([3, 4, 0]))
        self.assertEqual(pixels[16:19], bytes([4, 3, 0]))
        self.assertEqual(meta['origin_candidate'], [-3, 4])

    def test_malformed_record(self):
        record = self.shape()
        bad_header = bytearray(record)
        bad_header[15] = 0
        for data in (b'', record[:-1], record + b'X', bytes(bad_header)):
            with self.subTest(data=data), self.assertRaises(ValueError):
                decode_record(data)

    def test_bad_palette(self):
        with self.assertRaises(ValueError):
            read_palette(b'CMAP')


class IffTests(unittest.TestCase):
    def test_byterun(self):
        self.assertEqual(unpack_br1(b'\x80\x01AB\xfeC', 5), b'ABCCC')
        for data, size in ((b'\x02AB', 3), (b'\xfe', 3), (b'\xfeX', 2), (b'\x00X', 2)):
            with self.subTest(data=data), self.assertRaises(ValueError):
                unpack_br1(data, size)

    def test_chunk_bounds(self):
        for data in (b'FORM', b'FORM\x00\x00\x00\x04ILBMextra',
                     b'FORM\x00\x00\x00\x0cILBMBODY\x00\x00\x00\x08'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                iff_chunks(data)


class CorpusTests(unittest.TestCase):
    def test_manifest_integrity(self):
        manifest = json.loads((ROOT / 'reference_assets/MANIFEST.json').read_text())
        for entry in manifest['files']:
            data = (ROOT / entry['path']).read_bytes()
            self.assertEqual(len(data), entry['bytes'], entry['path'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry['sha256'], entry['path'])

    def test_all_archives_reproduce_preserved_records(self):
        count = 0
        shapes = ROOT / 'reference_assets/original_files/Wings_of_Fury/shapes'
        preserved = ROOT / 'reference_assets/unpacked_shapes'
        for source in shapes.glob('*.shp'):
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                expanded = unpack_rpck(source.read_bytes())
            self.assertEqual(expanded, (preserved / (source.name + '.unpacked')).read_bytes())
            for i, (name, offset, data) in enumerate(read_ppkc(expanded)):
                self.assertEqual(data, (preserved / source.stem / f'{i:03d}_{name}.bin').read_bytes())
                stride, h = struct.unpack_from('>HH', data)
                self.assertEqual(len(data), 20 + stride * h * sum(bool(v) for v in data[14:20]))
                count += 1
        self.assertEqual(count, 1049)

    def test_every_hellcat_record_decodes(self):
        sources = list((ROOT / 'reference_assets/unpacked_shapes/hellcat').glob('*.bin'))
        self.assertEqual(len(sources), 116)
        for source in sources:
            pixels, meta = decode_record(source.read_bytes())
            self.assertEqual(len(pixels), meta['width'] * meta['height'])
            self.assertLess(max(pixels), 32)

    def test_existing_iff_previews_reproduce_rgb(self):
        from PIL import Image
        shapes = ROOT / 'reference_assets/original_files/Wings_of_Fury/shapes'
        previews = ROOT / 'reference_assets/previews/png'
        for p in previews.glob('*.png'):
            candidates = [s for s in shapes.iterdir() if s.name.replace('.', '_') + '.png' == p.name]
            self.assertEqual(len(candidates), 1, p.name)
            image, _ = iff_img(candidates[0])
            with Image.open(p) as original:
                self.assertEqual(image.convert('RGB').tobytes(), original.convert('RGB').tobytes(), p.name)


if __name__ == '__main__':
    unittest.main()
