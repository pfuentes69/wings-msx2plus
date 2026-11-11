"""Original carrier artwork and its shared VRAM allocation."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from convert_ship import artifacts
from decode_mission import SOURCE
from decode_shapes import decode_record
from unpack_shapes import read_ppkc,unpack_rpck

class ShipTests(unittest.TestCase):
    def test_original_flag_and_radar_frames_are_retained(self):
        files=artifacts()
        for path,data in files.items():self.assertEqual(path.read_bytes(),data,str(path))
        records={n:r for n,_,r in read_ppkc(unpack_rpck((SOURCE/'shapes/world.shp').read_bytes()))}
        original=[decode_record(records['flg'+str(i)],plane_constants=True)[0] for i in range(3,7)]
        self.assertEqual((ROOT/'assets_src/ship/frames.indices').read_bytes(),b''.join(original))
        self.assertEqual(len(set(original)),4)
        # Both the cloth and radar change in the supplied combined records.
        self.assertGreater(len({p[:32*12] for p in original}),1)
        self.assertGreater(len({p[32*32:] for p in original}),1)
        self.assertTrue(all(0 not in p for p in original))

    def test_ship_cache_is_disjoint_from_all_other_atlases(self):
        occupied=set()
        def add(x,y,w,h):
            area={row*128+col for row in range(y,y+h) for col in range(x//2,(x+w)//2)}
            self.assertTrue(occupied.isdisjoint(area));occupied.update(area)
        for f in json.loads((ROOT/'assets_msx/hellcat/manifest.json').read_text())['animation']['frames']:
            add(f['atlas_x'],f['atlas_y'],f['width'],f['height'])
        count=json.loads((ROOT/'assets_msx/mission_a/manifest.json').read_text())['selected']['tile_count']
        for t in range(count):add(t%288//9*8,692+t%9*8+t//288*256,8,8)
        cockpit=json.loads((ROOT/'assets_src/dashboard/manifest.json').read_text())
        for x,y in cockpit['pilot_slots']:add(x,y,48,24)
        for f in cockpit['far_poses']:add(f['atlas_x'],f['atlas_y'],16,5)
        for x,y in cockpit['wave_backdrop_slots']:add(x,y,256,4)
        for x,y in cockpit['wave_tail_slots']:add(x,y,96,2)
        for f in json.loads((ROOT/'assets_msx/ship/manifest.json').read_text())['frames']:
            for x,y in f['parts']:add(x,y,16,14)
