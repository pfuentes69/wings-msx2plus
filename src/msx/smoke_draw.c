#include "smoke_draw.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "terrain_renderer.h"
#include "column_ops.h"
#include "../core/smoke.h"
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

/* Repaint tile rows first..last of a column from the page's tile cache (no
 * map decode): the cached rows go to Column_Runs as the "decoded" column
 * against a copy with those rows invalid. */
static u16 s_Rows[TERRAIN_MAP_ROWS + 1], s_Stale[TERRAIN_MAP_ROWS + 1];
static void RepaintRows(u8 page, u16 world, u8 first, u8 last)
{
    u8 slot = (world & 255) >> 3, row;
    const u16* cached = g_TerrainCached[page][slot];
    if (g_TerrainColumns[page][slot] == 65535u) return;
    for (row = 0; row < TERRAIN_MAP_ROWS; ++row) s_Rows[row] = s_Stale[row] = cached[row];
    s_Rows[TERRAIN_MAP_ROWS] = 65534u;   /* Column_Runs' sentinel */
    s_Stale[TERRAIN_MAP_ROWS] = 65535u;
    for (row = first; row <= last; ++row) s_Stale[row] = 65535u;
    g_ColumnX = world & 255;
    g_ColumnY = (u16)page * 256 + 24 + g_PanRows;   /* map rows, drawn at the pan */
    Column_Runs(s_Stale, s_Rows);
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
        for (column = (u16)(left & ~7); (i16)column < right; column += 8)
            RepaintRows(page, column, first, last);
    }
    return elevator;
}

/* Drawing state as statics: SDCC addresses them directly, where locals go
 * through the IX frame. */
static i16 s_X, s_Row, s_Left, s_Right, s_Limit;
static u8 s_Page;

static void Piece(const AircraftShape* piece)
{
    i16 l = s_X + piece->dx, t = s_Row + piece->dy, r = l + piece->width, b = t + piece->height;
    u8 sx = piece->atlas_x, ring, width, part;
    u16 sy = piece->atlas_y;
    if (l < s_Left) { sx += s_Left - l; l = s_Left; }
    if (r > s_Right) r = s_Right;
    if (t < 0) { sy -= t; t = 0; }
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

void Smoke_Draw(u8 page, u16 camera, u8 far, i16 shift, i8 heave, i16 limit) WINGS_BANKED
{
    const SmokePuff* p = g_Smoke;
    const signed char* box;
    Rect* rect = s_Old[page];
    SmokeDrawn* out = g_SmokeDrawn[page];
    u8 i, k, frame, drawn = 0;
    s_Page = page;
    s_Left = (i16)camera + 8; s_Right = (i16)camera + 256;
    s_Limit = limit > WAVE_TOP && !g_PanRows ? WAVE_TOP : limit;
    for (i = 0; i < SMOKE_COUNT; ++i, ++p)
    {
        if (!p->stage) continue;
        if (far)
        {
            frame = 5 + (p->stage > 3);
            s_X = (i16)p->x >> 3;
            s_Row = 161 - ((i16)(WINGS_FLIGHT_MAX_Y - 11) - (i16)p->y >> 3);
        }
        else
        {
            frame = p->stage - 1;
            s_X = (i16)p->x;
            s_Row = (i16)p->y - (i16)(WINGS_FLIGHT_MAX_Y - 172) + shift;
        }
        /* The frame's box, clipped: what Smoke_Restore erases. */
        box = g_SmokeBox + frame * 4;
        rect->left = s_X + box[0]; rect->right = rect->left + box[2];
        rect->top = s_Row - heave + box[1]; rect->bottom = rect->top + box[3];
        if (rect->left < s_Left) rect->left = s_Left;
        if (rect->right > s_Right) rect->right = s_Right;
        if (rect->top < 0) rect->top = 0;
        if (rect->bottom > s_Limit) rect->bottom = s_Limit;
        if (rect->right <= rect->left || rect->bottom <= rect->top) continue;
        out->x = (u16)s_X; out->row = s_Row; out->frame = frame;
        s_Row -= heave;
        for (k = g_SmokeFirst[frame]; k < g_SmokeFirst[frame + 1]; ++k) Piece(&g_SmokePieces[k]);
        ++rect; ++out; ++drawn;
    }
    s_OldCount[page] = drawn;
    g_SmokeDrawnCount[page] = drawn;
}
#endif
