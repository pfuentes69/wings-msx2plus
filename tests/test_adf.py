import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from inspect_adf import extract_ofs


def fixture():
    disk = bytearray(880 * 1024)
    disk[:4] = b'DOS\x00'
    def put(number, values, name=None, payload=None):
        data = bytearray(512)
        for offset, value in values.items():
            struct.pack_into('>I', data, offset, value)
        if name:
            data[432] = len(name)
            data[433:433 + len(name)] = name
        if payload:
            data[24:24 + len(payload)] = payload
        struct.pack_into('>I', data, 20, (-sum(struct.unpack('>128I', data))) & 0xffffffff)
        disk[number * 512:(number + 1) * 512] = data
    put(880, {0: 2, 24: 881, 508: 1}, b'disk')
    put(881, {0: 2, 16: 882, 324: 3, 508: 0xfffffffd}, b'file')
    put(882, {0: 8, 4: 881, 8: 1, 12: 3}, payload=b'abc')
    return disk


class AdfTests(unittest.TestCase):
    def test_ofs_file(self):
        self.assertEqual(extract_ofs(fixture()), {Path('file'): b'abc'})

    def test_rejects_unsupported_disk(self):
        with self.assertRaises(ValueError):
            extract_ofs(b'DOS\x01')

    def test_bad_checksum(self):
        image = fixture()
        image[882 * 512 + 24] ^= 1
        with self.assertRaisesRegex(ValueError, 'checksum'):
            extract_ofs(image)

    def test_pointer_outside_disk(self):
        image = fixture()
        root = bytearray(image[880 * 512:881 * 512])
        struct.pack_into('>I', root, 24, 9999)
        struct.pack_into('>I', root, 20, 0)
        struct.pack_into('>I', root, 20, (-sum(struct.unpack('>128I', root))) & 0xffffffff)
        image[880 * 512:881 * 512] = root
        with self.assertRaisesRegex(ValueError, 'outside'):
            extract_ofs(image)
