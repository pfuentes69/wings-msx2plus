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
  in bank 57. "Return from R&R" (rnk7) is left out.
And the intro (docs/intro.md), before rank selection:
- the title (shapes/wingstitle, 320 x 200, scaled to 256 wide), banks 59..62;
- the credits and the story ("A Time of Fury", the executable's text): the
  port's own pages, in the menu's font (drawn at run time) with the
  original's names in newarmyfont and the USI logo (creditscreen), bank 63."""
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
TITLE_BANKS = (59, 60, 61, 62)   # the title's 200 rows, 128 bytes each
INTRO_BANK = 63                  # the credits' and story's bitmaps
STORY_BANK = 24                  # the story's lines, STORY_LINE bytes each
TITLE_TOP = 6                    # the title's first row of the 212
STORY_COLUMNS = 40               # characters a story line (6 px each)
STORY_LINE = 42                  # bytes a stored line (the Text routine's most)
EXE = ROOT / 'reference_assets/original_files/Wings_of_Fury/wings'
# The intro pages' colours (0..7 a channel): black; the text's light grey;
# the roles' grey; the names' oranges (creditscreen: each line lighter at
# the top); the heading's golds (wingstitle); the USI logo's blues.
INTRO_FIXED = [(0, 0, 0), (6, 6, 6), (4, 4, 5), (7, 4, 0), (6, 3, 0), (5, 2, 0), (4, 1, 0), (7, 6, 2), (6, 4, 0)]
INTRO_TEXT, INTRO_ROLE = 1, 2
HEADING_SHADES = (7, 7)
# creditscreen's lines (rows), each cut in its role (to the colon) and its
# name: (rows, role's columns, name's columns), and where the page puts them.
CREDIT_LINES = (((13, 28), (38, 191), (198, 303)), ((45, 60), (38, 141), (146, 304)), ((76, 87), (39, 106), (114, 254)))
CREDIT_ROWS = ((22, 38), (58, 74), (94, 106))   # role's, name's first row
# The menu font's extra glyphs for the intro's text (5 x 7 in 6 px, bit 7
# leftmost): , ' ! - ( ) & ?
EXTRA_GLYPHS = {
    ',': ('......', '......', '......', '......', '......', '..#...', '.#....'),
    "'": ('..#...', '..#...', '.#....', '......', '......', '......', '......'),
    '!': ('..#...', '..#...', '..#...', '..#...', '..#...', '......', '..#...'),
    '-': ('......', '......', '......', '.###..', '......', '......', '......'),
    '(': ('...#..', '..#...', '.#....', '.#....', '.#....', '..#...', '...#..'),
    ')': ('.#....', '..#...', '...#..', '...#..', '...#..', '..#...', '.#....'),
    '&': ('.##...', '#..#..', '#.#...', '.#....', '#.#.#.', '#..#..', '.##.#.'),
    '?': ('.###..', '#...#.', '....#.', '...#..', '..#...', '......', '..#...'),
}
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
    for glyph in EXTRA_GLYPHS.values():
        out += bytes(sum(0x80 >> i for i, v in enumerate(row) if v == '#') for row in glyph)
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
          f'extern const unsigned char g_SmallFont[{280 + 7 * len(EXTRA_GLYPHS)}];',
          f'#define SMALL_FONT_EXTRA "{"".join(EXTRA_GLYPHS)}"']
    words = [(r << 4 | b, g) for r, g, b in BRIEF_PALETTE]
    end.append('/* The briefing\'s palette (0RRR0BBB, 00000GGG). */')
    end.append(f'const unsigned char g_BriefPalette[32] = {{{", ".join(f"0x{v:02x}" for w in words for v in w)}}};')
    end += c_bytes('g_SmallFont', small_font(), "The menu's 5 x 7 font (A..Z, 0..9, '>', ' ', '.', ':', then SMALL_FONT_EXTRA), 7 rows a glyph, bit 7 leftmost.")
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
    # The intro: the title, then the credits' and the story's pieces.
    title, title_palette = intro_title()
    images['title.png'] = preview(title, 256, 200, title_palette)
    data = pack(title, 256)
    binaries.update({OUT_PNG / f'bank_{b}.bin': data[i * 8192:(i + 1) * 8192] for i, b in enumerate(TITLE_BANKS)})
    words = [(r << 4 | b, g) for r, g, b in title_palette]
    end.append('/* The title\'s palette (0RRR0BBB, 00000GGG). */')
    end.append(f'const unsigned char g_TitlePalette[32] = {{{", ".join(f"0x{v:02x}" for w in words for v in w)}}};')
    h += [f'#define TITLE_BANK {TITLE_BANKS[0]}', f'#define TITLE_TOP {TITLE_TOP}',
          'extern const unsigned char g_TitlePalette[32];']
    bank, story, story_offset, pieces, pages, intro_palette, page_images = intro_pages()
    binaries[OUT_PNG / f'bank_{INTRO_BANK}.bin'] = bank
    binaries[OUT_PNG / f'bank_{STORY_BANK}.bin'] = story
    for i, page in enumerate(page_images):
        images[f'intro-{i}.png'] = preview(page, 256, 212, intro_palette)
    words = [(r << 4 | b, g) for r, g, b in intro_palette]
    end.append('/* The credits\' and story\'s palette (0RRR0BBB, 00000GGG). */')
    end.append(f'const unsigned char g_IntroPalette[32] = {{{", ".join(f"0x{v:02x}" for w in words for v in w)}}};')
    end.append('/* The bitmaps: bank, offset, bytes a row, rows, x (even), y. */')
    end.append(f'const unsigned char g_IntroPieceBank[{len(pieces)}] = {{{", ".join(str(p["bank"]) for p in pieces)}}};')
    end.append(f'const unsigned short g_IntroPieceOffset[{len(pieces)}] = {{{", ".join(str(p["offset"]) for p in pieces)}}};')
    for key, ctype in (('bytes', 'char'), ('height', 'char'), ('x', 'char'), ('y', 'char')):
        end.append(f'const unsigned {ctype} g_IntroPiece{key.title()}[{len(pieces)}] = {{{", ".join(str(p[key]) for p in pieces)}}};')
    end.append('/* The story\'s pages: their first line (STORY_LINE bytes each from')
    end.append(' * STORY_OFFSET in STORY_BANK), how many, and the first row. */')
    for key in ('first', 'count', 'top'):
        end.append(f'const unsigned char g_StoryPage{key.title()}[{len(pages)}] = {{{", ".join(str(p[key]) for p in pages)}}};')
    h += [f'#define INTRO_BANK {INTRO_BANK}', f'#define INTRO_PIECES {len(pieces)}',
          f'#define INTRO_PIECE_HEADING {len(pieces) - 1}', f'#define INTRO_TEXT {INTRO_TEXT}', f'#define INTRO_ROLE {INTRO_ROLE}',
          f'#define STORY_PAGES {len(pages)}', f'#define STORY_LINE {STORY_LINE}', f'#define STORY_BANK {STORY_BANK}', f'#define STORY_OFFSET {story_offset}',
          f'#define STORY_COLUMNS {STORY_COLUMNS}',
          'extern const unsigned char g_IntroPalette[32];', 'extern const unsigned short g_IntroPieceOffset[];',
          'extern const unsigned char g_IntroPieceBank[], g_IntroPieceBytes[], g_IntroPieceHeight[], g_IntroPieceX[], g_IntroPieceY[];',
          'extern const unsigned char g_StoryPageFirst[], g_StoryPageCount[], g_StoryPageTop[];']
    texts = {OUT_C: '\n'.join(c) + '\n', OUT_END: '\n'.join(end) + '\n', OUT_H: '\n'.join(h) + '\n'}
    return texts, images, binaries


def quantize(colours, count, fixed=((0, 0, 0),)):
    """count colours (0..7 a channel) for a Counter of colours: the fixed
    ones, then each next the one that most lowers the weighted error."""
    d = lambda a, b: (a[0] - b[0]) ** 2 * 3 + (a[1] - b[1]) ** 2 * 4 + (a[2] - b[2]) ** 2 * 2
    palette = list(fixed)
    while len(palette) < count:
        best = max((c for c in colours if c not in palette),
                   key=lambda k: sum(w * max(0, min(d(q, p) for p in palette) - d(q, k)) for q, w in colours.items()),
                   default=None)
        if best is None: break
        palette.append(best)
    palette += [(0, 0, 0)] * (count - len(palette))
    return palette, lambda c: min(range(count), key=lambda k: d(palette[k], c))


def intro_title():
    """wingstitle, box-scaled from 320 to 256 wide (the whole picture kept;
    its texts stay legible), in its 16 most telling colours."""
    from extract_iff import iff_img
    from collections import Counter
    image, meta = iff_img(SHAPES / 'wingstitle')
    scaled = image.convert('RGB').resize((256, 200), Image.BOX)
    rgb = [tuple(round(v * 7 / 255) for v in scaled.getpixel((x, y))) for y in range(200) for x in range(256)]
    palette, near = quantize(Counter(rgb), 16)
    index = {c: near(c) for c in set(rgb)}
    return bytes(index[c] for c in rgb), palette


def story_lines():
    """The executable's story (0x...: "A Time of Fury", NUL-separated lines,
    justified with spaces for 48 columns): its heading and its paragraphs,
    wrapped again for STORY_COLUMNS, a blank line between paragraphs."""
    data = EXE.read_bytes()
    start = data.index(b'A Time of Fury')
    end = data.index(b'from above...', start) + len(b'from above...')
    lines = [l.decode('latin-1') for l in data[start:end].split(b'\0')]
    heading, paragraphs, words = lines[0], [], []
    for line in lines[1:]:
        if not line.strip() or line.startswith('    '):
            if words: paragraphs.append(words); words = []
        words += line.split()
    if words: paragraphs.append(words)
    out = []
    for words in paragraphs:
        line = ''
        for w in words:
            if line and len(line) + 1 + len(w) > STORY_COLUMNS:
                out.append(line); line = w
            else:
                line = f'{line} {w}' if line else w
        out += [line, '']
    return heading, out[:-1]


def newarmy_text(text, top, bottom, transparent=0):
    """text in newarmyfont (12 rows), its upper half in colour top, the
    lower in bottom, as width-even pixel rows."""
    from convert_font import glyphs
    height, first, last, font = glyphs()
    rows = [[] for _ in range(height)]
    for ch in text.encode('latin-1'):
        width, bits = font[ch if first <= ch <= last else first]
        for r in range(height):
            rows[r] += [(top if r < height // 2 else bottom) if v else transparent for v in bits[r]] + [transparent]
    width = (len(rows[0]) + 1) // 2 * 2
    return [row + [transparent] * (width - len(row)) for row in rows], width


def intro_pages():
    """The credits' and story's pieces in INTRO_BANK and the pages' layout,
    with previews of the pages as drawn (msx/screen_end.c)."""
    from extract_iff import iff_img
    from collections import Counter
    from convert_font import glyphs
    # The USI logo: creditscreen's rows 131..199, columns 0..161.
    image, meta = iff_img(SHAPES / 'creditscreen')
    cmap = image.getpalette()[:3 * meta['colors']]
    rgb = [tuple(round(v * 7 / 255) for v in cmap[3 * i:3 * i + 3]) for i in range(meta['colors'])]
    pixels = image.tobytes()
    logo = [[rgb[pixels[y * 320 + x]] for x in range(162)] for y in range(131, 200)]
    blues, _ = quantize(Counter(c for row in logo for c in row if c not in INTRO_FIXED), 16 - len(INTRO_FIXED) + 1)
    palette = INTRO_FIXED + [b for b in blues if b != (0, 0, 0)][:16 - len(INTRO_FIXED)]
    palette += [(0, 0, 0)] * (16 - len(palette))
    _, near = quantize(Counter(), 16, palette)
    logo_index = [[near(c) for c in row] for row in logo]
    pieces, bank, story = [], bytearray(), bytearray()
    def add(rows, width, x, y, into=bank):
        pieces.append(dict(offset=len(into), bank=INTRO_BANK if into is bank else STORY_BANK,
                           bytes=width // 2, height=len(rows), x=x, y=y, rows=rows, width=width))
        for row in rows: into.extend(pack(bytes(row), width))
    # The credits page: the original's roles and names, cut from its lines
    # (msx/screen_end.c draws the texts at CREDIT_TEXTS' rows).
    for ((top, bottom), *parts), rows_at in zip(CREDIT_LINES, CREDIT_ROWS):
        for (left, right), y in zip(parts, rows_at):
            width = (right - left + 1) // 2 * 2
            rows = [[near(rgb[pixels[yy * 320 + x]]) for x in range(left, left + width)] for yy in range(top, bottom)]
            add(rows, width, (256 - width) // 2 // 2 * 2, y)
    add(logo_index, 162, 46, 124, story)
    heading, lines = story_lines()
    rows, width = newarmy_text(heading, *HEADING_SHADES)
    add(rows, width, (256 - width) // 2 // 2 * 2, 8)
    # The story's lines, fixed records in STORY_BANK; pages of as many as fit
    # below the heading (page 1) or the top margin.
    offset = len(story)
    for line in lines:
        record = line.upper().encode('latin-1')
        assert len(record) <= STORY_LINE and all(chr(b) in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .:' + ''.join(EXTRA_GLYPHS) for b in record), line
        story.extend(record + bytes(STORY_LINE - len(record)))
    pages, at = [], 0
    while at < len(lines):
        top = 28 if not pages else 12
        count = min((204 - top) // 9, len(lines) - at)
        pages.append(dict(first=at, count=count, top=top))
        at += count
        while at < len(lines) and not lines[at]: at += 1
    assert len(bank) <= 8192 and len(story) <= 8192, (len(bank), len(story))
    # Previews, as the run time draws them.
    font = small_font()
    order = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789> .:' + ''.join(EXTRA_GLYPHS)
    def text(page, x, y, string, ink):
        for i, ch in enumerate(string.upper()):
            g = order.index(ch) if ch in order else order.index(' ')
            for r in range(7):
                bits = font[g * 7 + r]
                for k in range(6):
                    if bits & (0x80 >> k): page[(y + r) * 256 + x + 6 * i + k] = ink
    def blit(page, p):
        for r, row in enumerate(p['rows']):
            for k, v in enumerate(row):
                if v: page[(p['y'] + r) * 256 + p['x'] + k] = v
    def centred(string): return (256 - 6 * len(string)) // 2 // 2 * 2
    credits = bytearray(256 * 212)
    for string, y, ink in CREDIT_TEXTS:
        text(credits, centred(string), y, string, ink)
    for p in pieces[:-1]: blit(credits, p)
    previews = [bytes(credits)]
    for n, page in enumerate(pages):
        image = bytearray(256 * 212)
        if not n: blit(image, pieces[-1])
        for i in range(page['count']):
            text(image, (256 - 6 * STORY_COLUMNS) // 2, page['top'] + 9 * i, lines[page['first'] + i], INTRO_TEXT)
        previews.append(bytes(image))
    return bytes(bank) + bytes(8192 - len(bank)), bytes(story), offset, pieces, pages, palette, previews


# The credits page's texts: (text, row, ink); msx/screen_end.c draws them
# centred.
CREDIT_TEXTS = (('ADAPTED FROM THE AMIGA VERSION', 8, INTRO_TEXT),
                ('PORTED BY PFUENTES69 (& CLAUDE)', 200, INTRO_TEXT))


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
