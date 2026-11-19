"""Banked HUD streams and pre-rendered values must match the authored dashboard."""
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from convert_dashboard import panel, bomb_pixels, compose, hud_variants, HUD_ELEMENTS, arrow_frames
from convert_hellcat import pack_pixels


def header_table(name):
    header=(ROOT/'src/generated/dashboard.h').read_text()
    return [int(v) for v in re.search(rf'{name}\[\] = {{([^}}]*)}}',header)[1].split(',')]


class DashboardBankTests(unittest.TestCase):
    def test_banked_streams_are_bounded_and_match_uncompressed_assets(self):
        metadata=json.loads((ROOT/'assets_src/dashboard/manifest.json').read_text())['asset_bank']
        bank=(ROOT/'assets_msx/dashboard/bank_12.bin').read_bytes()
        self.assertEqual(metadata['bank'],12)
        self.assertEqual(metadata['bytes'],len(bank))
        self.assertLessEqual(len(bank),8192)
        self.assertEqual(metadata['sha256'],hashlib.sha256(bank).hexdigest())
        streams=[('DashboardPanel',pack_pixels(panel())),
                 ('FarPlaneRLE',pack_pixels((ROOT/'assets_msx/dashboard/far-plane.indices').read_bytes())),
                 ('BombRLE',pack_pixels(bomb_pixels())),
                 ('ArrowRLE',b''.join(pack_pixels(p) for p,_ in arrow_frames()))]
        for index,(name,expected) in enumerate(streams):
            start=metadata['offsets'][name]
            end=metadata['offsets'][streams[index+1][0]] if index+1<len(streams) else len(bank)
            decoded=bytearray()
            self.assertEqual((end-start)%2,0)
            for at in range(start,end,2):
                count,value=bank[at:at+2]
                self.assertGreater(count,0)
                decoded.extend(bytes([value])*count)
            self.assertEqual(decoded,expected,name)

    def test_the_cockpit_bank_holds_its_shape_slots(self):
        import convert_cockpit
        slots,place=convert_cockpit.art()
        used=max(p[0] for p in place)+1
        bank=(ROOT/f'assets_msx/cockpit/bank_{convert_cockpit.COCKPIT_BANK}.bin').read_bytes()
        self.assertLessEqual(len(bank),8192)
        self.assertEqual(bank,b''.join(pack_pixels(slots[s]) for s in range(1,used)))
        self.assertEqual(slots[0],bytes(48*24))   # the compose buffer

    def test_hud_values_are_byte_aligned_crops_of_the_composed_panel(self):
        banks={b:(ROOT/f'assets_msx/dashboard/bank_{b}.bin').read_bytes() for b in (17,18,19,20)}
        tables={n:header_table(n) for n in ('g_HudBank','g_HudColumn','g_HudRow','g_HudBytes',
                                             'g_HudHeight','g_HudOffset','g_HudSize')}
        for index,(name,bank,states,_) in enumerate(HUD_ELEMENTS):
            column,row=tables['g_HudColumn'][index],tables['g_HudRow'][index]
            width,height=tables['g_HudBytes'][index],tables['g_HudHeight'][index]
            self.assertEqual(tables['g_HudBank'][index],bank)
            self.assertEqual(tables['g_HudSize'][index],width*height)
            for value,state in enumerate(states):
                render=compose(**state)
                crop=bytes(render[(row+y)*256+column*2+x] for y in range(height) for x in range(width*2))
                start=tables['g_HudOffset'][index]+value*width*height
                self.assertEqual(banks[bank][start:start+width*height],pack_pixels(crop),(name,value))
                self.assertLessEqual(start+width*height,8192)

    def test_lit_and_dark_dials_share_one_rectangle(self):
        elements={e['name']:e for e in hud_variants()}
        for dial in ('OIL','FUEL'):
            dark,lit=elements[dial+'_DIAL'],elements[dial+'_DIAL_LIT']
            self.assertEqual([dark[k] for k in ('x','y','width','height')],[lit[k] for k in ('x','y','width','height')])
            self.assertNotEqual(dark['data'],lit['data'])

    def test_original_bomb_frames_preserve_pixels_and_pivots(self):
        from decode_shapes import decode_record
        from unpack_shapes import read_ppkc, unpack_rpck
        source=ROOT/'reference_assets/original_files/Wings_of_Fury/shapes/torpedo.shp'
        records={n:r for n,_,r in read_ppkc(unpack_rpck(source.read_bytes()))}
        mapping=json.loads((ROOT/'assets_msx/terrain/manifest.json').read_text())['source_to_msx_index']
        atlas=(ROOT/'assets_msx/dashboard/bombs.indices').read_bytes()
        pivots=json.loads((ROOT/'assets_src/dashboard/manifest.json').read_text())['bomb_pivots']
        for frame in range(12):
            name=f'bom{frame:x}'
            pixels,meta=decode_record(records[name],plane_constants=True)
            ox,oy=meta['origin_candidate']
            px,py=pivots[frame]
            expected={(i%16-ox,i//16-oy):mapping[str(v)] for i,v in enumerate(pixels) if v}
            actual={(i%8-px,i//8-py):v for i,v in enumerate(atlas[frame*48:(frame+1)*48]) if v}
            self.assertEqual(actual,expected,name)


if __name__ == '__main__':
    unittest.main()
