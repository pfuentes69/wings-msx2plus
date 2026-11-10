"""Decode the observed Hellcat planar records to indexed, source-palette PNGs."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from PIL import Image, ImageDraw
from unpack_shapes import unpack_rpck, read_ppkc


def read_palette(data):
    # The standalone game palette has CMAP + four opaque bytes + 32 RGB triples.
    # Those four bytes are not an IFF chunk length and are not used as one.
    if len(data) != 104 or data[:4] != b'CMAP':
        raise ValueError('expected standalone 32-color CMAP palette (104 bytes)')
    return data[8:]


def decode_record(data, layout='plane'):
    if len(data) < 20:
        raise ValueError('truncated shape header')
    stride, height, origin_x, origin_y, source_x, source_y = struct.unpack_from('>HHhhhh', data)
    base_color, unknown = data[12:14]
    maps = list(data[14:20])
    planes = [v for v in maps if v]
    if not stride or stride % 2 or not height or stride > 1024 or height > 1024:
        raise ValueError('invalid or excessive shape dimensions')
    if not planes or maps[:len(planes)] != planes or any(v > 31 for v in planes):
        raise ValueError('invalid/noncontiguous plane maps')
    if base_color > 31 or unknown != 0:
        raise ValueError('unconfirmed base-color/header variant')
    if len(data) != 20 + stride * height * len(planes):
        raise ValueError('shape payload does not match stride, height and plane count')
    if layout not in ('plane', 'row'):
        raise ValueError('unsupported layout')
    width = stride * 8
    pixels = bytearray([base_color]) * (width * height)
    for k, bits in enumerate(planes):
        for y in range(height):
            start = 20 + ((k * height + y) if layout == 'plane' else (y * len(planes) + k)) * stride
            for byte_x in range(stride):
                value = data[start + byte_x]
                for bit in range(8):
                    if value & (128 >> bit):
                        pixels[y * width + byte_x * 8 + bit] |= bits
    metadata = dict(width=width, height=height, stride_bytes=stride,
                    origin_candidate=[origin_x, origin_y], source_position_candidate=[source_x, source_y],
                    base_color_candidate=base_color, unknown_byte=unknown, plane_maps=planes)
    return bytes(pixels), metadata


def make_sheet(images, columns=6, scale=3):
    cell_w = max(im.width for _, im in images) * scale + 16
    cell_h = max(im.height for _, im in images) * scale + 32
    sheet = Image.new('RGB', (columns * cell_w, ((len(images) + columns - 1) // columns) * cell_h), '#00a0f0')
    draw = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(images):
        x, y = (i % columns) * cell_w, (i // columns) * cell_h
        draw.text((x + 5, y + 3), name, fill='black')
        preview = im.convert('RGBA').resize((im.width * scale, im.height * scale), Image.Resampling.NEAREST)
        sheet.paste(preview, (x + 8, y + 24), preview)
    return sheet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='original .shp archive or expanded PPkc archive')
    parser.add_argument('output', type=Path, help='new output directory (must not exist)')
    parser.add_argument('--palette', type=Path, required=True, help='standalone wingspalette file')
    parser.add_argument('--prefix', default='hc', help='record name prefix, or empty string for all')
    parser.add_argument('--layout', choices=['plane', 'row'], default='plane', help='row is a rejected hypothesis for comparison')
    parser.add_argument('--palette-scale', choices=['amiga4', 'stored'], default='amiga4',
                        help='expand nibble-aligned Amiga components to full 8-bit range, or retain stored bytes')
    args = parser.parse_args()
    raw = args.input.read_bytes()
    palette_raw = args.palette.read_bytes()
    palette = read_palette(palette_raw)
    if args.palette_scale == 'amiga4':
        if any(value & 15 for value in palette):
            parser.error('palette is not aligned to 4-bit Amiga RGB components')
        palette = bytes((value >> 4) * 17 for value in palette)
    images, manifest = [], []
    for name, offset, data in read_ppkc(unpack_rpck(raw)):
        if not name.startswith(args.prefix):
            continue
        pixels, meta = decode_record(data, args.layout)
        im = Image.frombytes('P', (meta['width'], meta['height']), pixels)
        im.putpalette(palette + bytes(768 - len(palette)))
        # Zero is a preview transparency hypothesis, not a recovered mask plane.
        im.info['transparency'] = 0
        images.append((name, im))
        manifest.append(dict(name=name, offset=offset, bytes=len(data), record_sha256=hashlib.sha256(data).hexdigest(),
                             png=name + '.png', **meta))
    if not images:
        parser.error('no matching records')
    args.output.mkdir(parents=True, exist_ok=False)
    for name, im in images:
        im.save(args.output / (name + '.png'))
    make_sheet(images).save(args.output / 'contact-sheet.png')
    report = dict(source=str(args.input), source_sha256=hashlib.sha256(raw).hexdigest(),
                  palette=str(args.palette), palette_sha256=hashlib.sha256(palette_raw).hexdigest(),
                  palette_transform=('(component >> 4) * 17' if args.palette_scale == 'amiga4' else 'none'), layout=args.layout,
                  transparency='index 0 assumed for previews; no separate mask established', records=manifest)
    (args.output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'{len(images)} indexed PNGs and contact sheet written to {args.output}')


if __name__ == '__main__':
    main()
