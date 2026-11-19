"""The front end's artwork from the original (docs/front-end-art.md): shapes
from world.shp, recoloured to the port's palettes and packed for SCREEN 5.

  python tools/convert_screens.py          # src/generated/screens_art.c, assets_msx/screens/*.png
  python tools/convert_screens.py --check  # compare with what is generated

So far, both drawn over the play view in the play palette
(assets_msx/mission_a/palette.bin):
- the "THE END" plate (world shape gmov, 192 x 22);
- the weapon selection panel (selt, 96 x 72) and its highlighted lines
  (rock, bomb, torp), with four play colours lent while it shows.
And on their own palettes, full screen:
- the briefing's palette and small font (the menu's 5 x 7, msx/menu.c, 1 bit
  a pixel): the port's own compact layout, drawn by msx/screen_end.c;
- rank selection (shapes/selectrank, 320 x 200, recomposed to 256 wide) in
  banks 53..56 and its seven highlighted lines (selectrank.shp rnk0..rnk6)
  in bank 57. "Return from R&R" (rnk7) is left out."""
import argparse
from pathlib import Path
from PIL import Image
from decode_shapes import decode_record, read_palette
from unpack_shapes import read_ppkc, unpack_rpck

ROOT = Path(__file__).resolve().parents[1]
SHAPES = ROOT / 'reference_assets/original_files/Wings_of_Fury/shapes'
OUT_C = ROOT / 'src/generated/screens_art.c'          # segment 49: the weapon panel
OUT_END = ROOT / 'src/generated/screen_end_art.c'     # segment 50: "THE END"
OUT_H = ROOT / 'src/generated/screens_art.h'
OUT_PNG = ROOT / 'assets_msx/screens'
RANK_BANKS = (53, 54, 55, 56)   # rank selection's 200 rows, 128 bytes each
RANK_LINE_BANK = 57             # its 7 highlighted lines, 9 rows of 92 bytes each
RANK_INNER = (68, 252)          # the picture's inner columns kept (184): the content is 70..247
RANK_BAR_CUT = 128              # the bars (rows 0..27, 172..199) lose columns 128..191
RANK_LINE_Y, RANK_LINE_STEP, RANK_LINE_X = 91, 10, 64   # rnk0..rnk6 (192 x 9)
# The briefing's palette (0..7 a channel): black, rank.iff's red and blue
# lifted for small letters, its greys for the frame; the values' light grey
# (the capture: 172,170,173).
BRIEF_PALETTE = [(0, 0, 0), (7, 2, 1), (2, 3, 7), (2, 2, 2), (3, 3, 3), (4, 4, 4), (5, 5, 5), (6, 6, 6)] + [(0, 0, 0)] * 8
BRIEF_INK = 7
MENU_C = ROOT / 'src/msx/menu.c'


def small_font():
    """The menu's font (msx/menu.c s_Font: A..Z, 0..9, '>', ' ', '.', ':',
    7 rows of 6 pixels, nibble 0xb ink) as 7 bytes a glyph, bit 7 leftmost."""
    import re
    text = MENU_C.read_text()
    table = text[text.index('s_Font['):text.index('};', text.index('s_Font['))]
    rows = re.findall(r'\{(0x[0-9a-f]{2}(?:,0x[0-9a-f]{2}){20})\}', table)
    out = bytearray()
    for glyph in rows[:40]:
        data = [int(v, 16) for v in glyph.split(',')]
        for r in range(7):
            bits = 0
            for k, byte in enumerate(data[3 * r:3 * r + 3]):
                for n, nibble in enumerate((byte >> 4, byte & 15)):
                    if nibble == 0xb: bits |= 0x80 >> (2 * k + n)
            out.append(bits)
    assert len(out) == 280
    return bytes(out)


def world_shapes(names):
    archive = SHAPES / 'world.shp'
    palette = read_palette((SHAPES / 'wingspalette').read_bytes())   # 32 x (r, g, b), 0..240
    out = {}
    for name, _, record in read_ppkc(unpack_rpck(archive.read_bytes())):
        if name in names:
            pixels, meta = decode_record(record)
            out[name] = (pixels, meta['width'], meta['height'], meta['source_position_candidate'])
    return out, palette


def play_palette():
    data = (ROOT / 'assets_msx/mission_a/palette.bin').read_bytes()
    return [((data[2 * i] >> 4) & 7, data[2 * i + 1] & 7, data[2 * i] & 7) for i in range(16)]   # r, g, b of 0..7


def amiga_rgb(palette):
    """The Amiga palette as (r, g, b) of 0..15 (read_palette's scaled bytes or 12-bit words)."""
    if max(palette) > 255:
        return [((v >> 8) & 15, (v >> 4) & 15, v & 15) for v in palette]
    values = list(palette)
    return [(values[3 * i] >> 4, values[3 * i + 1] >> 4, values[3 * i + 2] >> 4) for i in range(len(values) // 3)]


def recolour(pixels, source, target, avoid=(0,), forced=None):
    """Source colour indices to the nearest target entry (0..7 per channel),
    never one in `avoid` (unless forced); index 0 stays transparent."""
    cache = dict(forced or {})
    out = bytearray(len(pixels))
    for i, c in enumerate(pixels):
        if not c:
            continue
        if c not in cache:
            r, g, b = (v / 15 * 7 for v in source[c])
            cache[c] = min((k for k in range(16) if k not in avoid),
                           key=lambda k: (target[k][0] - r) ** 2 * 3 + (target[k][1] - g) ** 2 * 4 + (target[k][2] - b) ** 2 * 2)
        out[i] = cache[c]
    return bytes(out)


def pack(pixels, width):
    return bytes((pixels[i] << 4) | pixels[i + 1] for i in range(0, len(pixels), 2))


# The weapon panel's warm colours and its band's blue are not in the play
# palette: while the panel shows, the play's greens (12, 15: no island near
# the carrier) and browns (13, 14: a few deck details) are lent to it.
# Source colour -> lent slot: yellow 10; yellow-orange 11 and orange 2;
# red 3 and dark red 4; the band's blue 5. The sky's blue (1) is the sky.
WEAPON_SLOTS = {12: (7, 7, 3), 13: (6, 1, 0), 14: (7, 4, 1), 15: (0, 1, 6)}
WEAPON_FORCED = {10: 12, 11: 14, 2: 14, 3: 13, 4: 13, 5: 15, 1: 0}
WEAPON_LINES = ('rock', 'bomb', 'torp')   # top to bottom in the panel


def c_bytes(name, data, comment):
    lines = [f'/* {comment} */', f'const unsigned char {name}[{len(data)}] = {{']
    for i in range(0, len(data), 24):
        lines.append('    ' + ', '.join(f'0x{b:02x}' for b in data[i:i + 24]) + ',')
    lines.append('};')
    return lines


def preview(pixels, width, height, palette):
    image = Image.frombytes('P', (width, height), pixels)
    image.putpalette([v * 255 // 7 for rgb in palette for v in rgb] + [0] * (768 - 48))
    return image


def artifacts():
    shapes, palette = world_shapes({'gmov', 'selt', *WEAPON_LINES})
    source = amiga_rgb(palette)
    target = play_palette()
    c = ['/* Generated by tools/convert_screens.py; do not edit. */',
         '#include "../msx/banking.h"', 'WINGS_CODE_SEGMENT(WINGS_SEGMENT_SCREENS)']
    end = ['/* Generated by tools/convert_screens.py; do not edit. */',
           '#include "../msx/banking.h"', 'WINGS_CODE_SEGMENT(WINGS_SEGMENT_SCREEN_END)']
    h = ['/* Generated by tools/convert_screens.py; do not edit. */', '#pragma once']
    images = {}
    # "THE END"
    pixels, width, height, _ = shapes['gmov']
    plate = recolour(pixels, source, target)
    images['end-plate.png'] = preview(plate, width, height, target)
    end += c_bytes('g_EndPlate', pack(plate, width), '"THE END" (world shape gmov), 4 bits a pixel, 0 transparent, play palette.')
    h += [f'#define END_PLATE_WIDTH {width}', f'#define END_PLATE_HEIGHT {height}',
          'extern const unsigned char g_EndPlate[];']
    # Weapon selection: the panel, then each line highlighted, in the play
    # palette with the lent slots.
    lent = [WEAPON_SLOTS.get(k, rgb) for k, rgb in enumerate(target)]
    avoid = (0, *WEAPON_SLOTS)
    pixels, width, height, (px, py) = shapes['selt']
    panel = recolour(pixels, source, lent, avoid, WEAPON_FORCED)
    c += c_bytes('g_WeaponPanel', pack(panel, width), 'The weapon panel (selt), 4 bits a pixel, opaque.')
    h += [f'#define WEAPON_PANEL_WIDTH {width}', f'#define WEAPON_PANEL_HEIGHT {height}',
          'extern const unsigned char g_WeaponPanel[];']
    strips, rows, heights, offsets, shown = bytearray(), [], [], [], bytearray(panel)
    for name in WEAPON_LINES:
        line, w, lh, (lx, ly) = shapes[name]
        assert (w, lx) == (width, px), (name, w, lx)
        strip = recolour(line, source, lent, avoid, WEAPON_FORCED)
        offsets.append(len(strips)); rows.append(ly - py); heights.append(lh)
        strips += pack(strip, w)
        if name == 'bomb':
            shown[(ly - py) * width:(ly - py + lh) * width] = strip
    c += c_bytes('g_WeaponLines', bytes(strips), 'The lines highlighted (rock, bomb, torp), 4 bits a pixel.')
    c.append('/* Each line: its first row in the panel, its rows, its offset in g_WeaponLines. */')
    c.append(f'const unsigned char g_WeaponLineRow[3] = {{{", ".join(map(str, rows))}}};')
    c.append(f'const unsigned char g_WeaponLineHeight[3] = {{{", ".join(map(str, heights))}}};')
    c.append(f'const unsigned short g_WeaponLineOffset[3] = {{{", ".join(map(str, offsets))}}};')
    # The lent colours as V9938 palette entries (0RRR0BBB, 00000GGG).
    words = [(r << 4 | b, g) for r, g, b in WEAPON_SLOTS.values()]
    end.append('/* Play palette entries 12..15 while the weapon panel shows (0RRR0BBB, 00000GGG). */')
    end.append(f'const unsigned char g_WeaponColours[8] = {{{", ".join(f"0x{v:02x}" for w in words for v in w)}}};')
    h += ['extern const unsigned char g_WeaponLines[];', 'extern const unsigned char g_WeaponLineRow[3];',
          'extern const unsigned char g_WeaponLineHeight[3];', 'extern const unsigned short g_WeaponLineOffset[3];',
          'extern const unsigned char g_WeaponColours[8];']
    images['weapon-panel.png'] = preview(bytes(shown), width, height, lent)
    # The briefing: its palette and small font in segment 50.
    binaries = {}
    h += [f'#define BRIEF_INK {BRIEF_INK}', 'extern const unsigned char g_BriefPalette[32];',
          'extern const unsigned char g_SmallFont[280];']
    words = [(r << 4 | b, g) for r, g, b in BRIEF_PALETTE]
    end.append('/* The briefing\'s palette (0RRR0BBB, 00000GGG). */')
    end.append(f'const unsigned char g_BriefPalette[32] = {{{", ".join(f"0x{v:02x}" for w in words for v in w)}}};')
    end += c_bytes('g_SmallFont', small_font(), "The menu's 5 x 7 font (A..Z, 0..9, '>', ' ', '.', ':'), 7 rows a glyph, bit 7 leftmost.")
    # Rank selection.
    picture, lines, rank_palette = rank_selection()
    images['rank.png'] = preview(picture, 256, 200, rank_palette)
    data = pack(picture, 256)
    binaries.update({OUT_PNG / f'bank_{b}.bin': data[i * 8192:(i + 1) * 8192] for i, b in enumerate(RANK_BANKS)})
    binaries[OUT_PNG / f'bank_{RANK_LINE_BANK}.bin'] = b''.join(pack(l, 184) for l in lines)
    words = [(r << 4 | b, g) for r, g, b in rank_palette]
    end.append('/* The rank selection palette (0RRR0BBB, 00000GGG). */')
    end.append(f'const unsigned char g_RankPalette[32] = {{{", ".join(f"0x{v:02x}" for w in words for v in w)}}};')
    h += [f'#define RANK_BANK {RANK_BANKS[0]}', f'#define RANK_LINE_BANK {RANK_LINE_BANK}',
          f'#define RANK_LINE_Y {RANK_LINE_Y}', f'#define RANK_LINE_STEP {RANK_LINE_STEP}',
          f'#define RANK_LINE_X {RANK_INNER[0] - 32}', '#define RANK_LINE_BYTES 92', '#define RANK_LINE_HEIGHT 9',
          'extern const unsigned char g_RankPalette[32];']
    texts = {OUT_C: '\n'.join(c) + '\n', OUT_END: '\n'.join(end) + '\n', OUT_H: '\n'.join(h) + '\n'}
    return texts, images, binaries


def rank_selection():
    """selectrank recomposed to 256 x 200 in a 16-colour palette, and the
    seven highlighted lines (184 x 9) at their place in it."""
    from extract_iff import iff_img
    image, meta = iff_img(SHAPES / 'selectrank')
    width, height = image.size
    pixels, cmap = image.tobytes(), image.getpalette()[:3 * meta['colors']]
    rgb = [tuple(round(v * 7 / 255) for v in cmap[3 * i:3 * i + 3]) for i in range(len(cmap) // 3)]
    old = [[rgb[pixels[y * width + x]] for x in range(width)] for y in range(height)]
    # Without Return from R&R: its row of the picture is black inside.
    r_and_r = RANK_LINE_Y + 7 * RANK_LINE_STEP
    for y in range(r_and_r, r_and_r + 9):
        for x in range(RANK_INNER[0], RANK_INNER[1]):
            old[y][x] = (0, 0, 0)
    def column(y, x):
        if y < 28 or y >= 172:      # the bars: one 64-px cut in their flat middle
            return old[y][x if x < RANK_BAR_CUT else x + 64]
        if x < 36: return old[y][x]
        if x < 36 + RANK_INNER[1] - RANK_INNER[0]: return old[y][x - 36 + RANK_INNER[0]]
        return old[y][x + 64]
    new = [[column(y, x) for x in range(256)] for y in range(height)]
    shapes = rank_lines()
    lines = []
    for k in range(7):
        strip, w, lh, (lx, ly) = shapes[f'rnk{k}']
        assert (w, lh, lx, ly) == (192, 9, RANK_LINE_X, RANK_LINE_Y + k * RANK_LINE_STEP), (k, w, lh, lx, ly)
        # The band has the letters as holes (0): the picture's gold shows through.
        cut = RANK_INNER[0] - RANK_LINE_X
        lines.append([[rgb[strip[y * w + x]] if strip[y * w + x] else new[ly + y][36 + x - cut]
                       for x in range(cut, cut + 184)] for y in range(lh)])
    # 16 colours: the most used, the rarest folded into their nearest.
    from collections import Counter
    count = Counter(c for row in new for c in row) + Counter(c for l in lines for row in l for c in row)
    palette = [c for c, _ in count.most_common(16)]
    if (0, 0, 0) in palette: palette.remove((0, 0, 0))
    palette = [(0, 0, 0)] + palette[:15]
    near = lambda c: min(range(16), key=lambda k: sum((a - b) ** 2 for a, b in zip(palette[k], c)))
    index = {c: near(c) for c in count}
    picture = bytes(index[c] for row in new for c in row)
    return picture, [bytes(index[c] for row in l for c in row) for l in lines], palette


def rank_lines():
    from unpack_shapes import read_ppkc as ppkc, unpack_rpck as rpck
    out = {}
    for name, _, record in ppkc(rpck((SHAPES / 'selectrank.shp').read_bytes())):
        pixels, meta = decode_record(record)
        out[name] = (pixels, meta['width'], meta['height'], meta['source_position_candidate'])
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    texts, images, binaries = artifacts()
    if args.check:
        for path, text in texts.items():
            assert path.read_text() == text, f'{path} is out of date'
        for path, data in binaries.items():
            assert path.read_bytes() == data, f'{path} is out of date'
        return
    for path, text in texts.items():
        path.write_text(text)
    OUT_PNG.mkdir(parents=True, exist_ok=True)
    for path, data in binaries.items():
        path.write_bytes(data)
    for name, image in images.items():
        image.convert('RGB').resize((image.width * 3, image.height * 3), Image.NEAREST).save(OUT_PNG / name)


if __name__ == '__main__':
    main()
