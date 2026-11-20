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
            if not f.get('streamed') and not f.get('unused'):add(f['atlas_x'],f['atlas_y'],f['width'],f['height'])
        from convert_dashboard import STATIC_TILE_FOOTPRINT
        count=STATIC_TILE_FOOTPRINT   # the old static tile cells (the cache's slots lie there)
        for t in range(count):add(t%288//9*8,692+t%9*8+t//288*256,8,8)
        cockpit=json.loads((ROOT/'assets_src/dashboard/manifest.json').read_text())
        for x,y in cockpit['pilot_slots']:add(x,y,48,24)
        for f in cockpit['far_poses']:add(f['atlas_x'],f['atlas_y'],16,5)
        for x,y in cockpit['wave_backdrop_slots']:add(x,y,256,4)
        for x,y in cockpit['wave_tail_slots']:add(x,y,96,2)
        for f in json.loads((ROOT/'assets_msx/ship/manifest.json').read_text())['frames']:
            for x,y in f['parts']:add(x,y,16,14)
        cache=json.loads((ROOT/'assets_msx/hellcat/manifest.json').read_text())['animation']['taxi_cache']
        add(cache['x'],cache['y'],cache['width'],cache['height'])
        for x,y in cockpit['weapon_backups']:add(x,y,8,8)
        for x,y in cockpit['bomb_slots']:add(x,y,8,6)
        for x,y in json.loads((ROOT/'assets_msx/ship/manifest.json').read_text())['crew_slots']:add(x,y,22,7)

        lift=json.loads((ROOT/'assets_msx/elevator/manifest.json').read_text())
        for x,y in lift['background_slots']:add(x,y,64,40)
        for x,y in lift['platform_slots']:add(x,y,32,7)
        # The lift uses a free part of page 1; every actual wave-cache byte
        # and the two plane clean-footprint rectangles must stay disjoint.
        for page in (0,1):add(0,page*256+212,48,36)
        for phase in range(12):
            for row in range(11):
                if phase%4==3 and row>=9:continue # relocated tails checked above
                add(144 if 4<=phase<8 else 48,212+phase%4*11+(256 if phase>=8 else 0)+row,96,1)

    def test_original_signalman_arms_and_map_markers(self):
        records={n:r for n,_,r in read_ppkc(unpack_rpck((SOURCE/'shapes/world.shp').read_bytes()))}
        original=[decode_record(records[f'fgy{i:x}'],plane_constants=True)[0] for i in range(16)]
        self.assertEqual((ROOT/'assets_src/ship/crew.indices').read_bytes(),b''.join(original))
        mission=json.loads((ROOT/'assets_src/missions/a-map.json').read_text())
        anchors=[c['x'] for c in mission['cells'] if c['shape_id']==159]
        manifest=json.loads((ROOT/'assets_msx/ship/manifest.json').read_text())
        self.assertEqual(anchors,manifest['crew_anchors'])
        self.assertEqual(anchors,[6968,7344])
        self.assertTrue(anchors[0]<mission['reset_x']<anchors[1])
        mapping=json.loads((ROOT/'assets_msx/terrain/manifest.json').read_text())['source_to_msx_index']
        pixels=(ROOT/'assets_msx/ship/crew.indices').read_bytes()
        for man in range(2):
            poses=[]
            for phase in range(8):
                patch=pixels[(man*8+phase)*308:(man*8+phase+1)*308]
                poses.append(patch)
                expected={}
                for index in (1,phase+8):
                    raw,meta=decode_record(records[f'fgy{index:x}'],plane_constants=True)
                    ox,oy=meta['origin_candidate']
                    for i,v in enumerate(raw):
                        if v:expected[(i%32-ox+10,161-oy+i//32-116)]=mapping[str(v)]
                for (x,y),value in expected.items():self.assertEqual(patch[y*22+x],value)
            self.assertEqual(len(set(poses)),8)

    def test_elevator_signalman_idle_uses_original_downward_arms(self):
        records={n:r for n,_,r in read_ppkc(unpack_rpck((SOURCE/'shapes/world.shp').read_bytes()))}
        meta=json.loads((ROOT/'assets_msx/ship/manifest.json').read_text())
        self.assertEqual(meta['crew_idle_frame'],16)
        self.assertEqual(meta['crew_idle_arms'],[0,8])
        self.assertEqual(meta['crew_pointing_arms']['fixed_left'],1)
        pixels=(ROOT/'assets_msx/ship/crew.indices').read_bytes()
        self.assertEqual(len(pixels),17*308)
        patch=pixels[16*308:17*308]
        expected={}
        mapping=json.loads((ROOT/'assets_msx/terrain/manifest.json').read_text())['source_to_msx_index']
        for name in ('fgy0','fgy8'):
            source,m=decode_record(records[name],plane_constants=True);ox,oy=m['origin_candidate']
            for i,v in enumerate(source):
                if v:expected[(i%32-ox+10,161-oy+i//32-116)]=mapping[str(v)]
        for (x,y),value in expected.items():self.assertEqual(patch[y*22+x],value)
        self.assertTrue(all(patch!=pixels[i*308:(i+1)*308] for i in range(8)))
