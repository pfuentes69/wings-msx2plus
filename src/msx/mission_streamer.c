#include "terrain_renderer.h"
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
/* The column table (u16 offsets into the map); terrain_patch.c rewrites it.
 * The runs stay in ROM bank TERRAIN_MAP_BANK: 4.3 KB of RAM saved. */
u8 g_TerrainMap[TERRAIN_MAP_TABLE_BYTES];
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
static u8 s_StripSlot[TERRAIN_STRIPS];   /* 255: not in VRAM */
u8 g_TerrainSlotStrip[TERRAIN_SLOTS];    /* 255: free; read by tools/verify_p0.py */
static u8 s_SlotMark[TERRAIN_SLOTS];
static u8 s_Hand;
typedef char TerrainStripTables[(TERRAIN_STRIPS <= 255 && TERRAIN_SLOTS <= 64) ? 1 : -1];

static void ResetTiles(void)
{
    u8 i;
    for (i = 0; i < TERRAIN_STRIPS; ++i) s_StripSlot[i] = 255;
    for (i = 0; i < TERRAIN_SLOTS; ++i) g_TerrainSlotStrip[i] = 255, s_SlotMark[i] = 0;
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
        add     a, #TERRAIN_TILE_BANK
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

static u8 LoadStrip(u8 strip)
{
    u8 slot;
    for (;;)
    {
        slot = s_Hand;
        if (++s_Hand == TERRAIN_SLOTS) s_Hand = 0;
        if (!s_SlotMark[slot]) break;
        s_SlotMark[slot] = 0;
    }
    if (g_TerrainSlotStrip[slot] != 255) s_StripSlot[g_TerrainSlotStrip[slot]] = 255;
    g_TerrainSlotStrip[slot] = strip; s_StripSlot[strip] = slot;
    /* A copy still running may read the slot. */
    VDP_CommandWait();
    s_UploadStrip = strip;
    s_UploadAddress = ((u16)(180 + ((slot >> 5) << 8)) << 7) + ((slot & 31) << 2);
    UploadStrip();
    return slot;
}

u16 Terrain_TileY(u16 tile)
{
    u8 strip = (u8)(tile >> 3), slot = s_StripSlot[strip];
    if (slot == 255) slot = LoadStrip(strip);
    s_SlotMark[slot] = 1;
    g_TileSourceX = (slot & 31) << 3;
    return 512 + 180 + ((u16)(slot >> 5) << 8) + ((tile & 7) << 3);
}

/* The column table into RAM; the strips load as columns need them. */
void Terrain_Load(void)
{
    u16 i;
    u8 count;
    s_Decoded[TERRAIN_MAP_ROWS] = TERRAIN_SENTINEL;
    ResetTiles();
    for (i = 0; i < TERRAIN_MAP_TABLE_BYTES; i += count)
    {
        count = TERRAIN_MAP_TABLE_BYTES - i > 64 ? 64 : TERRAIN_MAP_TABLE_BYTES - i;
        Scenery_Read(TERRAIN_MAP_BANK + (i >> 13), i & 8191, g_TerrainMap + i, count);
    }
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
#define TERRAIN_SEA_COLUMN 625u
#define TERRAIN_FAR_SEA_COLUMN 78u

/* The map column's run offset for a world x in the current view. */
static u16 ColumnOffset(u16 world)
{
    u16 column = world >> 3;
    if (g_TerrainFar)
        column = (column < TERRAIN_FAR_COLUMNS ? column : TERRAIN_FAR_SEA_COLUMN) + TERRAIN_FAR_COLUMN;
    else if (column >= TERRAIN_FAR_COLUMN) column = TERRAIN_SEA_COLUMN;
    column *= 2;
    return g_TerrainMap[column] | ((u16)g_TerrainMap[column + 1] << 8);
}

/* Decode a column's runs from the map bank, mapped into window 3 for the
 * moment (this code is resident; the caller's banked segment comes back
 * before we return; the interrupt handlers never use window 3). */
static void Decode(u16 offset, u16* out)
{
    u8 segment = g_Bank3Segment;
    /* No column record crosses a bank (tools/convert_mission.py). */
    *(volatile u8*)0x7800 = g_Bank3Segment = TERRAIN_MAP_BANK + (offset >> 13);
    Column_Decode((const u8*)0xA000 + (offset & 8191), out);
    *(volatile u8*)0x7800 = g_Bank3Segment = segment;
}

/* Spare time before a VBlank: load one strip that the next columns ahead
 * of the camera (in the direction of flight) will need, so new terrain
 * mostly finds its strips in VRAM. 1 when a strip was loaded. */
static u16 s_Ahead[TERRAIN_MAP_ROWS + 1];
static u16 s_PrefetchCamera = 65535u;
u8 Terrain_Prefetch(u16 camera, i8 direction)
{
    u8 column, row, strip;
    u16 x, tile;
    if (camera == s_PrefetchCamera) return 0;   /* nothing left ahead of it */
    for (column = 1; column <= 4; ++column)
    {
        x = direction > 0 ? camera + 255 + ((u16)column << 3) : camera + 8 - ((u16)column << 3);
        Decode(ColumnOffset(x), s_Ahead);
        for (row = 0; row < TERRAIN_MAP_ROWS; ++row)
        {
            tile = s_Ahead[row];
            if (tile < TERRAIN_UNIFORM_COUNT) continue;
            strip = (u8)(tile >> 3);
            if (s_StripSlot[strip] != 255) { s_SlotMark[s_StripSlot[strip]] = 1; continue; }
            s_SlotMark[LoadStrip(strip)] = 1;
            return 1;
        }
    }
    s_PrefetchCamera = camera;
    return 0;
}

void Terrain_DecodeColumn(u16 world, u16* out)
{
    Decode(ColumnOffset(world), out);
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
    u8 row, count, height, color, i;
    if (g_TerrainColumns[page][slot] == offset) return;
    g_TerrainColumns[page][slot] = offset;
    // All runs/offsets are bounded and round-trip checked during generation.
    Decode(offset, s_Decoded);
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

