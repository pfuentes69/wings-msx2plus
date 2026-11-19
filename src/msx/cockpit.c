#include <stdint.h>
#include "cockpit.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "../core/island.h"
#include "../core/planes.h"
#include "../core/ships.h"
#include "scenery_load.h"
#include "cockpit_map.h"   /* the map's features (src/generated/map_<map>) */
WINGS_CODE_SEGMENT(WINGS_SEGMENT_COCKPIT)

/* The original's (docs/research/amiga-cockpit-view.md), the port's model in
 * tools/convert_cockpit.py (scene, compose): keep the two together. */
#define WIDTH 46
#define ROWS 24
#define SKY 0x22
#define SEA 0x99
#define LAND 0x55
#define FAR_ALTITUDE 186     /* above: the distant view, plain sky */
#define LIFT 5               /* the port's horizon: 5 rows higher than the original's, dropping half as fast */
#define KIND_TOWER 4

CockpitState g_Cockpit;
static u8 s_Next[COCKPIT_SCENE_BYTES];
/* Band b (0 nearest .. 10): the ground it covers in columns ahead, and its
 * frames (ground objects 1..6, carrier and tower 0..7). */
static const u8 s_Far[11] = {20, 29, 39, 50, 62, 75, 89, 104, 120, 155, 190};
static const u8 s_K6[11] = {6, 6, 5, 5, 4, 4, 3, 3, 2, 2, 1};
static const u8 s_K7[11] = {7, 7, 6, 6, 5, 4, 3, 2, 1, 0, 0};

/* The planes' view size by band (tools/convert_cockpit.py PLANE_SIZE). */
static const u8 s_PlaneSet[11] = {
    COCKPIT_PLANE1, COCKPIT_PLANE1, COCKPIT_PLANE1, COCKPIT_PLANE2, COCKPIT_PLANE2, COCKPIT_PLANE2,
    COCKPIT_PLANE2, COCKPIT_PLANE2, COCKPIT_PLANE2, COCKPIT_PLANE3, COCKPIT_PLANE3};

/* (1 << b) - 1 */
static const u16 s_Below[12] = {0, 1, 3, 7, 15, 31, 63, 127, 255, 511, 1023, 2047};

static u16 s_Col;
static u8 s_Left, s_First, s_Last, s_ObjectLo;
static int16_t s_Hi;
/* What the scene was last computed from (Cockpit_Draw). */
static u16 s_InCol;
static u8 s_InBase, s_InSight, s_InLeft, s_InArrow, s_InWrecked, s_InGone, s_InPlanes[2 * PLANES_MAX], s_PlanesShown;
/* A scene waiting to be composed (from Cockpit_Draw's inputs), and the
 * renders it has waited. */
static u8 s_Pending, s_Again, s_Stale, s_PendAltitude;
static u16 s_PendX;
#define STALE 12  /* renders a picture waits for idle time (about 1.6 s) before renders step it */

/* The bands the columns first..last fall in: s_First..s_Last (0: none);
 * s_Hi their farthest distance ahead. In C:
 *   lo, hi = s_Left ? col - last, col - first : first - col, last - col;
 *   s_Hi = hi; if (hi < 13 || lo > 190) return 0;
 *   s_First = FirstBand[max(lo, 13)]; s_Last = LastBand[min(hi, 190)];
 *   return s_First <= s_Last; */
static u8 Bands(u16 first, u16 last) __naked
{
    first; last;   /* HL, DE */
    __asm
        ld bc, (_s_Col)
        ld a, (_s_Left)
        or a
        jr z, bands_right$
        push hl              ; first
        ld h, b
        ld l, c
        or a
        sbc hl, de           ; lo = col - last
        ex de, hl
        pop hl
        push de
        ld d, h
        ld e, l              ; de = first
        ld h, b
        ld l, c
        or a
        sbc hl, de           ; hi = col - first
        pop de               ; de = lo
        jr bands_have$
    bands_right$:
        or a
        sbc hl, bc           ; lo = first - col
        ex de, hl            ; de = lo, hl = last
        or a
        sbc hl, bc           ; hi = last - col
    bands_have$:
        ld (_s_Hi), hl
        bit 7, h
        jr nz, bands_none$   ; hi < 0
        ld a, h
        or a
        jr nz, bands_far$    ; hi >= 256
        ld a, l
        cp #13
        jr c, bands_none$
        cp #191
        jr c, bands_hi$
    bands_far$:
        ld a, #190
    bands_hi$:
        ld c, a              ; hi, clamped
        bit 7, d
        jr nz, bands_near$   ; lo < 0
        ld a, d
        or a
        jr nz, bands_none$   ; lo >= 256
        ld a, e
        cp #191
        jr nc, bands_none$
        cp #13
        jr nc, bands_lo$
    bands_near$:
        ld a, #13
    bands_lo$:
        ld e, a
        ld d, #0
        ld hl, #_g_CockpitFirstBand
        add hl, de
        ld b, (hl)
        ld a, b
        ld (_s_First), a
        ld e, c
        ld hl, #_g_CockpitLastBand
        add hl, de
        ld a, (hl)
        ld (_s_Last), a
        cp b
        jr c, bands_none$    ; last < first: a gap between bands
        ld a, #1
        ret
    bands_none$:
        xor a
        ret
    __endasm;
}

static u16 Mask(u16 first, u16 last)
{
    return Bands(first, last) ? s_Below[s_Last + 1] & ~s_Below[s_First] : 0;
}

/* The planes (0x4206): in a band 48..1280 px ahead, their row from the
 * original's horizon (base: altitude / 16 + 17, which the gunsight matches)
 * and their altitude; each slot's row
 * and view + 1 (0: not shown) into s_InPlanes. Returns 1 if they changed. */
static u8 Planes(u8 base, u16 col, u8 left)
{
    const Plane* e = g_Planes.plane;
    u8* out = s_InPlanes;
    int16_t at, row;
    u8 i, b, view, r, v, changed = 0;
    for (i = 0; i < PLANES_MAX; ++i, ++e, out += 2)
    {
        r = v = 0;
        if (base == 255 || (e->state != PLANE_FLYING && e->state != PLANE_DOWN)) goto next;
        at = e->x >> 3;
        at = left ? (int16_t)col - at : at - (int16_t)col;
        if (at < 0 || at >= 160) goto next;
        b = g_CockpitPlaneBand[(u8)at];
        if (b == 255) goto next;
        row = (int16_t)(base + 10 - b) - ((e->alt >> 2) + 4);
        if (row < -12 || row >= 36) goto next;
        view = e->shape + (left ? 0 : 28);
        if (view >= 56) view -= 56;
        r = (u8)row;
        v = s_PlaneSet[b] + g_CockpitPlaneView[view] + 1;
    next:
        if (out[0] != r || out[1] != v) { out[0] = r; out[1] = v; changed = 1; }
    }
    return changed;
}

static void Scene(u16 x, u8 altitude, u8 left, u8 arrow)
{
    u8 i, b, kind, frame, cur, d, deck;
    u8 far[11];
    u16 mask, n, from, to;
    {
        u8* p = s_Next;
        for (i = COCKPIT_SCENE_BYTES; i; --i) *p++ = 0;
        for (p = far, i = 11; i; --i) *p++ = 0;
    }
    s_Next[2] = arrow;
    if (altitude > FAR_ALTITUDE) { s_Next[0] = 255; return; }
    s_Col = x >> 3; s_Left = left;
    s_Next[0] = (altitude >> 5) + 17 - LIFT;   /* the original's altitude / 16 + 17 (convert_cockpit.horizon) */
    s_Next[3] = altitude >= 81 ? 17 : ((81 - altitude) >> 2) + 6;
    s_Next[1] = left;
    deck = s_Col >= COCKPIT_CARRIER_FIRST && s_Col <= COCKPIT_CARRIER_LAST;
    if (deck)
    {
        n = left ? COCKPIT_CARRIER_LAST - s_Col + 1 : s_Col - COCKPIT_CARRIER_FIRST + 1;
        s_Next[1] |= 2 | (n < 90 ? (u8)((n * 43) >> 8) : 15) << 4;   /* n / 6 */
    }
#if COCKPIT_LANDS
    for (mask = 0, i = 0; i < COCKPIT_LANDS; ++i) mask |= Mask(s_LandFirst[i], s_LandLast[i]);
    s_Next[4] = (u8)mask; s_Next[5] = mask >> 8;
#endif
#if COCKPIT_TREES
    for (mask = 0, i = 0; i < COCKPIT_TREES; ++i) mask |= Mask(s_TreeFirst[i], s_TreeLast[i]);
    s_Next[6] = (u8)mask; s_Next[7] = mask >> 8;
#endif
    /* The objects that can be within 190 columns (sorted by first column;
     * the window moves with the plane). */
    from = s_Col > 190 + COCKPIT_OBJECT_REACH ? s_Col - 190 - COCKPIT_OBJECT_REACH : 0;
    to = s_Col + 190;
    i = s_ObjectLo < COCKPIT_OBJECTS ? s_ObjectLo : 0;
    while (i && s_ObjectFirst[i - 1] >= from) --i;
    while (i < COCKPIT_OBJECTS && s_ObjectFirst[i] < from) ++i;
    s_ObjectLo = i;
    for (; i < COCKPIT_OBJECTS && s_ObjectFirst[i] <= to; ++i)
    {
        kind = s_ObjectKind[i];
        if (deck && kind >= 3) continue;   /* over the carrier: the deck view shows it (ships hidden) */
        if (kind == 5 && (g_ShipsGone >> s_ObjectIndex[i]) & 1) continue;   /* sunk */
        if (!Bands(s_ObjectFirst[i], s_ObjectLast[i])) continue;
        for (b = s_First; b <= s_Last; ++b)
        {
            d = s_Hi < s_Far[b] ? (u8)s_Hi : s_Far[b];
            cur = s_Next[8 + b];
            if (cur > COCKPIT_TOWER && cur <= COCKPIT_DECK) continue;   /* a tower sticks */
            if (kind != KIND_TOWER && d <= far[b]) continue;            /* the farthest wins */
            far[b] = d;
            switch (kind)
            {
            case 0: frame = (g_Island.hut[s_ObjectIndex[i]].wrecked ? COCKPIT_WRECK : COCKPIT_HUT) + s_K6[b] - 1; break;
            case 1: frame = COCKPIT_DUGOUT + s_K6[b] - 1; break;
            case 2: frame = COCKPIT_GUN + s_K6[b] - 1; break;
            case 5: frame = s_ShipView[s_ObjectIndex[i]] + s_K7[b] + (left ? 8 : 0); break;
            default: frame = (kind == 3 ? COCKPIT_CARRIER : COCKPIT_TOWER) + s_K7[b] + (left ? 8 : 0); break;
            }
            s_Next[8 + b] = frame + 1;
        }
    }
    for (i = 0; i < 2 * PLANES_MAX; ++i) s_Next[19 + i] = s_InPlanes[i];
}

void Cockpit_Load(void) WINGS_BANKED
{
    u8 slot, row, line[24];
    u16 offset = 0, y;
    s_Pending = s_Again = s_PlanesShown = 0;   /* RAM is not cleared at boot */
    for (slot = 0; slot < 2 * PLANES_MAX; ++slot) s_InPlanes[slot] = 0;
    for (slot = 1; slot < COCKPIT_SLOTS; ++slot)
        for (row = 0, y = g_CockpitSlotY[slot] - 512; row < 24; ++row, ++y, offset += 24)
        {
            if (slot == COCKPIT_BANK_SLOTS + 1 && !row) offset = 0;   /* the second bank */
            Scenery_Read(slot <= COCKPIT_BANK_SLOTS ? COCKPIT_BANK : COCKPIT_BANK2, offset, line, 24);
            VDP_WriteVRAM(line, y * 128 + g_CockpitSlotX[slot] / 2, 1, 24);
        }
}

/* 1 if s_Next differs from the buffer's scene. */
static u8 Differs(void) __naked
{
    __asm
        ld hl, #_s_Next
        ld de, #_g_Cockpit
        ld b, #COCKPIT_SCENE_BYTES
    differs_loop$:
        ld a, (de)
        cp (hl)
        jr nz, differs_yes$
        inc hl
        inc de
        djnz differs_loop$
        xor a
        ret
    differs_yes$:
        ld a, #1
        ret
    __endasm;
}

/* s_Next becomes the buffer's scene. */
static void Keep(void) __naked
{
    __asm
        ld hl, #_s_Next
        ld de, #_g_Cockpit
        ld bc, #COCKPIT_SCENE_BYTES
        ldir
        ret
    __endasm;
}

static void Fill(u8 y, u8 rows, u8 colour)
{
    g_VDP_Command.DX = COCKPIT_BUFFER_X;
    g_VDP_Command.DY = COCKPIT_BUFFER_Y + y;
    g_VDP_Command.NX = 48;
    g_VDP_Command.NY = rows;
    g_VDP_Command.CLR = colour;
    g_VDP_Command.ARG = 0;
    g_VDP_Command.CMD = VDP_CMD_HMMV;
    VDP_CommandSetupR36();
}

/* Shape i with its origin at this row (and the window's centre column: its
 * columns come clipped, tools/convert_cockpit.py), clipped to rows top..23. */
static void Blit(u8 i, u8 row, u8 top)
{
    int8_t y = (int8_t)row - g_CockpitOY[i];
    u8 h = g_CockpitH[i], skip = 0;
    if (y >= ROWS) return;
    if (y < (int8_t)top)
    {
        skip = top - y;
        if (skip >= h) return;
        h -= skip; y = top;
    }
    if ((u8)y + h > ROWS) h = ROWS - y;
    g_VDP_Command.SX = g_CockpitX[i];
    g_VDP_Command.SY = g_CockpitY[i] + skip;
    g_VDP_Command.DX = g_CockpitDX[i];
    g_VDP_Command.DY = COCKPIT_BUFFER_Y + (u8)y;
    g_VDP_Command.NX = g_CockpitW[i];
    g_VDP_Command.NY = h;
    g_VDP_Command.ARG = 0;
    g_VDP_Command.CMD = VDP_CMD_LMMM + VDP_OP_TIMP;
    VDP_CommandSetupR32();
}

/* Band b's jungle strip. */
static const u8 s_Tree[11] = {
    COCKPIT_TREE + 5, COCKPIT_TREE + 5, COCKPIT_TREE + 4, COCKPIT_TREE + 4, COCKPIT_TREE + 3, COCKPIT_TREE + 3,
    COCKPIT_TREE + 2, COCKPIT_TREE + 2, COCKPIT_TREE + 1, COCKPIT_TREE + 1, COCKPIT_TREE};

/* The picture in two halves: the sky, the sea and the ground, far to near
 * a row lower each band; then the targets on it (the port draws them after
 * the ground, so a nearer band's jungle does not hide them), the deck view
 * and the sight. */
static void ComposeFar(void)
{
    u8 base = s_Next[0], b, row;
    u16 bit = 1 << 10;
    u16 land = s_Next[4] | (u16)s_Next[5] << 8, trees = s_Next[6] | (u16)s_Next[7] << 8;
    Fill(0, ROWS, SKY);
    if (base == 255) return;
    if (base < ROWS) Fill(base, ROWS - base, SEA);
    for (b = 11, row = base; b; --b, bit >>= 1, ++row)
    {
        if (land & bit && row < ROWS) Fill(row, 1, LAND);
        if (trees & bit) Blit(s_Tree[b - 1], row, 0);
    }
}

static void ComposeNear(void)
{
    u8 base = s_Next[0], row, step, top, shape, size;
    const u8* object = s_Next + 8 + 10;
    if (base != 255)
    {
        if (s_Next[1] & 2)
        {
            /* The deck view (0x4430): it slides down a row every 6 columns
             * of deck behind, its far part clipped away. */
            step = s_Next[1] >> 4;
            row = base + step + 9;
            top = base + (step > 7 ? step - 7 : 0);
            shape = s_Next[1] & 1 ? 13 : 5;   /* 3dcn, 3dtn facing left; 3dcf, 3dtf */
            Blit(COCKPIT_DECK + (step < 6 ? step >> 1 : 3), row + 1, top);
            Blit(COCKPIT_CARRIER + shape, row, top);
            Blit(COCKPIT_TOWER + shape, row, 0);
        }
        /* The gunsight under the targets and planes (the original draws it
         * last, over them: it hid them, on the column they are drawn at). */
        Blit(COCKPIT_SIGHT, s_Next[3], 0);
        for (row = base; object >= s_Next + 8; ++row, --object)
            if (*object) Blit(*object - 1, row, 0);
        /* The planes: the farthest size first, then by slot. */
        for (size = COCKPIT_PLANE3; ; size = size == COCKPIT_PLANE3 ? COCKPIT_PLANE2 : COCKPIT_PLANE1)
        {
            for (object = s_Next + 19; object < s_Next + 19 + 2 * PLANES_MAX; object += 2)
                if (object[1] && object[1] - 1 >= size && object[1] - 1 < size + 26) Blit(object[1] - 1, object[0], 0);
            if (size == COCKPIT_PLANE1) break;
        }
    }
    VDP_CommandWait();
}

/* One step of the work: 1 the scene from the inputs (done if unchanged),
 * 2 and 3 the picture's halves; then the buffer holds it (a new
 * generation). A change of inputs meanwhile waits for the picture
 * (s_Again), so a run of changes still completes pictures. */
static void Step(void)
{
    switch (s_Pending)
    {
    case 1:
        Scene(s_PendX, s_PendAltitude, s_InLeft, s_InArrow);
        s_Pending = Differs() || g_Cockpit.generation == 255 ? 2 : 0;
        break;
    case 2:
        ComposeFar();
        s_Pending = 3;
        break;
    default:
        ComposeNear();
        Keep();
        if (++g_Cockpit.generation == 255) g_Cockpit.generation = 0;
        s_Pending = s_Again;
        s_Again = s_Stale = 0;   /* the next picture waits again */
        break;
    }
    if (!s_Pending) s_Stale = 0;
}

u8 Cockpit_Work(void) WINGS_BANKED
{
    if (!s_Pending) return 0;
    do Step(); while (s_Pending >= 2);
    return 1;
}

u8 Cockpit_Draw(u8 page, u16 x, u16 y, u8 facing_left) WINGS_BANKED
{
    u8 changed = g_Cockpit.generation == 255, altitude, base, sight, wrecked, gone, planes;
    u8 arrow = g_Planes.live ? Planes_Arrow((int16_t)x) : 0;
    y = WINGS_FLIGHT_MAX_Y - y;
    altitude = y > 255 ? 255 : (u8)y;
    base = altitude > FAR_ALTITUDE ? 255 : altitude >> 4;
    sight = altitude >= 81 ? 17 : ((81 - altitude) >> 2) + 6;
    wrecked = g_IslandWrecks;
    gone = g_ShipsGone;
    /* The scene only when what it comes from has changed: the plane's
     * place, and the planes' rows and views (they move on their own). */
    /* (None in the air: nothing to look at, unless some were shown.) */
    planes = g_Planes.live || s_PlanesShown ? Planes(base == 255 ? 255 : base + 17, x >> 3, facing_left) : 0;
    s_PlanesShown = g_Planes.live;
    if (changed || planes || (x >> 3) != s_InCol || base != s_InBase || sight != s_InSight ||
        facing_left != s_InLeft || arrow != s_InArrow || wrecked != s_InWrecked || gone != s_InGone)
    {
        s_InGone = gone;
        s_InCol = x >> 3; s_InBase = base; s_InSight = sight;
        s_InLeft = facing_left; s_InArrow = arrow; s_InWrecked = wrecked;
        s_PendX = x; s_PendAltitude = altitude;
        if (s_Pending >= 2) s_Again = 1; else s_Pending = 1;
    }
    /* Composed in idle time (Cockpit_Work); without it, a step a render
     * once it has waited (all at once the first time). */
    if (changed) while (s_Pending) Step();
    else if (s_Pending && ++s_Stale > STALE) Step();
    /* The buffer, unless half drawn. */
    if (g_Cockpit.shown[page] != g_Cockpit.generation && s_Pending != 3)
    {
        y = (u16)page * 256 + 172 + COCKPIT_WINDOW_Y;
        VDP_CommandHMMM(COCKPIT_BUFFER_X, COCKPIT_BUFFER_Y, COCKPIT_WINDOW_X, y, WIDTH, ROWS);
        /* The torpedo plane's arrow (0xf21a) at the window's top centre. */
        if (arrow == 1)
            VDP_CommandLMMM(COCKPIT_ARROW0_ATLAS_X, COCKPIT_ARROW0_ATLAS_Y, COCKPIT_WINDOW_X + COCKPIT_ARROW_LEFT_X, y, 16, COCKPIT_ARROW_HEIGHT, VDP_OP_TIMP);
        else if (arrow == 2)
            VDP_CommandLMMM(COCKPIT_ARROW1_ATLAS_X, COCKPIT_ARROW1_ATLAS_Y, COCKPIT_WINDOW_X + COCKPIT_ARROW_RIGHT_X, y, 16, COCKPIT_ARROW_HEIGHT, VDP_OP_TIMP);
        g_Cockpit.shown[page] = g_Cockpit.generation;
    }
    return g_Cockpit.generation;
}
