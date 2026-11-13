"""Banked HUD streams must decode to the authored SCREEN 5 assets."""
import hashlib
import json
from pathlib import Path
import re
import sys
import struct
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from convert_dashboard import panel, weapon_patch, bomb_pixels
from convert_hellcat import pack_pixels

class DashboardBankTests(unittest.TestCase):
    def test_banked_streams_are_bounded_and_match_uncompressed_assets(self):
        metadata=json.loads((ROOT/'assets_src/dashboard/manifest.json').read_text())['asset_bank']
        bank=(ROOT/'assets_msx/dashboard/bank_12.bin').read_bytes()
        self.assertEqual(metadata['bank'],12)
        self.assertEqual(metadata['bytes'],len(bank))
        self.assertLessEqual(len(bank),8192)
        self.assertEqual(metadata['sha256'],hashlib.sha256(bank).hexdigest())
        header=(ROOT/'src/generated/dashboard.h').read_text()
        icons=int(re.search(r'#define WEAPON_ICONS_OFFSET (\d+)',header)[1])
        streams=[('DashboardPanel',pack_pixels(panel())),
                 ('PilotRLE',pack_pixels((ROOT/'assets_msx/dashboard/pilot.indices').read_bytes())),
                 ('FarPlaneRLE',pack_pixels((ROOT/'assets_msx/dashboard/far-plane.indices').read_bytes())),
                 ('BombRLE',pack_pixels(bomb_pixels()))]
        for index,(name,expected) in enumerate(streams):
            start=metadata['offsets'][name]
            end=metadata['offsets'][streams[index+1][0]] if index+1<len(streams) else icons
            decoded=bytearray()
            self.assertEqual((end-start)%2,0)
            for at in range(start,end,2):
                count,value=bank[at:at+2]
                self.assertGreater(count,0)
                decoded.extend(bytes([value])*count)
            self.assertEqual(decoded,expected,name)
        self.assertEqual(bank[icons:icons+231],b''.join(pack_pixels(weapon_patch(i)) for i in range(3)))

    def test_original_bomb_frames_preserve_pixels_and_pivots(self):
        from decode_shapes import decode_record
        from unpack_shapes import read_ppkc, unpack_rpck
        source=ROOT/'reference_assets/original_files/Wings_of_Fury/shapes/torpedo.shp'
        records={n:r for n,_,r in read_ppkc(unpack_rpck(source.read_bytes()))}
        mapping=json.loads((ROOT/'assets_msx/terrain/manifest.json').read_text())['source_to_msx_index']
        atlas=(ROOT/'assets_msx/dashboard/bombs.indices').read_bytes()
        for frame,name in enumerate(('bom3','bom5','bom6','bom9','bom7')):
            pixels,meta=decode_record(records[name],plane_constants=True)
            ox,oy=meta['origin_candidate']
            expected={(i%16-ox,i//16-oy):mapping[str(v)] for i,v in enumerate(pixels) if v}
            actual={(i%8-4,i//8-4):v for i,v in enumerate(atlas[frame*64:(frame+1)*64]) if v}
            self.assertEqual(actual,expected,name)
        header=(ROOT/'src/generated/dashboard.h').read_text()
        bank=(ROOT/'assets_msx/dashboard/bank_12.bin').read_bytes()
        ammo=int(re.search(r'#define AMMO_DIGITS_OFFSET (\d+)',header)[1])
        life=int(re.search(r'#define LIFE_DIGITS_OFFSET (\d+)',header)[1])
        self.assertEqual(life-ammo,280)
        self.assertEqual(len(bank)-life,420)

    def test_banked_atlas_tables_preserve_reduced_shape_layout(self):
        meta=json.loads((ROOT/'assets_src/dashboard/manifest.json').read_text())
        bank=(ROOT/'assets_msx/dashboard/bank_7.bin').read_bytes();table=meta['tables_bank']
        self.assertEqual(table['bank'],7)
        self.assertEqual(table['bytes'],len(bank));self.assertLessEqual(len(bank),8192)
        self.assertEqual(table['sha256'],hashlib.sha256(bank).hexdigest())
        start=table['offsets']['g_FarShapes']
        for i,pose in enumerate(meta['far_poses']):
            actual=struct.unpack_from('<HbbBBBH',bank,start+i*9)
            self.assertEqual(actual,(0,-pose['origin_candidate'][0],-pose['origin_candidate'][1],16,pose['height'],pose['atlas_x'],pose['atlas_y']))
        start=table['offsets']['g_FarPoseForFrame']
        self.assertEqual(list(bank[start:start+len(meta['far_pose_for_frame'])]),meta['far_pose_for_frame'])

        frames=json.loads((ROOT/'assets_msx/hellcat/manifest.json').read_text())['animation']['frames']
        start=table['offsets']['g_AircraftShapes']
        for i,frame in enumerate(frames):
            actual=struct.unpack_from('<HbbBBBH',bank,start+i*9)
            self.assertEqual(actual,tuple(frame[k] for k in ('data_offset','dx','dy','width','height','atlas_x','atlas_y')))
