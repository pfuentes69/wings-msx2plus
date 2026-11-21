#include "terrain_renderer.h"
#include "terrain_patch.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "system.h"
#include "scenery_load.h"
#include "mission_tiles.h"
#include "column_ops.h"

u8 g_TerrainFar;
/* Close-view pan in whole tile rows x 8 (0..48) for the page being drawn:
 * the scenery is drawn this many rows lower (docs/altitude-view.md). */
u8 g_PanRows;
/* The column table (u16 offsets into the runs) stays in ROM, at the start
 * of the map's first bank. The columns shown with other runs (wrecked huts,
 * the deck's spare planes, sinking ships) are in this list, sorted by
 * column; terrain_patch.c keeps it. Until 2026-11-21 the whole table was
 * in RAM (2.2 KB on map a, 8 KB on map o). */
u16 g_ChangeColumn[TERRAIN_CHANGES], g_ChangeOffset[TERRAIN_CHANGES];
u8 g_Changes;
extern u8 g_Bank3Segment;   /* crt0's shadow of the window-3 register */
/* The tile ids each page shows per ring column, and the map column drawn
 * there (65535: invalid). Shared with the smoke eraser (smoke_draw.c). */
u16 g_TerrainCached[2][32][TERRAIN_MAP_ROWS];
u16 g_TerrainColumns[2][32];
// One extra entry holds a sentinel (65534) that never matches the cache,
// which only holds tile IDs or 65535; Column_Equal stops there.
#define TERRAIN_SENTINEL 65534u
typedef char TerrainSentinelFree[(TERRAIN_TILE_COUNT < TERRAIN_SENTINEL) ? 1 : -1];

static u16 s_Decoded[TERRAIN_MAP_ROWS + 1];

/* The tile cache: strips of 8 tiles (ids 8k..8k+7, 8 x 64 px) load from
 * ROM into TERRAIN_SLOTS VRAM slots as columns need them: slot s is at
 * x (s % 32) * 8, y 692 + (s / 32) * 256 (rows 180.. of pages 2, 3). A clock
 * picks the slot to reuse: an access marks it, a load passes marked slots
 * once (clearing the mark) and takes the first unmarked one. Whatever the
 * pages still show of an evicted strip stays there; copying a tile again
 * loads its strip again. */
u8 g_TileSourceX;
#ifdef TERRAIN_STRIPS_MAX
u8 g_StripSlot[TERRAIN_STRIPS_MAX];   /* 255: not in VRAM */
#else
u8 g_StripSlot[TERRAIN_STRIPS];
#endif
u8 g_TerrainSlotStrip[TERRAIN_SLOTS];    /* 255: free; read by tools/verify_p0.py */
u8 g_SlotMark[TERRAIN_SLOTS];
static u8 s_Hand;
#ifndef WINGS_MAP_RECORD
typedef char TerrainStripTables[(TERRAIN_STRIPS <= 255 && TERRAIN_SLOTS <= 64) ? 1 : -1];
#endif

static void ResetTiles(void)
{
    u8 i;
    for (i = 0; i < TERRAIN_STRIPS; ++i) g_StripSlot[i] = 255;
    for (i = 0; i < TERRAIN_SLOTS; ++i) g_TerrainSlotStrip[i] = 255, g_SlotMark[i] = 0;
    s_Hand = 0;
}

/* Upload strip s_UploadStrip's 256 bytes (8 tiles x 8 rows x 4 bytes, its
 * 64 rows in order) from its ROM bank, mapped into window 3, straight to
 * VRAM at s_UploadAddress (in the upper 64 KiB). All 64 rows lie in one
 * 16 KiB block (rows 180..243 of page 2 or 3), so R14 is set once. ~6,400
 * T-states; the C version through RAM and MSXgl's writes cost ~25,000. */
static u16 s_UploadAddress;
static u8 s_UploadStrip;
static void UploadStrip(void) __naked
{
    __asm
        ld      a, (_g_Bank3Segment)
        push    af
        ld      a, (_s_UploadStrip)
        ld      c, a
        rlca                            ; bank = TERRAIN_TILE_BANK + strip / 32
        rlca
        rlca
        and     a, #7
#ifdef WINGS_MAP_RECORD
        ld      hl, #_g_Map             ; tile_bank (map_record.h)
        add     a, (hl)
#else
        add     a, #TERRAIN_TILE_BANK
#endif
        ld      (_g_Bank3Segment), a
        ld      (0x7800), a
        ld      a, c                    ; source = A000h + (strip % 32) * 256
        and     a, #31
        add     a, #0xA0
        ld      h, a
        ld      l, #0
        ld      de, (_s_UploadAddress)
        ld      a, d                    ; R14: address bits 14..16 (bit 16 set)
        rlca
        rlca
        and     a, #3
        or      a, #4
        di
        out     (0x99), a
        ld      a, #0x8e
        out     (0x99), a
        ei
        ld      b, #64
    upload_row$:
        ld      a, e
        di
        out     (0x99), a
        ld      a, d
        and     a, #0x3f
        or      a, #0x40
        ei
        out     (0x99), a
        ld      c, #0x98
        outi
        outi
        outi
        outi
        inc     b                       ; outi counted B down 4 times
        inc     b
        inc     b
        inc     b
        ex      de, hl                  ; address += 128
        ld      a, #128
        add     a, l
        ld      l, a
        jr      nc, upload_next$
        inc     h
    upload_next$:
        ex      de, hl
        djnz    upload_row$
        pop     af
        ld      (_g_Bank3Segment), a
        ld      (0x7800), a
        ret
    __endasm;
}

u8 Terrain_LoadStrip(u8 strip)
{
    u8 slot;
    for (;;)
    {
        slot = s_Hand;
        if (++s_Hand == TERRAIN_SLOTS) s_Hand = 0;
        if (!g_SlotMark[slot]) break;
        g_SlotMark[slot] = 0;
    }
    if (g_TerrainSlotStrip[slot] != 255) g_StripSlot[g_TerrainSlotStrip[slot]] = 255;
    g_TerrainSlotStrip[slot] = strip; g_StripSlot[strip] = slot;
    /* A copy still running may read the slot. */
    VDP_CommandWait();
    s_UploadStrip = strip;
    s_UploadAddress = ((u16)(180 + ((slot >> 5) << 8)) << 7) + ((slot & 31) << 2);
    UploadStrip();
    return slot;
}

/* In Z80: every terrain repaint and copy calls it (the C was ~1,100
 * T-states). The C it implements:
 *     u8 strip = (u8)(tile >> 3), slot = g_StripSlot[strip];
 *     if (slot == 255) slot = LoadStrip(strip);
 *     g_SlotMark[slot] = 1;
 *     g_TileSourceX = (slot & 31) << 3;
 *     return 512 + 180 + ((u16)(slot >> 5) << 8) + ((tile & 7) << 3);
 * HL = tile (below 2048: strips fit a byte); returns DE. */
u16 Terrain_TileY(u16 tile) __naked
{
    (void)tile;
    __asm
        ld      a, l
        and     a, #7
        add     a, a
        add     a, a
        add     a, a
        add     a, #0xb4            ; 692 = 0x2b4: the low byte, no carry (<= 0xec)
        push    af
        srl     h
        rr      l
        srl     h
        rr      l
        srl     h
        rr      l                   ; L = strip
        ld      e, l
        ld      d, #0
        ld      hl, #_g_StripSlot
        add     hl, de
        ld      a, (hl)
        inc     a
        jr      nz, cached$
        ld      a, e
        call    _Terrain_LoadStrip          ; A = strip -> A = slot
        inc     a
cached$:
        dec     a                   ; A = slot
        ld      e, a
        ld      d, #0
        ld      hl, #_g_SlotMark
        add     hl, de
        ld      (hl), #1
        ld      d, a
        and     a, #31
        add     a, a
        add     a, a
        add     a, a
        ld      (_g_TileSourceX), a
        ld      a, d
        rlca
        rlca
        rlca
        and     a, #1               ; slot >> 5 (slots < 64)
        add     a, #0x02
        ld      d, a
        pop     af
        ld      e, a
        ret
    __endasm;
}

/* Every column as the map has it; the strips load as columns need them. */
void Terrain_Load(void)
{
    s_Decoded[TERRAIN_MAP_ROWS] = TERRAIN_SENTINEL;
    g_SinkActive = 0;   /* RAM is not cleared at boot */
    g_Changes = 0;
    g_PrefetchCamera = 65535u;
    ResetTiles();
}

void Terrain_LoadEnd(void) {}

void Terrain_InitPage(u8 page)
{
    u8 column, row;
    for (column = 0; column < 32; ++column)
    {
        g_TerrainColumns[page][column] = 65535u;
        for (row = 0; row < TERRAIN_MAP_ROWS; ++row)
            g_TerrainCached[page][column][row] = 0; // VRAM was cleared to the all-sky tile.
    }
}

/* Map columns of open sea (x 5000, between the islands and the carrier),
 * drawn for every column beyond the map's ends: the ocean goes on, as in the
 * original. tests/test_mission.py checks that both are plain sea. */
#ifndef TERRAIN_SEA_COLUMN   /* the ROM: the record's (tools/build_maps.py) */
#define TERRAIN_SEA_COLUMN 625u
#define TERRAIN_FAR_SEA_COLUMN 78u
#endif

/* Window 3 (A000h-BFFFh) = segment, sdcccall(1): A. LD (nn),A, the form
 * loaders patch (docs/diag-rom.md); a pointer write compiled to LD (HL),A. */
static void SetBank3(u8 segment) __naked
{
    (void)segment;
    __asm
        ld      (0x7800), a
        ret
    __endasm;
}

/* The u16 at byte offset of the map in ROM (even: it never crosses a
 * bank), window 3 mapped for the moment; the caller's segment comes back
 * (the shadow first, as in Decode). */
u16 Terrain_MapWord(u16 offset)
{
    u8 segment = g_Bank3Segment;
    u16 word;
    g_Bank3Segment = TERRAIN_MAP_BANK + (offset >> 13);
    SetBank3(g_Bank3Segment);
    word = *(const u16*)(0xA000 + (offset & 8191));
    g_Bank3Segment = segment;
    SetBank3(segment);
    return word;
}

/* The list position of column, or where it would go: the first entry not
 * below it. */
u8 Terrain_ChangeAt(u16 column)
{
    u8 low = 0, high = g_Changes, middle;
    while (low < high)
    {
        middle = (low + high) >> 1;
        if (g_ChangeColumn[middle] < column) low = middle + 1;
        else high = middle;
    }
    return low;
}

/* The column table's entry for column (HL; returns DE): the table starts
 * the map's first bank and is under 8 KiB. Z80: every drawn column needs
 * it (Terrain_MapWord's C cost ~250 T-states more, and P0's carrier frames
 * are a knife-edge on NTSC). */
static u16 TableWord(u16 column) __naked
{
    (void)column;
    __asm
        ld      a, (_g_Bank3Segment)
        ld      c, a
#ifdef WINGS_MAP_RECORD
        ld      a, (_g_Map + 1)         ; map_bank (map_record.h)
#else
        ld      a, #TERRAIN_MAP_BANK
#endif
        ld      (_g_Bank3Segment), a    ; the shadow first
        ld      (0x7800), a
        add     hl, hl
        ld      a, h
        or      a, #0xA0
        ld      h, a
        ld      e, (hl)
        inc     hl
        ld      d, (hl)
        ld      a, c
        ld      (_g_Bank3Segment), a
        ld      (0x7800), a
        ret
    __endasm;
}

/* The map column's run offset for a world x in the current view. */
static u16 ColumnOffset(u16 world)
{
    u16 column = world >> 3;
    u8 at;
    if (g_TerrainFar)
        column = (column < TERRAIN_FAR_COLUMNS ? column : TERRAIN_FAR_SEA_COLUMN) + TERRAIN_FAR_COLUMN;
    else if (column >= TERRAIN_FAR_COLUMN) column = TERRAIN_SEA_COLUMN;
    /* The list is sorted: most columns are outside its first..last. */
    if (g_Changes && column >= g_ChangeColumn[0] && column <= g_ChangeColumn[g_Changes - 1]
        && (at = Terrain_ChangeAt(column)) < g_Changes && g_ChangeColumn[at] == column)
        return g_ChangeOffset[at];
    return TableWord(column);
}

/* Decode a column's runs from the map bank, mapped into window 3 for the
 * moment (this code is resident; the caller's banked segment comes back
 * before we return; the music's interrupt maps window 3 for itself and
 * puts back the segment the shadow names: the shadow is written first). */
static void Decode(u16 offset, u16* out)
{
    u8 segment = g_Bank3Segment;
    /* No column record crosses a bank (tools/convert_mission.py). */
    g_Bank3Segment = TERRAIN_MAP_BANK + (offset >> 13);   /* the shadow first (banking.c) */
    SetBank3(g_Bank3Segment);
    Column_Decode((const u8*)0xA000 + (offset & 8191), out);
    g_Bank3Segment = segment;
    SetBank3(segment);
}

/* Sinking ships (docs/ship-sinking.md): in the close view a hull column's
 * tiles come down g_SinkHull[i].rows tile rows, the rows above repeating
 * its top tile (sky). The rows pushed down pass under the wave strip. */
SinkHull g_SinkHull[SINK_HULLS];
u8 g_SinkActive;
/* Per page and ring slot: the hull rows its column was drawn lowered by
 * (0 for any other column). Terrain_DrawColumn redraws a column whose
 * rows changed, though its runs (the offset) are the same. */
static u8 s_SinkDrawn[2][32];
static const SinkHull* Hull(u16 world)
{
    const SinkHull* hull = g_SinkHull;
    u8 i;
    for (i = 0; i < SINK_HULLS; ++i, ++hull)
        if (hull->rows && world >= hull->left && world <= hull->right) return hull;
    return 0;
}
static void Sink(const SinkHull* hull, u16* out)
{
    u16* to;
    u16 top;
    u8 n, rows = hull->rows < TERRAIN_MAP_ROWS ? hull->rows : TERRAIN_MAP_ROWS;
    top = out[0];
    to = out + TERRAIN_MAP_ROWS;
    for (n = TERRAIN_MAP_ROWS - rows; n; --n) { --to; *to = to[-(i16)rows]; }
    for (n = rows; n; --n) *--to = top;
}

/* A hull column one stage behind: on the page it is the column drawn a
 * tile row higher, and the overlays are already erased (Render). Move it
 * down 8 px (bottom up, above the dashboard), paint the top row with the
 * top tile's colour and shift the cache: 2 VDP commands instead of a
 * dozen tile copies. 0 when the column does not allow it. */
static u8 Lower(u16 world, u8 page, u8 slot)
{
    u16* cached = g_TerrainCached[page][slot];
    u16 base = (u16)page * 256, y;
    u8 first, color = TERRAIN_TILE_COLOR(cached[0]);
    if (color == 255) return 0;
    first = Column_Lower(cached);   /* Z80: also shifts the cache */
    if (first == 255) return 0;
    /* Only the rows from the hull's top move: the sky above stays. */
    y = 24 + g_PanRows + ((u16)first << 3);
    if (y + 8 < 172)
    {
        g_VDP_Command.SX = g_VDP_Command.DX = world & 255;
        g_VDP_Command.SY = base + 163; g_VDP_Command.DY = base + 171;
        g_VDP_Command.NX = 8; g_VDP_Command.NY = 164 - y;
        g_VDP_Command.ARG = 0x08;   /* bottom up: the copy overlaps */
        g_VDP_Command.CMD = VDP_CMD_HMMM;
        VDP_CommandSetupR32();
    }
    if (y < 172) VDP_CommandHMMV(world & 255, base + y, 8, y + 8 > 172 ? 172 - y : 8, color * 17);
    return 1;
}

void Terrain_DecodeColumn(u16 world, u16* out)
{
    const SinkHull* hull;
    Decode(ColumnOffset(world), out);
    if (g_SinkActive && !g_TerrainFar && (hull = Hull(world))) Sink(hull, out);
}

void Terrain_DrawColumn(u16 world, u8 page)
{
    u8 slot = (world & 255) >> 3;
    u16 offset = ColumnOffset(world);
    u16* cached;
    u16* decoded;
    /* The cache holds map rows; a close-view pan draws them g_PanRows
     * lower, and rows pushed below the playfield are cached, not drawn. */
    u16 tile, source_y, dest_y = (u16)page * 256 + 24 + g_PanRows;
    u8 row, count, height, color, i, rows;
    const SinkHull* hull = g_SinkActive && !g_TerrainFar ? Hull(world) : 0;
    rows = hull ? hull->rows : 0;
    if (g_TerrainColumns[page][slot] == offset)
    {
        if (s_SinkDrawn[page][slot] == rows) return;
        /* A sinking stage (docs/ship-sinking.md). */
        if (rows && s_SinkDrawn[page][slot] + 1 == rows && Lower(world, page, slot))
        {
            s_SinkDrawn[page][slot] = rows;
            return;
        }
    }
    g_TerrainColumns[page][slot] = offset;
    s_SinkDrawn[page][slot] = rows;
    // All runs/offsets are bounded and round-trip checked during generation.
    Decode(offset, s_Decoded);
    if (hull) Sink(hull, s_Decoded);
    cached = g_TerrainCached[page][slot];
    decoded = s_Decoded;
#ifndef WINGS_TERRAIN_C
    /* Hand-written Z80 (column_ops.c): SDCC's version of the loop below cost
     * ~900 T-states per tile run before the VDP setup. */
    g_ColumnX = world & 255; g_ColumnY = dest_y;
    Column_Runs(cached, decoded);
    (void)row; (void)count; (void)height; (void)color; (void)i; (void)tile; (void)source_y;
#else
    row = 0;
    for (;;)
    {
        count = Column_Equal(cached, decoded); // unchanged rows; stops at the sentinel
        row += count;
        if (row >= TERRAIN_MAP_ROWS) break;
        cached += count;
        decoded += count;
        dest_y += count * 8;
        tile = *decoded;
        count = 1;
        color = TERRAIN_TILE_COLOR(tile);
        if (color != 255)
        {
            while (row + count < TERRAIN_MAP_ROWS && decoded[count] == tile) ++count;
        }
        else
        {
            // Consecutive IDs are stacked vertically within a strip.
            while (row + count < TERRAIN_MAP_ROWS && count < 8 - (tile & 7) &&
                   decoded[count] == tile + count) ++count;
        }
        height = count * 8;
        if (dest_y % 256 + height > 172) height = 172 - dest_y % 256;
        if (dest_y % 256 >= 172) {}
        else if (color != 255)
            VDP_CommandHMMV(world & 255, dest_y, 8, height, color * 17);
        else
        {
            source_y = Terrain_TileY(tile);
            VDP_CommandHMMM(g_TileSourceX, source_y, world & 255, dest_y, 8, height);
        }
        // The next command waits before submission; update the cache in parallel.
        for (i = 0; i < count; ++i) *cached++ = *decoded++;
        row += count;
        dest_y += count * 8;
    }
#endif
}

/* Column_Runs writes these directly. */
typedef char ColumnRunsCommands[(VDP_CMD_HMMM == 0xD0 && VDP_CMD_HMMV == 0xC0) ? 1 : -1];
typedef char ColumnRunsLayout[(sizeof(VDP_Command) == 15 && sizeof(g_VDP_Command.SX) == 2) ? 1 : -1];

