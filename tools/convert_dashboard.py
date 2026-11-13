"""Adapt the original IFF dashboard to the mission SCREEN 5 display."""
import argparse
import hashlib
from io import BytesIO
import itertools
import json
import struct
from pathlib import Path
from PIL import Image
from convert_hellcat import c_array, pack_pixels
from extract_iff import iff_img
from unpack_shapes import read_ppkc, unpack_rpck
from decode_shapes import decode_record

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'reference_assets/original_files/Wings_of_Fury/shapes'

DASHBOARD_DIGITS = {
    '0': ('01110','10001','10001','10001','10001','10001','01110'),
    '1': ('00100','01100','00100','00100','00100','00100','01110'),
    '2': ('01110','10001','00001','00010','00100','01000','11111'),
    '3': ('11110','00001','00001','01110','00001','00001','11110'),
    '4': ('00010','00110','01010','10010','11111','00010','00010'),
    '5': ('11111','10000','10000','11110','00001','00001','11110'),
    '6': ('01110','10000','10000','11110','10001','10001','01110'),
    '7': ('11111','00001','00010','00100','01000','01000','01000'),
    '8': ('01110','10001','10001','01110','10001','10001','01110'),
    '9': ('01110','10001','10001','01111','00001','00001','01110'),
}


def original():
    image, metadata = iff_img(SOURCE / 'iff-dash')
    if image.size != (640, 37) or image.mode != 'P':
        raise ValueError('unexpected original dashboard geometry')
    return image, metadata

def dashboard_palette():
    """Use the original instrument colors during the fixed dashboard raster."""
    source = original()[0].getpalette()
    palette = bytearray()
    for i in range(16):
        r, g, b = (round(v * 7 / 240) for v in source[i*3:i*3+3])
        palette.extend(((r << 4) | b, g))
    # Index zero is also the hardware-masked border: keep the flight sky.
    palette[:2] = (ROOT / 'assets_msx/mission_a/palette.bin').read_bytes()[:2]
    # A shared dark-sea slot keeps the separator stable while colors change.
    # Move the dashboard blue to unused pink slot 9, leaving slot 1 unchanged.
    palette[18:20] = palette[2:4]
    palette[2:4] = (ROOT / 'assets_msx/mission_a/palette.bin').read_bytes()[2:4]
    return bytes(palette)


def dashboard_shape(name):
    for key, _, raw in read_ppkc(unpack_rpck((SOURCE / 'dash.shp').read_bytes())):
        if key == name:
            pixels, meta = decode_record(raw)
            return Image.frombytes('P', (meta['width'], meta['height']), pixels), meta
    raise ValueError(f'missing dashboard sprite {name}')


def weapon_patch(weapon):
    sprite,_=dashboard_shape(('bomb','misl','torp')[weapon])
    sprite=sprite.crop((12,0,64,5)).resize((20,5),Image.Resampling.NEAREST)
    patch=bytearray([11])*22*7
    for yy in range(7): patch[yy*22]=6; patch[yy*22+21]=6
    for yy in range(5):
        for xx in range(20):
            c=sprite.getpixel((xx,yy))
            patch[(yy+1)*22+xx+1]=11 if c==16 or c&15==0 else 9 if c&15==1 else c&15
    return bytes(patch)


def panel():
    image, _ = original()
    image = image.copy()

    def paste_shape(name, x, y):
        sprite, meta = dashboard_shape(name)
        for yy in range(sprite.height):
            for xx in range(sprite.width):
                color = sprite.getpixel((xx, yy))
                if color != 16 and 0 <= x+xx < 640 and 0 <= y+yy < 37:
                    image.putpixel((x+xx, y+yy), color & 15)

    # Separate original sprites are absent from iff-dash. These static values
    # reproduce the supplied reference; gameplay instruments remain pending.
    for y in range(10, 17):
        for x in range(28, 80): image.putpixel((x, y), 11)
    paste_shape('bomb', 16, 11)
    for name, x, y in [('ndlg', 208, 19), ('ndln', 430, 19)]:
        _, meta = dashboard_shape(name)
        ox, oy = meta['origin_candidate']
        paste_shape(name, x-ox, y-oy)
    adapted = image.resize((248, 36), Image.Resampling.NEAREST)
    pixels = bytearray([1]) * (256 * 40)
    for y in range(36):
        pixels[(y+4)*256+8:(y+5)*256] = bytes(11 if p == 0 else 9 if p == 1 else p & 15
            for p in adapted.crop((0, y, 248, y+1)).tobytes())
    def rectangle(x, y, width, height, color):
        for yy in range(y, y+height):
            pixels[yy*256+x:yy*256+x+width] = bytes([color])*width

    def glyph(rows, x, y, color):
        for yy, row in enumerate(rows):
            for xx, bit in enumerate(row):
                if bit == '1': pixels[(y+yy)*256+x+xx] = color

    # Clear complete legacy counter regions before drawing aligned frames.
    # Partial repainting leaves stepped black edges from iff-dash underneath.
    rectangle(19, 22, 22, 11, 6)
    rectangle(50, 22, 12, 11, 6)
    rectangle(201, 12, 48, 23, 6)

    # All numbers share one 5x7 face, including score and ammunition zeroes.
    digits = DASHBOARD_DIGITS
    rectangle(19, 22, 21, 11, 11)
    rectangle(50, 22, 11, 11, 11)
    for digit, x in [('3',20), ('0',30), ('3',51)]:
        rectangle(x, 23, 9, 9, 15)
        glyph(digits[digit], x+2, 24, 12)
    # Separate fields share two-pixel side padding and one-pixel vertical padding.
    rectangle(201, 13, 45, 9, 11)
    for x in range(203, 240, 6): glyph(digits['0'], x, 14, 15)
    rectangle(201, 24, 15, 9, 11)
    for x in (203, 209): glyph(digits['0'], x, 25, 15)

    # The dial bases have room for seven rows. Use full-width letterforms
    # instead of squeezing the legends into the previous 3x5 face.
    glyphs = {'O': ('01110','10001','10001','10001','10001','10001','01110'),
              'I': ('11111','00100','00100','00100','00100','00100','11111'),
              'L': ('10000','10000','10000','10000','10000','10000','11111'),
              'F': ('11111','10000','10000','11110','10000','10000','10000'),
              'U': ('10001','10001','10001','10001','10001','10001','01110'),
              'E': ('11111','10000','10000','11110','10000','10000','11111')}
    for word, center, left, right in [('OIL',89,75,102), ('FUEL',175,162,189)]:
        rectangle(left, 32, right-left, 7, 11)
        width = len(word)*6-1
        x = center-width//2
        for char in word:
            glyph(glyphs[char], x, 32, 15)
            x += 6
    icon=weapon_patch(0)
    for yy in range(7): pixels[(14+yy)*256+18:(14+yy)*256+40]=icon[yy*22:(yy+1)*22]
    return pixels

def reticle():
    im, _ = dashboard_shape('targ')
    im = im.resize((12, 9), Image.Resampling.NEAREST)
    return bytes(0 if p == 16 else 9 if p & 15 == 1 else p & 15 for p in im.tobytes())

def rle(packed):
    encoded = bytearray()
    for value, group in itertools.groupby(packed):
        count = len(list(group))
        while count:
            take = min(count, 255); encoded.extend((take, value)); count -= take
    return encoded

def ui_shape(name):
    im, meta = dashboard_shape(name)
    return bytes(0 if p == 16 else 9 if p & 15 == 1 else p & 15 for p in im.tobytes()), meta

def pilot_frame(kind, level):
    # Forward-looking adaptation: the horizon recedes with altitude; source
    # perspective strips and carrier silhouettes replace the former side map.
    horizon = 17 + level * 2
    pixels = bytearray([2]) * (48 * 24)
    for y in range(min(24,horizon),24):
        pixels[y*48:(y+1)*48] = bytes([6 if kind == 2 else 9])*48
    if kind:
        name = '3dl9' if kind == 2 else '3dc' + chr(ord('a') + max(0,7-level))
        source, meta = ui_shape(name)
        width = max(2,round(meta['width']*48/128))
        resized = Image.frombytes('P',(meta['width'],meta['height']),source).resize((width,meta['height']),Image.Resampling.NEAREST)
        ox = round(meta['origin_candidate'][0]*48/128)
        oy = meta['origin_candidate'][1]
        for yy in range(meta['height']):
            for xx in range(width):
                dx,dy=24-ox+xx,horizon-oy+yy
                color=resized.tobytes()[yy*width+xx]
                if color and 0<=dx<48 and 0<=dy<24: pixels[dy*48+dx]=color
    target=reticle()
    for y in range(9):
        for x in range(12):
            c=target[y*12+x]
            if c: pixels[(4+y)*48+18+x]=c
    return bytes(pixels)

def ocean_artwork():
    """Keep source wave indices and the separate ocean palette together."""
    palette, _ = iff_img(SOURCE / 'ocean.palette')
    records={name:raw for name,_,raw in read_ppkc(unpack_rpck((SOURCE/'world.shp').read_bytes()))}
    frames=[]
    for letter in 'abcdefghijkl':
        pixels,meta=decode_record(records['wav'+letter], plane_constants=True)
        if (meta['width'],meta['height'])!=(96,11): raise ValueError('wave dimensions changed')
        if any(v == 0 for v in pixels[192:]):
            raise ValueError('wave transparency extends beyond the two restored rows')
        frames.append(pixels)
    return frames, bytes(palette.getpalette()[:96])

def wave_mapping():
    _, source = ocean_artwork()
    target = (ROOT / 'assets_msx/mission_a/palette.bin').read_bytes()
    colors = [(target[i*2] >> 4, target[i*2+1], target[i*2] & 7) for i in range(16)]
    # Retain the shared aircraft palette. Fit opaque ocean shades to its five
    # blue slots; zero alone is transparent, never a substitute for dark sea.
    return {i: (0 if i == 0 else min(range(1,6), key=lambda j:
        sum((source[i*3+c]*7/240-colors[j][c])**2 for c in range(3))))
        for i in range(32)}

def waves():
    frames, _ = ocean_artwork()
    mapping = wave_mapping()
    return [bytes(mapping[v] for v in frame) for frame in frames]

BOMB_NAMES = ('bom3','bom5','bom6','bom9','bom7')

def bomb_pixels():
    """Original horizontal/diagonal/down poses, padded around their source pivot."""
    records={n:r for n,_,r in read_ppkc(unpack_rpck((SOURCE/'torpedo.shp').read_bytes()))}
    mapping=json.loads((ROOT/'assets_msx/terrain/manifest.json').read_text())['source_to_msx_index']
    result=bytearray(5*64)
    for frame,name in enumerate(BOMB_NAMES):
        pixels,meta=decode_record(records[name],plane_constants=True)
        ox,oy=meta['origin_candidate']
        for i,color in enumerate(pixels):
            if not color:continue
            x,y=i%meta['width']-ox+4,i//meta['width']-oy+4
            if not (0<=x<8 and 0<=y<8):raise ValueError('bomb exceeds padded frame')
            result[frame*64+y*8+x]=mapping[str(color)]
    return bytes(result)

def atlas_slots(count, reserve_water=False, reserve_ship=False, reserve_combat=False, reserve_crew=False, frames=None):
    if frames is None: frames=json.loads((ROOT/'assets_msx/hellcat/manifest.json').read_text())['animation']['frames']
    tiles=json.loads((ROOT/'assets_msx/mission_a/manifest.json').read_text())['selected']['tile_count']
    occupied=[bytearray(256) for _ in range(512)]
    for f in frames:
        if f.get('streamed'): continue
        for y in range(f['atlas_y']-512,f['atlas_y']-512+f['height']):
            occupied[y][f['atlas_x']:f['atlas_x']+f['width']]=bytes([1])*f['width']
    for tile in range(tiles):
        x=tile%288//9*8;y=tile//288*256+180+tile%9*8
        for row in range(y,y+8):occupied[row][x:x+8]=bytes([1])*8
    slots=[]
    for y in range(489):
        for x in range(0,209,2):
            if all(not any(occupied[row][x:x+48]) for row in range(y,y+24)):
                slots.append((x,y+512))
                for row in range(y,y+24):occupied[row][x:x+48]=bytes([1])*48
                if len(slots)==count:
                    if not reserve_water: return slots
                    def allocate(number,width,height):
                        result=[]
                        for yy in range(513-height):
                            for xx in range(0,257-width,2):
                                if all(not any(occupied[r][xx:xx+width]) for r in range(yy,yy+height)):
                                    result.append((xx,yy+512))
                                    for r in range(yy,yy+height):occupied[r][xx:xx+width]=bytes([1])*width
                                    if len(result)==number:return result
                        raise ValueError(f'not enough {width}x{height} atlas rectangles')
                    backups=allocate(2,256,4)
                    tails=allocate(3,96,2)
                    if reserve_ship:
                        ships = allocate(24,16,14)
                        if reserve_combat:
                            if reserve_crew:
                                crew=allocate(34,22,7)
                                weapons=allocate(36,8,8)
                                return slots,backups,ships,tails,weapons,crew,allocate(5,8,8)
                            return slots,backups,ships,tails,allocate(36,8,8)
                        return slots,backups,ships,tails
                    return slots,backups
    raise ValueError('not enough pilot-view atlas rectangles')

def artifacts():
    image,metadata=original();files={}
    def png(path,im):
        output=BytesIO();im.save(output,format='PNG');files[ROOT/path]=output.getvalue()
    def indexed(path,pixels,width,height, dashboard=False):
        im=Image.frombytes('P',(width,height),bytes(pixels));p=dashboard_palette() if dashboard else (ROOT/'assets_msx/mission_a/palette.bin').read_bytes()
        im.putpalette(bytes(v*255//7 for i in range(16) for v in (p[i*2]>>4,p[i*2+1],p[i*2]&7))+bytes(720));png(path,im)
    png('assets_src/dashboard/original.png',image)
    indexed('assets_msx/dashboard/panel.png',panel(),256,40, dashboard=True)
    files[ROOT/'assets_msx/dashboard/palette.bin']=dashboard_palette()
    slots, water_backups, ship_slots, tails, weapon_backups, crew_slots, bomb_slots=atlas_slots(27, reserve_water=True, reserve_ship=True, reserve_combat=True, reserve_crew=True); profiles=[pilot_frame(kind,level) for kind in range(3) for level in range(8)]
    pilot=b''.join(pack_pixels(p) for p in profiles)
    files[ROOT/'assets_msx/dashboard/pilot.indices']=b''.join(profiles)
    indexed('assets_msx/dashboard/pilot-sheet.png',b''.join(profiles),48,24*24, dashboard=True)
    water=waves();files[ROOT/'assets_msx/dashboard/waves.sc5']=b''.join(pack_pixels(w) for w in water)
    files[ROOT/'assets_msx/dashboard/waves.indices']=b''.join(water)
    indexed('assets_msx/dashboard/waves.png',b''.join(water),96,11*12)
    source_frames, ocean_palette = ocean_artwork()
    files[ROOT/'assets_src/dashboard/waves.indices']=b''.join(source_frames)
    files[ROOT/'assets_src/dashboard/ocean-palette.rgb']=bytes(ocean_palette)
    source_sheet=Image.frombytes('P',(96,132),b''.join(source_frames))
    source_sheet.putpalette(bytes((v>>4)*17 for v in ocean_palette)+bytes(672))
    source_sheet.info['transparency']=0
    png('assets_src/dashboard/waves-ocean.png',source_sheet)
    reduced={name:raw for name,_,raw in read_ppkc(unpack_rpck((SOURCE/'8thscale.shp').read_bytes()))}
    names=[name for name in reduced if name.startswith('lpn')]
    mapping=json.loads((ROOT/'assets_msx/terrain/manifest.json').read_text())['source_to_msx_index']
    poses=[]; far_pixels=bytearray()
    for index,name in enumerate(names):
        raw=reduced[name]; pixels,meta=decode_record(raw,allow_reduced_flag=True,plane_constants=True)
        pixels=bytes(0 if v==0 else mapping[str(v)] for v in pixels)
        x,y=slots[24+index//12];x+=(index%3)*16;y+=(index%12//3)*5
        poses.append(dict(name=name,atlas_x=x,atlas_y=y,sha256=hashlib.sha256(raw).hexdigest(),**meta))
        far_pixels.extend(pixels+bytes(16*(5-meta['height'])))
    animation=json.loads((ROOT/'assets_msx/hellcat/manifest.json').read_text())['animation']
    selected=['lpnn']*len(animation['frames'])
    table_start=(ROOT/'reference_assets/original_files/Wings_of_Fury/wings').read_bytes().find(b'lpn2lpn1lpn0')-160
    if table_start != 0x13ed4: raise ValueError('reduced aircraft table moved')
    exe=(ROOT/'reference_assets/original_files/Wings_of_Fury/wings').read_bytes()
    def slot_name(slot):return exe[table_start+slot*4:table_start+slot*4+4].decode()
    for bank,right in [('left_bank',False),('right_bank',True)]:
        source_names=animation['evidence']['source_tables'][bank]['names']
        for frame,meta in enumerate(animation['frames']):
            if meta['name'] not in source_names:continue
            phase=source_names.index(meta['name'])
            if phase==0:continue
            if phase<=8 or phase>=18:
                step=phase if phase<=8 else 26-phase
                slot=52+((step-1)//4)+(2 if right else 0)
            else:slot=phase+47+(9 if right != (phase>13) else 0)
            selected[frame]=slot_name(slot)
    for ids,labels in [(animation['pitch_right'],['lpnp','lpnp','lpno','lpno','lpnn','lpnq','lpnq','lpnr','lpnr','lpns']),
                       (animation['pitch_left'],['lpn2','lpn2','lpn1','lpn1','lpn0','lpn3','lpn3','lpn4','lpn4','lpn5'])]:
        for frame,name in zip(ids,labels): selected[frame]=name
    pose_ids=bytes(names.index(name) for name in selected)
    files[ROOT/'assets_msx/dashboard/far-plane.indices']=bytes(far_pixels)
    indexed('assets_msx/dashboard/far-poses.png',far_pixels,16,5*len(poses))
    code='/* Generated by tools/convert_dashboard.py; do not edit. */\n#pragma once\n'
    tiles=bytes(c for d in '0123456789' for row in DASHBOARD_DIGITS[d]
                for c in ([15,15]+[12 if bit == '1' else 15 for bit in row]+[15]))
    ammo_digits=pack_pixels(tiles)
    code+=c_array('g_DashboardPalette',dashboard_palette(),'[32]')
    bundle=bytearray(); offsets={}
    for name,data in [('DashboardPanel',pack_pixels(panel())),('PilotRLE',pilot),('FarPlaneRLE',pack_pixels(far_pixels)),('BombRLE',pack_pixels(bomb_pixels()))]:
        offsets[name]=len(bundle); bundle.extend(rle(data))
        code+=f'#define {name.upper()}_OFFSET {offsets[name]}\n'
    code+='#define DASHBOARD_BANK 12\n'
    # Prebuilt packed icon patches are read only when changing the loadout.
    icons=bytearray()
    for weapon in range(3): icons.extend(pack_pixels(weapon_patch(weapon)))
    code+=f'#define WEAPON_ICONS_OFFSET {len(bundle)}\n'
    bundle.extend(icons)

    # Black frame and white padding around the one-digit lives counter.
    life_tiles=bytes(c for d in '0123456789' for row in DASHBOARD_DIGITS[d]
        for c in ([11,15,15]+[12 if bit=='1' else 15 for bit in row]+[15,15,11,6]))
    code+=f'#define AMMO_DIGITS_OFFSET {len(bundle)}\n';bundle.extend(ammo_digits)
    code+=f'#define LIFE_DIGITS_OFFSET {len(bundle)}\n';bundle.extend(pack_pixels(life_tiles))
    if len(bundle)>8192: raise ValueError('dashboard assets exceed bank 12')
    files[ROOT/'assets_msx/dashboard/bank_12.bin']=bytes(bundle)
    tables=bytearray();table_offsets={}
    table_header='/* Generated by tools/convert_dashboard.py; do not edit. */\n#pragma once\n'
    def table(name,kind,values):
        nonlocal table_header
        table_offsets[name]=len(tables)
        table_header+=f'#define {name} (({kind}*)(g_DashboardTables+{len(tables)}))\n'
        for value in values:tables.extend(struct.pack('<H' if kind=='unsigned short' else 'B',value))
    for name,slots0 in [('Bomb',bomb_slots),('Pilot',slots[:24]),('WaveTail',tails),('WaveBackdrop',water_backups),('WeaponBackup',weapon_backups)]:
        table('g_'+name+'X','unsigned char',[x for x,y in slots0])
        table('g_'+name+'Y','unsigned short',[y for x,y in slots0])
    code+=f"#define FAR_PLANE_COUNT {len(poses)}\n"
    table_offsets['g_FarShapes']=len(tables)
    table_header+=f'#define g_FarShapes ((AircraftShape*)(g_DashboardTables+{len(tables)}))\n'
    for p in poses:tables.extend(struct.pack('<HbbBBBH',0,-p['origin_candidate'][0],-p['origin_candidate'][1],16,p['height'],p['atlas_x'],p['atlas_y']))
    table('g_FarPoseForFrame','unsigned char',pose_ids)
    tables.extend(bytes((-len(tables))%64))
    table_header+=f'#define DASHBOARD_TABLE_BYTES {len(tables)}\nextern unsigned char g_DashboardTables[DASHBOARD_TABLE_BYTES];\n'
    files[ROOT/'src/generated/dashboard_tables.h']=table_header.encode()
    code+='unsigned char g_DashboardTables[DASHBOARD_TABLE_BYTES];\n'
    if len(tables)>8192:raise ValueError('dashboard tables exceed bank 7')
    code+=f'#define AIRCRAFT_TABLE_OFFSET {len(tables)}\n'
    table_offsets['g_AircraftShapes']=len(tables)
    for frame in animation['frames']:
        tables.extend(struct.pack('<HbbBBBH',frame['data_offset'],frame['dx'],frame['dy'],frame['width'],frame['height'],frame['atlas_x'],frame['atlas_y']))
    if len(tables)>8192:raise ValueError('dashboard tables exceed bank 7')
    files[ROOT/'assets_msx/dashboard/bank_7.bin']=bytes(tables)
    files[ROOT/'assets_msx/dashboard/bombs.indices']=bomb_pixels()
    indexed('assets_msx/dashboard/bombs.png',bomb_pixels(),8,40)
    files[ROOT/'src/generated/dashboard.h']=code.encode()
    records=[]
    for name,offset,raw in read_ppkc(unpack_rpck((SOURCE/'dash.shp').read_bytes())):
        _,meta=decode_record(raw)
        records.append(dict(name=name,offset=offset,sha256=hashlib.sha256(raw).hexdigest(),**meta))
    manifest=dict(records=records, source='reference_assets/original_files/Wings_of_Fury/shapes/iff-dash',source_sha256=hashlib.sha256((SOURCE/'iff-dash').read_bytes()).hexdigest(),**metadata,
        tables_bank=dict(bank=7,bytes=len(tables),offsets=table_offsets,sha256=hashlib.sha256(tables).hexdigest()),
        asset_bank=dict(bank=12,bytes=len(bundle),offsets=offsets,sha256=hashlib.sha256(bundle).hexdigest()),
        bomb_slots=bomb_slots,bomb_names=BOMB_NAMES,
        bomb_source='torpedo.shp',bomb_source_sha256=hashlib.sha256((SOURCE/'torpedo.shp').read_bytes()).hexdigest(),
        bomb_pose_ticks=[5,3],bomb_timing='MSX adaptation: horizontal 200 ms, diagonal 120 ms, then vertical; 25 Hz weapon clock',pilot_slots=slots[:24],far_poses=poses,far_pose_for_frame=list(pose_ids),
        dashboard_palette='original iff-dash RGB4 quantized to RGB3; shared flight border/sea slots 0/1; dashboard blue relocated to 9',
        static_instruments=dict(secondary_stock=30,lives=3,score='0000000',oil_needle='ndlg',fuel_needle='ndln'),
        wave_palette='original ocean.palette CMAP, nearest fit to five shared blue slots; source zero stays transparent',
        ocean_palette_sha256=hashlib.sha256((SOURCE/'ocean.palette').read_bytes()).hexdigest(),
        wave_source_sha256=hashlib.sha256(b''.join(source_frames)).hexdigest(),
        wave_source_to_msx=wave_mapping(), wave_backdrop_slots=water_backups, wave_tail_slots=tails, weapon_backups=weapon_backups,
        wave_names=['wav'+c for c in 'abcdefghijkl'],target=dict(width=256,height=40,visible_width=248),
        scope='original dashboard and perspective sprites; forward-looking altitude profiles and lookahead classification are MSX adaptations')
    files[ROOT/'assets_src/dashboard/manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    return files

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true'); args = parser.parse_args()
    for path, data in artifacts().items():
        if args.check:
            if not path.exists() or path.read_bytes() != data: parser.error(f'stale dashboard: {path}')
        else:
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
