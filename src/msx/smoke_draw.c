#include "smoke_draw.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "terrain_renderer.h"
#include "../core/smoke.h"
#include "../core/island.h"
#include "../generated/hellcat_frames.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_EFFECTS)

#ifdef WINGS_P1_FLIGHT
SmokeDrawn g_SmokeDrawn[2][SMOKE_DRAWN_MAX];
u8 g_SmokeDrawnCount[2];
/* Screen rectangles to erase, per page. */
typedef struct Rect { i16 left, right, top, bottom; } Rect;
static Rect s_Old[2][SMOKE_DRAWN_MAX];
static u8 s_OldCount[2];

#define TERRAIN_TOP 24      /* first terrain row; above it the sky is plain */
#define WAVE_TOP 159        /* smoke stays above the wave strip */
#define ELEVATOR_LEFT 7004
#define ELEVATOR_RIGHT 7068

/* 1 when the page's tiles in this column, tile rows first..last, are all
 * plain sky (solid colour 0): the puff can be erased with a fill. */
static u8 SkyRows(u8 page, u16 world, u8 first, u8 last)
{
    u8 slot = (world & 255) >> 3;
    const u16* cached = &g_TerrainCached[page][slot][first];
    if (g_TerrainColumns[page][slot] == 65535u) return 0;
    for (;;)
    {
        if (*cached >= TERRAIN_TILE_COUNT || g_MissionTileColors[*cached]) return 0;
        if (first++ == last) return 1;
        ++cached;
    }
}

/* Repaint VRAM rows top..bottom - 1 (top at or below map row 0) over the
 * 8-px columns that left..right touches, from the page's tile cache: one
 * VDP command per tile, a copy from the tile atlas or a fill for a solid
 * tile, cut to the rows asked for. Much cheaper than redrawing whole
 * columns for a small shape. */
static void RepaintTiles(u8 page, i16 left, i16 right, i16 top, i16 bottom)
{
    const u16* cached;
    u16 column, tile, base = (u16)page * 256;
    i16 y, next, origin = TERRAIN_TOP + g_PanRows;
    u8 slot, row, first = (u8)((top - origin) >> 3), color;
    for (column = (u16)(left & ~7); (i16)column < right; column += 8)
    {
        slot = (column & 255) >> 3;
        if (g_TerrainColumns[page][slot] == 65535u) continue;
        cached = &g_TerrainCached[page][slot][first];
        row = first; y = top;
        do
        {
            next = origin + (i16)(row + 1) * 8;
            if (next > bottom) next = bottom;
            tile = *cached++;
            if (tile < TERRAIN_TILE_COUNT)
            {
                color = g_MissionTileColors[tile];
                if (color != 255) VDP_CommandHMMV(column & 255, base + y, 8, next - y, color * 17);
                else VDP_CommandHMMM(g_MissionTileX[tile], g_MissionTileY[tile] + (u8)(y - origin) - row * 8,
                                     column & 255, base + y, 8, next - y);
            }
            y = next; ++row;
        } while (y < bottom);
    }
}

static void SkyFill(u8 page, i16 left, i16 right, i16 top, i16 bottom)
{
    u8 ring, width, part;
    left &= ~1; right = (right + 1) & ~1;
    ring = left & 255; width = right - left;
    while (width)
    {
        part = width;
        if ((u16)ring + part > 256) part = 256 - ring;
        VDP_CommandHMMV(ring, (u16)page * 256 + top, part, bottom - top, 0);
        ring += part; width -= part;
    }
}

void Smoke_ClearPages(void) WINGS_BANKED
{
    s_OldCount[0] = s_OldCount[1] = g_SmokeDrawnCount[0] = g_SmokeDrawnCount[1] = 0;
}

u8 Smoke_Restore(u8 page, u8 rebuilt, u16 camera) WINGS_BANKED
{
    u16 column;
    u8 i, elevator = 0, first, last, n = s_OldCount[page];
    Rect* r = s_Old[page];
    i16 left, right, top = TERRAIN_TOP + g_PanRows;   /* VRAM row of map row 0 */
    (void)camera;
    s_OldCount[page] = 0;
    if (rebuilt) return 0;
    for (i = 0; i < n; ++i, ++r)
    {
        /* The whole rectangle, even if the camera has since moved: the
         * page's ring still holds the pixels there. */
        left = r->left; right = r->right;
        if (r->bottom <= top) { SkyFill(page, left, right, r->top, r->bottom); continue; }
        first = (u8)(((r->top < top ? top : r->top) - top) >> 3);
        last = (u8)((r->bottom - 1 - top) >> 3);
        /* Over plain sky (the usual case) one fill erases the puff. */
        for (column = (u16)(left & ~7); (i16)column < right; column += 8)
            if (!SkyRows(page, column, first, last)) break;
        if ((i16)column >= right) { SkyFill(page, left, right, r->top, r->bottom); continue; }
        if (r->top < top) SkyFill(page, left, right, r->top, top);
        if (!g_TerrainFar && right > ELEVATOR_LEFT && left < ELEVATOR_RIGHT) elevator = 1;
        /* Otherwise repaint the tiles under it from the page's tile cache. */
        RepaintTiles(page, left, right, r->top < top ? top : r->top, r->bottom);
    }
    return elevator;
}

/* Drawing state as statics: SDCC addresses them directly, where locals go
 * through the IX frame. */
static i16 s_X, s_Row, s_Left, s_Right, s_Top, s_Limit;
static u8 s_Page;

static void Piece(const AircraftShape* piece)
{
    i16 l = s_X + piece->dx, t = s_Row + piece->dy, r = l + piece->width, b = t + piece->height;
    u8 sx = piece->atlas_x, ring, width, part;
    u16 sy = piece->atlas_y;
    if (l < s_Left) { sx += s_Left - l; l = s_Left; }
    if (r > s_Right) r = s_Right;
    if (t < s_Top) { sy += s_Top - t; t = s_Top; }
    if (b > s_Limit) b = s_Limit;
    if (r <= l || b <= t) return;
    ring = l & 255; width = r - l;
    for (;;)
    {
        part = width;
        if ((u16)ring + part > 256) part = 256 - ring;
        VDP_CommandLMMM(sx, sy, ring, (u16)s_Page * 256 + t, part, b - t, VDP_OP_TIMP);
        width -= part;
        if (!width) return;
        sx += part; ring = 0;
    }
}

/* Place a shape at world (x, y) in this view (s_Far, s_Shift). */
static u8 s_Far, s_Drawn;
static i16 s_Shift;
static i8 s_Heave;
static Rect* s_Rect;
static SmokeDrawn* s_Out;
static void Place(u16 x, u16 y)
{
    if (s_Far)
    {
        s_X = (i16)x >> 3;
        s_Row = 161 - ((i16)(WINGS_FLIGHT_MAX_Y - 11) - (i16)y >> 3);
    }
    else
    {
        s_X = (i16)x;
        s_Row = (i16)y - (i16)(WINGS_FLIGHT_MAX_Y - 172) + s_Shift;
    }
}

/* Draw frame at the placed position, clipped, and keep its box for
 * Smoke_Restore. The box is worked out in statics: SDCC is slow through a
 * struct pointer. */
static i16 s_BoxLeft, s_BoxRight, s_BoxTop, s_BoxBottom;
static void Shape(u8 frame)
{
    const signed char* box = g_SmokeBox + (frame << 2);
    const AircraftShape* piece;
    Rect* rect;
    u8 k, end;
    if (s_Drawn == SMOKE_DRAWN_MAX) return;
    s_BoxLeft = s_X + box[0]; s_BoxRight = s_BoxLeft + (u8)box[2];
    s_Row -= s_Heave;
    s_BoxTop = s_Row + box[1]; s_BoxBottom = s_BoxTop + (u8)box[3];
    if (s_BoxLeft < s_Left) s_BoxLeft = s_Left;
    if (s_BoxRight > s_Right) s_BoxRight = s_Right;
    if (s_BoxTop < s_Top) s_BoxTop = s_Top;
    if (s_BoxBottom > s_Limit) s_BoxBottom = s_Limit;
    if (s_BoxRight <= s_BoxLeft || s_BoxBottom <= s_BoxTop) return;
    rect = s_Rect;
    rect->left = s_BoxLeft; rect->right = s_BoxRight;
    rect->top = s_BoxTop; rect->bottom = s_BoxBottom;
    s_Out->x = (u16)s_X; s_Out->row = s_Row + s_Heave; s_Out->frame = frame;
    k = g_SmokeFirst[frame]; end = g_SmokeFirst[frame + 1];
    for (piece = &g_SmokePieces[k]; k < end; ++k, ++piece) Piece(piece);
    ++s_Rect; ++s_Out; ++s_Drawn;
}

void Smoke_Draw(u8 page, u16 camera, u8 far, i16 shift, i8 heave, i16 limit) WINGS_BANKED
{
    const SmokePuff* p = g_Smoke;
    const IslandGun* g = g_Island.gun;
    u8 i, frame;
    s_Page = page; s_Far = far; s_Shift = shift; s_Heave = heave;
    s_Rect = s_Old[page]; s_Out = g_SmokeDrawn[page]; s_Drawn = 0;
    s_Left = (i16)camera + 8; s_Right = (i16)camera + 256;
    /* In the close-view pan the top lines (the split above line heave +
     * fine) show VRAM rows -heave .. fine - 1 at the heave-only scroll: keep
     * the shapes out of them. */
    s_Top = far || shift <= (i16)g_PanRows ? 0 : shift - (i16)g_PanRows;
    /* The near view stops above the wave strip; the distant view's flash
     * reaches down to its sand row. */
    s_Limit = far ? (limit > 161 ? 161 : limit) : limit > WAVE_TOP && !g_PanRows ? WAVE_TOP : limit;
    /* Dugout barrels, behind the puffs. */
    for (i = 0; i < ISLAND_MAX_DUGOUTS; ++i, ++g)
    {
        frame = g->frame;
        if (frame == ISLAND_GUN_NONE || (frame == ISLAND_GUN_FAR) != far) continue;
        Place(g->x, WINGS_FLIGHT_MAX_Y - ISLAND_GUN_ALTITUDE);
        Shape(far ? SMOKE_FRAME_FAR_FLASH : SMOKE_FRAME_GUN + frame);
    }
    for (i = 0; i < SMOKE_COUNT; ++i, ++p)
    {
        if (!p->stage) continue;
        Place(p->x, p->y);
        if (far) frame = 5 + (p->stage > 3);
        else frame = p->stage == SMOKE_STAGE_FIRE ? SMOKE_FRAME_FIRE : p->stage - 1;
        Shape(frame);
    }
    s_OldCount[page] = s_Drawn;
    g_SmokeDrawnCount[page] = s_Drawn;
}
#endif
