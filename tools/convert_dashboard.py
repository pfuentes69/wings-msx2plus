"""Adapt the original IFF dashboard to the mission SCREEN 5 display."""
import argparse
import hashlib
from io import BytesIO
import itertools
import json
from pathlib import Path
from PIL import Image
from convert_hellcat import c_array, pack_pixels
from extract_iff import iff_img
from unpack_shapes import read_ppkc, unpack_rpck
from decode_shapes import decode_record

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'reference_assets/original_files/Wings_of_Fury/shapes'

def original():
    image, metadata = iff_img(SOURCE / 'iff-dash')
    if image.size != (640, 37) or image.mode != 'P':
        raise ValueError('unexpected original dashboard geometry')
    return image, metadata

def panel():
    image, _ = original()
    palette = (ROOT / 'assets_msx/mission_a/palette.bin').read_bytes()
    rgb3 = [(palette[i * 2] >> 4, palette[i * 2 + 1], palette[i * 2] & 7) for i in range(16)]
    source_palette = image.getpalette()
    mapping = []
    for i in range(16):
        color = [v * 7 / 240 for v in source_palette[i * 3:i * 3 + 3]]
        mapping.append(min(range(16), key=lambda j: sum((color[c] - rgb3[j][c]) ** 2 for c in range(3))))
    # Both palette entries 0 and 11 encode source black.
    for i in range(16):
        if source_palette[i * 3:i * 3 + 3] == [0, 0, 0]: mapping[i] = 1
    # Fit the complete artwork inside the eight-pixel hardware mask. Retain
    # source pixel edges; one vertical line is lost when fitting 37 to 36 rows.
    adapted = image.resize((248, 36), Image.Resampling.NEAREST)
    pixels = bytearray([mapping[0]]) * (256 * 40)
    for y in range(36):
        pixels[(y + 4) * 256 + 8:(y + 5) * 256] = bytes(mapping[p] for p in adapted.crop((0, y, 248, y + 1)).tobytes())
    return pixels

def reticle():
    palette = (ROOT / 'assets_msx/mission_a/palette.bin').read_bytes()
    rgb3 = [(palette[i * 2] >> 4, palette[i * 2 + 1], palette[i * 2] & 7) for i in range(16)]
    source_palette = original()[0].getpalette()
    mapping = []
    for i in range(16):
        color = [v * 7 / 240 for v in source_palette[i * 3:i * 3 + 3]]
        mapping.append(min(range(16), key=lambda j: sum((color[c] - rgb3[j][c]) ** 2 for c in range(3))))
    for name, _, raw in read_ppkc(unpack_rpck((SOURCE / 'dash.shp').read_bytes())):
        if name == 'targ':
            pixels, meta = decode_record(raw)
            im = Image.frombytes('P', (meta['width'], meta['height']), pixels).resize((12, 9), Image.Resampling.NEAREST)
            return bytes(0 if p == 16 else mapping[p & 15] for p in im.tobytes())
    raise ValueError('missing original target reticle')

def rle(packed):
    encoded = bytearray()
    for value, group in itertools.groupby(packed):
        count = len(list(group))
        while count:
            take = min(count, 255); encoded.extend((take, value)); count -= take
    return encoded

def ui_shape(name):
    for key, _, raw in read_ppkc(unpack_rpck((SOURCE / 'dash.shp').read_bytes())):
        if key == name:
            pixels, meta = decode_record(raw)
            palette = original()[0].getpalette()
            target = (ROOT / 'assets_msx/mission_a/palette.bin').read_bytes()
            colors = [(target[i*2]>>4,target[i*2+1],target[i*2]&7) for i in range(16)]
            mapping = [min(range(16), key=lambda j: sum((palette[i*3+c]*7/240-colors[j][c])**2 for c in range(3))) for i in range(16)]
            return bytes(0 if v == 16 else mapping[v & 15] for v in pixels), meta
    raise ValueError(f'missing dashboard sprite {name}')

def pilot_frame(kind, level):
    # Forward-looking adaptation: the horizon recedes with altitude; source
    # perspective strips and carrier silhouettes replace the former side map.
    horizon = 17 + level * 2
    pixels = bytearray(48 * 24)
    for y in range(min(24,horizon),24):
        pixels[y*48:(y+1)*48] = bytes([12 if kind == 2 else 1])*48
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

def atlas_slots(count, reserve_water=False, reserve_ship=False):
    frames=json.loads((ROOT/'assets_msx/hellcat/manifest.json').read_text())['animation']['frames']
    tiles=json.loads((ROOT/'assets_msx/mission_a/manifest.json').read_text())['selected']['tile_count']
    occupied=[bytearray(256) for _ in range(512)]
    for f in frames:
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
                    if reserve_ship:return slots,backups,allocate(24,16,14),tails
                    return slots,backups
    raise ValueError('not enough pilot-view atlas rectangles')

def artifacts():
    image,metadata=original();files={}
    def png(path,im):
        output=BytesIO();im.save(output,format='PNG');files[ROOT/path]=output.getvalue()
    def indexed(path,pixels,width,height):
        im=Image.frombytes('P',(width,height),bytes(pixels));p=(ROOT/'assets_msx/mission_a/palette.bin').read_bytes()
        im.putpalette(bytes(v*255//7 for i in range(16) for v in (p[i*2]>>4,p[i*2+1],p[i*2]&7))+bytes(720));png(path,im)
    png('assets_src/dashboard/original.png',image)
    indexed('assets_msx/dashboard/panel.png',panel(),256,40)
    slots, water_backups, ship_slots, tails=atlas_slots(27, reserve_water=True, reserve_ship=True); profiles=[pilot_frame(kind,level) for kind in range(3) for level in range(8)]
    pilot=b''.join(pack_pixels(p) for p in profiles)
    files[ROOT/'assets_msx/dashboard/pilot.indices']=b''.join(profiles)
    indexed('assets_msx/dashboard/pilot-sheet.png',b''.join(profiles),48,24*24)
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
    for name,data in [('DashboardPanel',pack_pixels(panel())),('PilotRLE',pilot),('FarPlaneRLE',pack_pixels(far_pixels))]:
        packed=rle(data);code+=c_array('g_'+name,packed,f'[{len(packed)}]')
    code+='const unsigned char g_PilotX[24] = {'+','.join(str(x) for x,y in slots[:24])+'};\n'
    code+='const unsigned short g_PilotY[24] = {'+','.join(str(y) for x,y in slots[:24])+'};\n'
    code+='const unsigned char g_WaveTailX[3] = {'+','.join(str(x) for x,y in tails)+'};\n'
    code+='const unsigned short g_WaveTailY[3] = {'+','.join(str(y) for x,y in tails)+'};\n'
    code+='const unsigned char g_WaveBackdropX[2] = {'+','.join(str(x) for x,y in water_backups)+'};\n'
    code+='const unsigned short g_WaveBackdropY[2] = {'+','.join(str(y) for x,y in water_backups)+'};\n'
    code+=f"#define FAR_PLANE_COUNT {len(poses)}\n"
    code+='const AircraftShape g_FarShapes[FAR_PLANE_COUNT] = {\n'+''.join(
        f"    {{0, {-p['origin_candidate'][0]}, {-p['origin_candidate'][1]}, 16, {p['height']}, {p['atlas_x']}, {p['atlas_y']}}},\n" for p in poses)+'};\n'
    code+=c_array('g_FarPoseForFrame',pose_ids,f'[{len(pose_ids)}]')
    files[ROOT/'src/generated/dashboard.h']=code.encode()
    records=[]
    for name,offset,raw in read_ppkc(unpack_rpck((SOURCE/'dash.shp').read_bytes())):
        _,meta=decode_record(raw)
        records.append(dict(name=name,offset=offset,sha256=hashlib.sha256(raw).hexdigest(),**meta))
    manifest=dict(records=records, source='reference_assets/original_files/Wings_of_Fury/shapes/iff-dash',source_sha256=hashlib.sha256((SOURCE/'iff-dash').read_bytes()).hexdigest(),**metadata,
        pilot_slots=slots[:24],far_poses=poses,far_pose_for_frame=list(pose_ids),
        wave_palette='original ocean.palette CMAP, nearest fit to five shared blue slots; source zero stays transparent',
        ocean_palette_sha256=hashlib.sha256((SOURCE/'ocean.palette').read_bytes()).hexdigest(),
        wave_source_sha256=hashlib.sha256(b''.join(source_frames)).hexdigest(),
        wave_source_to_msx=wave_mapping(), wave_backdrop_slots=water_backups, wave_tail_slots=tails,
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
