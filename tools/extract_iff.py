"""Decode bounded IFF/ILBM images and embedded Rpck-compressed palettes."""
import argparse
from pathlib import Path
import struct
import warnings

from PIL import Image, ImageDraw
from unpack_shapes import unpack_rpck


def unpack_br1(data, size):
    out = bytearray()
    pos = 0
    while pos < len(data):
        if len(out) == size and data[pos:] == b'\x00':
            warnings.warn('ByteRun1: one unconsumed zero byte after complete image (observed selectrank BODY padding)', stacklevel=2)
            break
        control = data[pos]
        pos += 1
        if control == 128:
            continue
        count = control + 1 if control < 128 else 257 - control
        consumed = count if control < 128 else 1
        if pos + consumed > len(data) or len(out) + count > size:
            raise ValueError('truncated or oversized ByteRun1 run')
        out.extend(data[pos:pos + consumed] if control < 128 else data[pos:pos + 1] * count)
        pos += consumed
    if len(out) != size:
        raise ValueError('ByteRun1 output does not match declared dimensions')
    return bytes(out)


def iff_chunks(data):
    if len(data) < 12 or data[:4] != b'FORM' or data[8:12] != b'ILBM':
        raise ValueError('missing IFF/ILBM header')
    end = 8 + struct.unpack_from('>I', data, 4)[0]
    if end != len(data):
        raise ValueError('IFF FORM length does not match file size')
    chunks = {}
    pos = 12
    while pos < end:
        if pos + 8 > end:
            raise ValueError('truncated IFF chunk header')
        key, size = data[pos:pos + 4], struct.unpack_from('>I', data, pos + 4)[0]
        start = pos + 8
        if start + size + (size % 2) > end:
            raise ValueError('IFF chunk outside FORM bounds')
        if key in chunks and key in (b'BMHD', b'BODY', b'CMAP'):
            raise ValueError('duplicate required IFF chunk')
        chunks.setdefault(key, data[start:start + size])
        pos = start + size + (size % 2)
    return chunks


def iff_img(path):
    chunks = iff_chunks(unpack_rpck(path.read_bytes()))
    bm = chunks.get(b'BMHD', b'')
    if len(bm) != 20 or b'BODY' not in chunks:
        raise ValueError('missing BODY or invalid BMHD')
    w, h, x, y, planes, mask, compression, pad, transparent = struct.unpack_from('>HHhhBBBBH', bm)
    if not w or not h or w * h > 4_000_000 or not 1 <= planes <= 8 or mask not in (0, 1, 2) or compression not in (0, 1):
        raise ValueError('unsupported or excessive ILBM dimensions/encoding')
    cmap = chunks.get(b'CMAP', b'')
    if not cmap or len(cmap) % 3 or len(cmap) > 768 or transparent > 255:
        raise ValueError('invalid or missing palette')
    rowbytes = ((w + 15) // 16) * 2
    rowplanes = planes + (mask == 1)
    need = h * rowbytes * rowplanes
    raw = unpack_br1(chunks[b'BODY'], need) if compression == 1 else chunks[b'BODY']
    if len(raw) != need:
        raise ValueError('ILBM BODY size mismatch')
    pixels, alpha = bytearray(w * h), bytearray([255]) * (w * h)
    for yy in range(h):
        for xx in range(w):
            index = yy * w + xx
            pixels[index] = sum(((raw[(yy * rowplanes + p) * rowbytes + xx // 8] >> (7 - xx % 8)) & 1) << p for p in range(planes))
            if mask == 1:
                alpha[index] = 255 if raw[(yy * rowplanes + planes) * rowbytes + xx // 8] & (128 >> (xx % 8)) else 0
            elif mask == 2 and pixels[index] == transparent:
                alpha[index] = 0
    if max(pixels) >= len(cmap) // 3:
        raise ValueError('pixel index exceeds palette')
    im = Image.frombytes('P', (w, h), bytes(pixels))
    im.putpalette(cmap + bytes(768 - len(cmap)))
    if mask == 2:
        im.info['transparency'] = transparent
    elif mask == 1:
        im = im.convert('RGBA')
        im.putalpha(Image.frombytes('L', (w, h), bytes(alpha)))
    return im, dict(width=w, height=h, planes=planes, compression=compression, mask=mask, colors=len(cmap) // 3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='ILBM file or source directory')
    parser.add_argument('output', type=Path, help='new output directory (must not exist)')
    args = parser.parse_args()
    sources = sorted(args.input.iterdir()) if args.input.is_dir() else [args.input]
    images = []
    for p in sources:
        if not p.is_file():
            continue
        data = unpack_rpck(p.read_bytes())
        if data[:4] == b'FORM' and data[8:12] == b'ILBM':
            im, meta = iff_img(p)
            images.append((p.name, im))
            print(p.name, meta)
        elif not args.input.is_dir():
            parser.error('input is not an IFF/ILBM image')
    if not images:
        parser.error('no IFF/ILBM images found')
    args.output.mkdir(parents=True, exist_ok=False)
    sheet = Image.new('RGB', (1080, ((len(images) + 2) // 3) * 260), '#dddddd')
    draw = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(images):
        im.save(args.output / (name.replace('.', '_') + '.png'))
        preview = im.convert('RGBA')
        preview.thumbnail((345, 225), Image.Resampling.NEAREST)
        x, y = (i % 3) * 360 + 5, (i // 3) * 260
        draw.text((x, y + 3), name, fill='black')
        sheet.paste(preview, (x, y + 25), preview)
    sheet.save(args.output / 'contact-sheet.png')


if __name__ == '__main__':
    main()
