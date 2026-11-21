"""Map records (tools/build_maps.py, docs/map-records.md): the packed
records decode back to each map's converted tables."""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_maps  # noqa: E402


def unpack(record, data):
    """{field: value} of a record's RAM part, by the packer's layout."""
    out, at = {}, 0
    for name, kind, count, _ in record:
        size, fmt = build_maps.SIZE[kind], '<' + build_maps.FORMAT[kind]
        items = []
        for _ in range(1 if count is None else count):
            item = struct.unpack_from(fmt, data, at)
            items.append(item if len(item) > 1 else item[0])
            at += size
        out[name] = items[0] if count is None else items
    return out


class MapRecordTests(unittest.TestCase):
    def test_the_generated_records_and_headers_are_current(self):
        files = build_maps.build(build_maps.maps_present())
        for path, data in files.items():
            self.assertTrue(path.is_file() and path.read_bytes() == data, f'stale {path}: python3 tools/build_maps.py')

    def test_each_record_holds_its_maps_tables(self):
        for letter in build_maps.maps_present():
            v = build_maps.parse(build_maps.GENERATED / f'map_{letter}')
            data = (build_maps.OUT / f'record_{letter}.bin').read_bytes()
            banks = build_maps.banks(letter)
            layout = build_maps.fields(dict(v, reset_x=0, tile_bank=0, map_bank=0, runs_at=0, heights_at=0,
                                            sea_column=0, far_sea_column=0))
            got = unpack(layout, data)
            self.assertEqual((got['tile_bank'], got['map_bank']), (banks['tiles'], banks['column_map']), letter)
            self.assertEqual(got['width'], v['MISSION_SURFACE_WIDTH'])
            self.assertEqual(got['palette'], v['g_TerrainPalette'])
            self.assertEqual(got['huts'], v['ISLAND_HUTS'])
            self.assertEqual(got['hut_x'][:v['ISLAND_HUTS']], v['s_HutX'][:v['ISLAND_HUTS']])
            self.assertEqual(got['ships'], v['SHIP_COUNT'])
            self.assertEqual(got['ship_gun_x'][:v['SHIP_GUNS']], v['s_ShipGunX'][:v['SHIP_GUNS']])
            self.assertEqual(got['water'][:v['MISSION_WATER_REGIONS']], v['g_MissionWaterBands'])
            self.assertEqual(list(zip(got['class_end'], got['class_surface'], got['class_ship']))[:got['class_count']],
                             v['class_runs'])
            # The ROM tables after the RAM part, at their window-3 addresses.
            runs = [struct.unpack_from('<HH', data, got['runs_at'] - 0xA000 + 4 * i) for i in range(got['surface_runs'])]
            self.assertEqual(runs, v['g_MissionSurfaceRuns'])
            n = got['height_runs']
            ends = list(struct.unpack_from(f'<{n}H', data, got['heights_at'] - 0xA000))
            heights = list(data[got['heights_at'] - 0xA000 + 2 * n:][:n])
            self.assertEqual((ends, heights), (v['s_MissionHeightEnd'], v['s_MissionHeight']))

    def test_every_u16_field_is_even_so_the_host_layout_is_sdccs(self):
        v = build_maps.parse(build_maps.GENERATED / 'map_a')
        layout = build_maps.fields(dict(v, reset_x=0, tile_bank=0, map_bank=0, runs_at=0, heights_at=0,
                                        sea_column=0, far_sea_column=0))
        build_maps.pack(layout)   # raises on an odd u16 offset


if __name__ == '__main__':
    unittest.main()
