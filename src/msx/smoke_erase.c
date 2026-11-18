#include "smoke_draw.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "vdp_ring.h"
#include "terrain_renderer.h"
#include "../core/flight.h"
#include "../generated/hellcat_frames.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_PATCH)

/* The smoke path's erase (Smoke_Restore), split from smoke_draw.c for room
 * (2026-11-18): each shape the page drew is repainted from the page's tile
 * cache, or filled with sky. Its box table is a copy in this segment
 * (smoke_erase_box.c, tools/convert_hellcat.py). */

#ifdef WINGS_P1_FLIGHT
#define TERRAIN_TOP 24      /* first terrain row; above it the sky is plain */
#define ELEVATOR_LEFT ((int)CARRIER_X - 28)
#define ELEVATOR_RIGHT ((int)CARRIER_X + 36)

/* 1 when the page's tiles in this column, tile rows first..last, are all
 * plain sky (solid colour 0): the puff can be erased with a fill. */
static u8 SkyRows(u8 page, u16 world, u8 first, u8 last)
{
    u8 slot = (world & 255) >> 3;
    const u16* cached = &g_TerrainCached[page][slot][first];
    for (;;)
    {
        if (*cached >= TERRAIN_TILE_COUNT || TERRAIN_TILE_COLOR(*cached)) return 0;
        if (first++ == last) return 1;
        ++cached;
    }
}

/* Repaint VRAM rows top..bottom - 1 (top at or below map row 0) over the
 * 8-px columns that left..right touches, from the page's tile cache: one
 * VDP command per tile, a copy from the tile atlas or a fill for a solid
 * tile, cut to the rows asked for. Much cheaper than redrawing whole
 * columns for a small shape.
 *
 * The cache always matches VRAM (a new page starts as all sky), except for
 * rows under an overlay (the signalmen, the elevator), which hold 65535 so
 * the column is repainted when the ring reuses it. Those rows are repainted
 * from the map instead; the overlay is drawn again later in the frame. A
 * column flagged invalid for that reason still has valid rows: skipping it
 * left 8-px blocks of smoke in the sky over the carrier. */
static u16 s_Decoded[TERRAIN_MAP_ROWS + 1];
/* The loop's state as statics (SDCC reaches them directly, where locals go
 * through the IX frame); each tile fills g_VDP_Command and issues it, the
 * column's DX, NX and ARG set once. */
static u16 s_Column, s_PageBase;
static i16 s_Y, s_Next, s_Bottom, s_Origin;
static u8 s_RepaintRow, s_First;
static const u16* s_Cached;
static void RepaintTiles(u8 page, i16 left, i16 right, i16 top, i16 bottom)
{
    u16 tile;
    u8 color, decoded;
    s_Origin = TERRAIN_TOP + g_PanRows;
    s_Bottom = bottom;
    s_PageBase = (u16)page << 8;
    s_First = (u8)((top - s_Origin) >> 3);
    g_VDP_Command.NX = 8; g_VDP_Command.ARG = 0;
    for (s_Column = (u16)(left & ~7); (i16)s_Column < right; s_Column += 8)
    {
        s_Cached = &g_TerrainCached[page][(u8)s_Column >> 3][s_First];
        s_RepaintRow = s_First; s_Y = top; decoded = 0;
        g_VDP_Command.DX = (u8)s_Column;
        do
        {
            s_Next = s_Origin + ((i16)(s_RepaintRow + 1) << 3);
            if (s_Next > s_Bottom) s_Next = s_Bottom;
            tile = *s_Cached++;
            if (tile >= TERRAIN_TILE_COUNT)
            {
                if (!decoded) { Terrain_DecodeColumn(s_Column, s_Decoded); decoded = 1; }
                tile = s_Decoded[s_RepaintRow];
            }
            if (tile < TERRAIN_TILE_COUNT)
            {
                g_VDP_Command.DY = s_PageBase + s_Y;
                g_VDP_Command.NY = s_Next - s_Y;
                color = TERRAIN_TILE_COLOR(tile);
                if (color != 255)
                {
                    g_VDP_Command.CLR = color * 17;
                    g_VDP_Command.CMD = VDP_CMD_HMMV;
                }
                else
                {
                    g_VDP_Command.SY = Terrain_TileY(tile) + (u8)(s_Y - s_Origin) - ((u16)s_RepaintRow << 3);
                    g_VDP_Command.SX = g_TileSourceX;
                    g_VDP_Command.CMD = VDP_CMD_HMMM;
                }
                VDP_CommandSetupR32();
            }
            s_Y = s_Next; ++s_RepaintRow;
        } while (s_Y < s_Bottom);
    }
}

static void SkyFill(u8 page, i16 left, i16 right, i16 top, i16 bottom)
{
    left &= ~1; right = (right + 1) & ~1;
    VDP_RING_SET(0, 0, (u16)page * 256 + top, bottom - top, VDP_CMD_HMMV);
    g_VDP_Command.CLR = 0;
    Vdp_RingCopy((u8)left, right - left);
}

/* The page's clip in statics while it is restored: SDCC is slow through a
 * struct pointer. */
static i16 s_Left, s_Right, s_Top, s_Limit;
static i8 s_Heave;
static void UseClip(const SmokeClip* clip)
{
    s_Left = clip->left; s_Right = clip->right; s_Top = clip->top;
    s_Limit = clip->limit; s_Heave = clip->heave;
}

/* A drawn shape's box on the page, clipped as it was drawn: Box(frame)
 * for the shape at (s_BX, s_BY), in Z80, from this segment's table. */
static i16 s_BoxLeft, s_BoxRight, s_BoxTop, s_BoxBottom, s_BX, s_BY;
#define SMOKE_BOX_TABLE _g_SmokeEraseBox
#include "smoke_box.h"

u8 Smoke_Restore(u8 page, u8 rebuilt, u16 camera) WINGS_BANKED
{
    u16 column;
    u8 i, elevator = 0, first, last, n = g_SmokeDrawnCount[page];
    const SmokeDrawn* d = g_SmokeDrawn[page];
    i16 left, right, top = TERRAIN_TOP + g_PanRows;   /* VRAM row of map row 0 */
    (void)camera;
    g_SmokeDrawnCount[page] = 0;
    if (rebuilt) return 0;
    UseClip(&g_SmokeClip[page]);
    for (i = 0; i < n; ++i, ++d)
    {
        /* The whole box, even if the camera has since moved: the page's
         * ring still holds the pixels there. */
        s_BX = (i16)d->x; s_BY = d->row;
        Box(d->frame);
        left = s_BoxLeft; right = s_BoxRight;
        if (s_BoxBottom <= top) { SkyFill(page, left, right, s_BoxTop, s_BoxBottom); continue; }
        first = (u8)(((s_BoxTop < top ? top : s_BoxTop) - top) >> 3);
        last = (u8)((s_BoxBottom - 1 - top) >> 3);
        /* Over plain sky (the usual case) one fill erases the puff. */
        for (column = (u16)(left & ~7); (i16)column < right; column += 8)
            if (!SkyRows(page, column, first, last)) break;
        if ((i16)column >= right) { SkyFill(page, left, right, s_BoxTop, s_BoxBottom); continue; }
        if (s_BoxTop < top) SkyFill(page, left, right, s_BoxTop, top);
        /* The elevator (map rows 13.., Elevator_Draw) is redrawn only when
         * a repaint reached its rows, not for smoke in the sky above it. */
        if (!g_TerrainFar && right > ELEVATOR_LEFT && left < ELEVATOR_RIGHT && s_BoxBottom > top + 13 * 8)
            elevator = 1;
        /* Otherwise repaint the tiles under it from the page's tile cache. */
        RepaintTiles(page, left, right, s_BoxTop < top ? top : s_BoxTop, s_BoxBottom);
    }
    return elevator;
}

#endif
