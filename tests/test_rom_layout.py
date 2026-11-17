"""Banked ASCII8 code layout guard used by the mission ROM post-build step."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import check_rom_layout  # noqa: E402


def record(kind, address, payload):
    data = bytes([len(payload), address >> 8, address & 0xFF, kind]) + payload
    return ':' + (data + bytes([-sum(data) & 0xFF])).hex().upper()


def hex_file(chunks):
    """chunks: [(full 24-bit address, byte count)] -> Intel HEX text."""
    lines = []
    for address, count in chunks:
        lines.append(record(4, 0, (address >> 16).to_bytes(2, 'big')))
        lines.append(record(0, address & 0xFFFF, bytes(count)))
    return '\n'.join(lines + [record(1, 0, b'')]) + '\n'


class RomLayoutTests(unittest.TestCase):
    def check(self, chunks, code=(3, 16), data=(4, 5)):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'rom.ihx'
            path.write_text(hex_file(chunks))
            return check_rom_layout.check(check_rom_layout.read_hex(path), 256, set(code), set(data))

    def test_valid_layout_reports_free_space(self):
        errors, report = self.check([(0x4000, 16), (0x03A000, 8), (0x10A000, 4)])
        self.assertEqual(errors, [])
        self.assertIn('resident 4000h-400Fh: 16 bytes, 24560 free of 24576', report)
        self.assertIn('segment 16 A000h-A003h: 4 bytes, 8188 free', report)

    def test_resident_code_may_not_enter_banked_window(self):
        errors, _ = self.check([(0x9FFF, 2)])
        self.assertTrue(any('A000h' in e and 'resident' in e for e in errors), errors)

    def test_banked_code_must_stay_in_window_three(self):
        errors, _ = self.check([(0x10BFFF, 2)])
        self.assertTrue(any('segment 16' in e for e in errors), errors)

    def test_undeclared_segment_and_data_collision_fail(self):
        errors, _ = self.check([(0x11A000, 1)], code=(3, 4))
        self.assertTrue(any('segment 17' in e for e in errors), errors)
        self.assertTrue(any('overlaps a raw data bank' in e for e in errors), errors)

    def test_resident_and_out_of_rom_segments_are_rejected(self):
        errors, _ = self.check([], code=(2, 32))
        self.assertEqual(len(errors), 2, errors)

    def test_bad_checksum_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'bad.ihx'
            path.write_text(':0100000000FE\n')
            with self.assertRaises(ValueError):
                check_rom_layout.read_hex(path)

    def test_banked_entry_points_match_header_declarations(self):
        """Every banked module declares its segment and marks its prototypes."""
        for module in ('msx/dashboard', 'msx/weapons', 'msx/menu', 'msx/ship', 'msx/elevator', 'core/engine', 'core/landing', 'core/flight_model', 'msx/rope', 'core/smoke', 'msx/smoke_draw', 'core/game', 'core/ships', 'core/rockets'):
            source = (ROOT / f'src/{module}.c').read_text()
            header = (ROOT / f'src/{module}.h').read_text()
            self.assertIn('WINGS_CODE_SEGMENT(WINGS_SEGMENT_', source, module)
            for line in header.splitlines():
                if line.rstrip().endswith(');') and '(' in line and not line.startswith(('#', '/', ' ')):
                    self.assertIn('WINGS_BANKED', line, f'{module}.h: {line}')


if __name__ == '__main__':
    unittest.main()
