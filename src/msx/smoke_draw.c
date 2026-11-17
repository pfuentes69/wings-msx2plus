#include "smoke_draw.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "vdp_ring.h"
#include "terrain_renderer.h"
#include "../core/smoke.h"
#include "../core/island.h"
#include "../core/combat.h"
extern CombatState g_Combat;   /* world_flight.c */
#include "mission_island.h"
#include "../generated/hellcat_frames.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_EFFECTS)

#ifdef WINGS_P1_FLIGHT
SmokeDrawn g_SmokeDrawn[2][SMOKE_DRAWN_MAX];
u8 g_SmokeDrawnCount[2];
/* The clip each page was drawn with: Smoke_Restore works each erase box out
 * again from the drawn list (RAM is short; no per-shape rectangles). */
typedef struct Clip { i16 left, right, top, limit; i8 heave; } Clip;
static Clip s_Clip[2];

#define TERRAIN_TOP 24      /* first terrain row; above it the sky is plain */
#define WAVE_TOP 159        /* smoke stays above the wave strip */
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
static void RepaintTiles(u8 page, i16 left, i16 right, i16 top, i16 bottom)
{
    const u16* cached;
    u16 column, tile, base = (u16)page * 256, source;
    i16 y, next, origin = TERRAIN_TOP + g_PanRows;
    u8 slot, row, first = (u8)((top - origin) >> 3), color, decoded;
    for (column = (u16)(left & ~7); (i16)column < right; column += 8)
    {
        slot = (column & 255) >> 3;
        cached = &g_TerrainCached[page][slot][first];
        row = first; y = top; decoded = 0;
        do
        {
            next = origin + (i16)(row + 1) * 8;
            if (next > bottom) next = bottom;
            tile = *cached++;
            if (tile >= TERRAIN_TILE_COUNT)
            {
                if (!decoded) { Terrain_DecodeColumn(column, s_Decoded); decoded = 1; }
                tile = s_Decoded[row];
            }
            if (tile < TERRAIN_TILE_COUNT)
            {
                color = TERRAIN_TILE_COLOR(tile);
                if (color != 255) VDP_CommandHMMV(column & 255, base + y, 8, next - y, color * 17);
                else
                {
                    source = Terrain_TileY(tile) + (u8)(y - origin) - row * 8;
                    VDP_CommandHMMM(g_TileSourceX, source, column & 255, base + y, 8, next - y);
                }
            }
            y = next; ++row;
        } while (y < bottom);
    }
}

static void SkyFill(u8 page, i16 left, i16 right, i16 top, i16 bottom)
{
    left &= ~1; right = (right + 1) & ~1;
    VDP_RING_SET(0, 0, (u16)page * 256 + top, bottom - top, VDP_CMD_HMMV);
    g_VDP_Command.CLR = 0;
    Vdp_RingCopy((u8)left, right - left);
}

/* world_flight.c (resident): one atlas shape from the aircraft banks. */
void Atlas_LoadShape(const AircraftShape* shape);
void Smoke_LoadPieces(void) WINGS_BANKED
{
    u8 i;
    for (i = 0; i < SMOKE_PIECE_COUNT; ++i) Atlas_LoadShape(&g_SmokePieces[i]);
}

void Smoke_ClearPages(void) WINGS_BANKED
{
    g_SmokeDrawnCount[0] = g_SmokeDrawnCount[1] = 0;
}

/* The page's clip in statics while it is restored or drawn: SDCC is slow
 * through a struct pointer. */
static i16 s_Left, s_Right, s_Top, s_Limit;
static i8 s_Heave;
static void UseClip(const Clip* clip)
{
    s_Left = clip->left; s_Right = clip->right; s_Top = clip->top;
    s_Limit = clip->limit; s_Heave = clip->heave;
}

/* A drawn shape's box on the page, clipped as it was drawn. */
static i16 s_BoxLeft, s_BoxRight, s_BoxTop, s_BoxBottom;
static u8 Box(i16 x, i16 row, u8 frame)
{
    const signed char* box = g_SmokeBox + (frame << 2);
    s_BoxLeft = x + box[0]; s_BoxRight = s_BoxLeft + (u8)box[2];
    s_BoxTop = row - s_Heave + box[1]; s_BoxBottom = s_BoxTop + (u8)box[3];
    if (s_BoxLeft < s_Left) s_BoxLeft = s_Left;
    if (s_BoxRight > s_Right) s_BoxRight = s_Right;
    if (s_BoxTop < s_Top) s_BoxTop = s_Top;
    if (s_BoxBottom > s_Limit) s_BoxBottom = s_Limit;
    return s_BoxRight > s_BoxLeft && s_BoxBottom > s_BoxTop;
}

u8 Smoke_Restore(u8 page, u8 rebuilt, u16 camera) WINGS_BANKED
{
    u16 column;
    u8 i, elevator = 0, first, last, n = g_SmokeDrawnCount[page];
    const SmokeDrawn* d = g_SmokeDrawn[page];
    i16 left, right, top = TERRAIN_TOP + g_PanRows;   /* VRAM row of map row 0 */
    (void)camera;
    g_SmokeDrawnCount[page] = 0;
    if (rebuilt) return 0;
    UseClip(&s_Clip[page]);
    for (i = 0; i < n; ++i, ++d)
    {
        /* The whole box, even if the camera has since moved: the page's
         * ring still holds the pixels there. */
        Box((i16)d->x, d->row, d->frame);
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

/* Drawing state as statics: SDCC addresses them directly, where locals go
 * through the IX frame. */
static i16 s_X, s_Row;
static u8 s_Page;

static void Piece(const AircraftShape* piece)
{
    i16 l = s_X + piece->dx, t = s_Row + piece->dy, r = l + piece->width, b = t + piece->height;
    u8 sx = piece->atlas_x;
    u16 sy = piece->atlas_y;
    if (l < s_Left) { sx += s_Left - l; l = s_Left; }
    if (r > s_Right) r = s_Right;
    if (t < s_Top) { sy += s_Top - t; t = s_Top; }
    if (b > s_Limit) b = s_Limit;
    if (r <= l || b <= t) return;
    VDP_RING_SET(sx, sy, (u16)s_Page * 256 + t, b - t, VDP_CMD_LMMM + VDP_OP_TIMP);
    Vdp_RingCopy((u8)l, r - l);
}

/* Place a shape at world (x, y) in this view (s_Far, s_Shift). */
static u8 s_Far, s_Drawn, s_FlagPhase;
static i16 s_Shift;
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

/* Draw frame at the placed position, clipped, and list it for
 * Smoke_Restore and the verification. */
static void Shape(u8 frame)
{
    const AircraftShape* piece;
    SmokeDrawn* out;
    u8 k, end;
    if (s_Drawn == SMOKE_DRAWN_MAX || !Box(s_X, s_Row, frame)) return;
    out = s_Out;
    out->x = (u16)s_X; out->row = s_Row; out->frame = frame;
    s_Row -= s_Heave;
    k = g_SmokeFirst[frame]; end = g_SmokeFirst[frame + 1];
    for (piece = &g_SmokePieces[k]; k < end; ++k, ++piece) Piece(piece);
    ++s_Out; ++s_Drawn;
}

void Smoke_Draw(u8 page, u16 camera, u8 far, i16 shift, i8 heave, i16 limit) WINGS_BANKED
{
    const SmokePuff* p = g_Smoke;
    const IslandGun* g = g_Island.gun;
    const IslandSoldier* soldier = g_Island.soldier;
    Clip* clip = &s_Clip[page];
    u8 i, frame;
    s_Page = page; s_Far = far; s_Shift = shift;
    s_Out = g_SmokeDrawn[page]; s_Drawn = 0;
    clip->heave = heave;
    clip->left = (i16)camera + 8; clip->right = (i16)camera + 256;
    /* In the close-view pan the top lines (the split above line heave +
     * fine) show VRAM rows -heave .. fine - 1 at the heave-only scroll: keep
     * the shapes out of them. */
    clip->top = g_TopClip;   /* 0 in the distant view */
    /* The near view stops above the wave strip; the distant view's flash
     * reaches down to its sand row. */
    clip->limit = far ? (limit > 161 ? 161 : limit) : limit > WAVE_TOP && !g_PanRows ? WAVE_TOP : limit;
    UseClip(clip);
    /* Dugout barrels, behind the puffs. */
    for (i = 0; i < ISLAND_MAX_DUGOUTS; ++i, ++g)
    {
        frame = g->frame;
        if (frame == ISLAND_GUN_NONE || (frame == ISLAND_GUN_FAR) != far) continue;
        Place(g->x, WINGS_FLIGHT_MAX_Y - ISLAND_GUN_ALTITUDE);
        Shape(far ? SMOKE_FRAME_FAR_FLASH : SMOKE_FRAME_GUN + frame);
    }
    /* The island flag's cloth (0x3b52), close view only, waving through
     * flg0..flg2 until the island is cleared; the pole is in the scenery. */
#if ISLAND_COUNT
    /* (A map without islands, j, must not compile this loop: SDCC 4.6
     * dropped the rest of the function after it, docs/sdcc-pitfalls.md.) */
    if (!far)
        for (i = 0; i < ISLAND_COUNT; ++i)
        {
            if (g_Island.cleared & (1 << i)) continue;
            if ((u16)(s_IslandFlagX[i] - camera + 16) > 288u) continue;
            /* RAM is not cleared at boot: any phase above 2 restarts. */
            if (!s_FlagPhase-- || s_FlagPhase > 2) s_FlagPhase = 2;
            Place(s_IslandFlagX[i], WINGS_FLIGHT_MAX_Y - 11);
            Shape(SMOKE_FRAME_FLAG + s_FlagPhase);
        }
#endif
    /* Island soldiers (0x3eee) at altitude 12: walking guy0..guy4, dying
     * guy5..guy7, the corpse guy8 (+ 9 facing left). The distant view
     * shows a 2-frame figure and no corpses. */
    /* None out, or no island land in view: no soldier to place. */
    i = ISLAND_MAX_SOLDIERS;
    if (g_Island.out)
    {
        i16 low = far ? g_SoldierLandLow >> 3 : g_SoldierLandLow, high = far ? g_SoldierLandHigh >> 3 : g_SoldierLandHigh;
        if ((i16)camera + 272 > low && (i16)camera - 16 < high) i = 0;
    }
    for (; i < ISLAND_MAX_SOLDIERS; ++i, ++soldier)
    {
        if (!(soldier->state & 7)) continue;
        if (far && (soldier->state & 7) == ISLAND_SOLDIER_DEAD) continue;
        /* Off this view: nothing to place (x alone is cheap). */
        Soldier_Now(soldier);
        if ((u16)((far ? g_SoldierX >> 3 : g_SoldierX) - (i16)camera + 16) > 288u) continue;
        frame = far ? SMOKE_FRAME_FAR_SOLDIER + (g_SoldierFrame & 1)
                    : SMOKE_FRAME_SOLDIER + g_SoldierFrame + (soldier->dir < 0 ? 9 : 0);
        Place((u16)g_SoldierX, WINGS_FLIGHT_MAX_Y - ISLAND_SOLDIER_ALTITUDE);
        Shape(frame);
    }
    for (i = 0; i < SMOKE_COUNT; ++i, ++p)
    {
        if (!p->stage) continue;
        Place(p->x, p->y);
        if (far) frame = 5 + (p->stage > 3);
        else frame = p->stage == SMOKE_STAGE_FIRE ? SMOKE_FRAME_FIRE : p->stage - 1;
        Shape(frame);
    }
    /* Rockets (0x0702), drawn like the original's ordnance at 11 px below
     * their altitude: ro01.. before ignition, rc01.. lit, bumb far off. */
    if (g_Combat.rockets)
    {
        const CombatRocket* r = g_Combat.rocket;
        i16 x;
        for (i = 0; i < COMBAT_ROCKETS; ++i, ++r)
        {
            if (!r->live) continue;
            x = r->x.w.whole;   /* signed: open sea past the map's ends */
            if ((u16)((far ? x >> 3 : x) - camera + 24) > 304u) continue;
            Place((u16)x, WINGS_FLIGHT_MAX_Y - r->y);
            Shape(far ? SMOKE_FRAME_FAR_ROCKET : r->frame + (r->live == 1 ? SMOKE_FRAME_ROCKET_UNLIT : SMOKE_FRAME_ROCKET));
        }
    }
    g_SmokeDrawnCount[page] = s_Drawn;
}
#endif
