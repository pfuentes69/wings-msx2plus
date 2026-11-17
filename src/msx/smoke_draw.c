#include "smoke_draw.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "vdp_ring.h"
#include "terrain_renderer.h"
#include "../core/smoke.h"
#include "../core/island.h"
#include "../core/combat.h"
#include "../core/ships.h"
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

/* A drawn shape's box on the page, clipped as it was drawn: Box(frame)
 * for the shape at (s_BX, s_BY), in Z80. */
static i16 s_BoxLeft, s_BoxRight, s_BoxTop, s_BoxBottom, s_BX, s_BY;
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
    UseClip(&s_Clip[page]);
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

/* Drawing state as statics: SDCC addresses them directly, where locals go
 * through the IX frame. */
static i16 s_X, s_Row;
static u8 s_Page;

/* Statics, not locals: SDCC reaches them directly (the locals' IX frame
 * made this ~2,700 T-states a piece). */
static i16 s_PL, s_PT, s_PR, s_PB;
static void Piece(const AircraftShape* piece)
{
    s_PL = s_X + piece->dx; s_PR = s_PL + piece->width;
    s_PT = s_Row + piece->dy; s_PB = s_PT + piece->height;
    g_VDP_Command.SX = piece->atlas_x;
    g_VDP_Command.SY = piece->atlas_y;
    if (s_PL < s_Left) { g_VDP_Command.SX += s_Left - s_PL; s_PL = s_Left; }
    if (s_PR > s_Right) s_PR = s_Right;
    if (s_PT < s_Top) { g_VDP_Command.SY += s_Top - s_PT; s_PT = s_Top; }
    if (s_PB > s_Limit) s_PB = s_Limit;
    if (s_PR <= s_PL || s_PB <= s_PT) return;
    g_VDP_Command.DY = ((u16)s_Page << 8) + s_PT;
    g_VDP_Command.NY = s_PB - s_PT;
    g_VDP_Command.ARG = 0;
    g_VDP_Command.CMD = VDP_CMD_LMMM + VDP_OP_TIMP;
    Vdp_RingCopy((u8)s_PL, s_PR - s_PL);
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
    if (s_Drawn == SMOKE_DRAWN_MAX) return;
    s_BX = s_X; s_BY = s_Row;
    if (!Box(frame)) return;
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
    /* Ship guns (0x4c3e): barrels and their flashes, expl far off. */
    for (i = 0; i < g_Ships.shown_count; ++i)
    {
        const ShipGunShown* gun = &g_Ships.shown[i];
        /* Off this view (most of a ship's guns): skip before any clipping. */
        if ((u16)((far ? (i16)gun->x >> 3 : (i16)gun->x) - (i16)camera + 24) > 304u) continue;
        Place(gun->x, WINGS_FLIGHT_MAX_Y - gun->altitude);
        Shape(far ? SMOKE_FRAME_FAR_FLASH : SMOKE_FRAME_GUN + gun->frame);
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
    /* Shell splashes (0x52f8): spl6 down to spl1 at altitude 13, a
     * ricochet on land at 9; far off, the last three frames only. */
    if (g_Ships.splashes)
    {
        const ShipSplash* s = g_Ships.splash;
        for (i = 0; i < SHIP_SPLASHES; ++i, ++s)
        {
            if (!s->life || (far && (s->land || s->life > 3))) continue;
            if ((u16)((far ? s->x >> 3 : s->x) - (i16)camera + 24) > 304u) continue;
            Place((u16)s->x, WINGS_FLIGHT_MAX_Y - (s->land ? 9 : 13));
            Shape(far ? SMOKE_FRAME_FAR_SPLASH + s->life - 1 :
                  s->land ? SMOKE_FRAME_RICOCHET : SMOKE_FRAME_SPLASH + s->life - 1);
        }
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
    /* The falling torpedo (0x0726), as ordnance 11 px below its altitude:
     * tor2, tor7 facing left, bumb far off. Running, only its wake shows. */
    if (g_Combat.torpedo.live == TORPEDO_FALLING)
    {
        i16 x = g_Combat.torpedo.x.w.whole;
        if ((u16)((far ? x >> 3 : x) - camera + 24) <= 304u)
        {
            Place((u16)x, WINGS_FLIGHT_MAX_Y - g_Combat.torpedo.y);
            Shape(far ? SMOKE_FRAME_FAR_ROCKET : SMOKE_FRAME_TORPEDO + g_Combat.torpedo.left);
        }
    }
    g_SmokeDrawnCount[page] = s_Drawn;
}
#endif
