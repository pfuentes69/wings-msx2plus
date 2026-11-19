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
/* RepaintColumn's state (smoke_repaint.h), as statics. */
static u16 s_Column;
static const u16* s_Cached;
static u8 s_RepaintRow, s_Y8, s_Next8, s_Bottom8, s_Origin8, s_Page8, s_DecodedOnce;
#include "smoke_repaint.h"
static void RepaintTiles(u8 page, i16 left, i16 right, i16 top, i16 bottom)
{
    u8 first;
    s_Origin8 = TERRAIN_TOP + g_PanRows;
    s_Bottom8 = (u8)bottom;
    s_Page8 = page;
    first = (u8)((top - s_Origin8) >> 3);
    g_VDP_Command.NX = 8; g_VDP_Command.ARG = 0;
    for (s_Column = (u16)(left & ~7); (i16)s_Column < right; s_Column += 8)
    {
        s_Cached = &g_TerrainCached[page][(u8)s_Column >> 3][first];
        s_RepaintRow = first; s_Y8 = (u8)top; s_DecodedOnce = 0;
        g_VDP_Command.DX = (u8)s_Column;
        RepaintColumn();
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
/* AllSky's input (smoke_sky.h): the box's first cache entry and ring slot,
 * its columns and tile rows. */
static const u16* s_SkyPtr;
static u8 s_SkySlot, s_SkyCols, s_SkyRows;
#include "smoke_sky.h"

u8 Smoke_Restore(u8 page, u8 rebuilt, u16 camera) WINGS_BANKED
{
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
        s_SkySlot = (u8)left >> 3;
        s_SkyPtr = &g_TerrainCached[page][s_SkySlot][first];
        s_SkyCols = (u8)((right - (left & ~7) + 7) >> 3);
        s_SkyRows = last - first + 1;
        if (AllSky()) { SkyFill(page, left, right, s_BoxTop, s_BoxBottom); continue; }
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
