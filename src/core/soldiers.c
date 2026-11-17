#include "island.h"
#include "mission.h"
#include "sound.h"
#include "mission_island.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_MISSION)

/* The island soldiers' update (0x3eee) and deaths (0x1a8c), banked apart
 * from the rest of the island (segment 23 is full). island.c releases them
 * (0x1de4, 0x1e82, 0x4fee). */
#ifdef WINGS_P1_FLIGHT

#define ISLAND_SOLDIERS (ISLAND_GARRISON * (ISLAND_HUTS + ISLAND_DUGOUTS))
#define STATE(s) ((s)->state & 7)   /* bit 3: PENDING, bits 4..7: island */
#ifdef __SDCC
#include <stddef.h>
#define ISLAND_SOLDIER_OFFSET 162   /* used by Walk's assembly */
typedef char SoldierOffset[offsetof(IslandState, soldier) == ISLAND_SOLDIER_OFFSET ? 1 : -1];
#endif

/* Each island's land: the surface around its beach anchors (Island_Reset).
 * A soldier stays on it; the next step's water check can only fail at its
 * ends. */
static int16_t s_LandLeft[ISLAND_COUNT ? ISLAND_COUNT : 1], s_LandRight[ISLAND_COUNT ? ISLAND_COUNT : 1];   /* a map may have none (j) */
int16_t g_SoldierLandLow, g_SoldierLandHigh;   /* all islands' land */

void Soldiers_Reset(void) WINGS_BANKED
{
    uint8_t i;
    int16_t x;
    g_SoldierLandLow = g_SoldierLandHigh = 0;
    if (!ISLAND_COUNT) return;
    for (i = 0; i < ISLAND_COUNT; ++i)
    {
        /* The land around the beach anchors, to the first water. */
        x = (int16_t)s_IslandLeft[i];
        while (x > 0 && Mission_Surface((uint16_t)(x - 1)) != MISSION_SEA) --x;
        s_LandLeft[i] = x;
        x = (int16_t)s_IslandRight[i];
        while (Mission_Surface((uint16_t)x) != MISSION_SEA) ++x;
        s_LandRight[i] = x;
    }
    g_SoldierLandLow = s_LandLeft[0]; g_SoldierLandHigh = s_LandRight[0];
    for (i = 1; i < ISLAND_COUNT; ++i)
    {
        if (s_LandLeft[i] < g_SoldierLandLow) g_SoldierLandLow = s_LandLeft[i];
        if (s_LandRight[i] > g_SoldierLandHigh) g_SoldierLandHigh = s_LandRight[i];
    }
}

/* A walker moves lazily. Between two exact steps (the original's water
 * and dugout checks) his steps are plain: 3 px and the next walking frame
 * each update. So x and frame are kept as of update `base`, with `delay`
 * plain steps after it, and worked out when needed; the update loop runs
 * only when a walker's plain steps run out or someone is dying
 * (g_Island.wait counts the updates in between). With 20 soldiers out
 * this costs nothing most updates, where stepping each one cost ~280
 * T-states a soldier. */
int16_t g_SoldierX;
uint8_t g_SoldierFrame;

/* k mod 5 (SDCC's division is a slow library call). */
static const uint8_t s_Mod5[256] = {0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0};

/* A soldier's x now (walkers: 3 px a plain step since `base`). */
static uint8_t s_Steps;
static int16_t NowX(const IslandSoldier* s)
{
    uint16_t steps;
    if (STATE(s) != ISLAND_SOLDIER_WALKING) { s_Steps = 0; return s->x; }
    s_Steps = (uint8_t)(g_Island.tick - s->base);
    steps = ((uint16_t)s_Steps << 1) + s_Steps;
    return s->dir < 0 ? s->x - (int16_t)steps : s->x + (int16_t)steps;
}

static void Now(const IslandSoldier* s)
{
    uint8_t f;
    g_SoldierX = NowX(s);
    f = s->frame;
    if (s_Steps)
    {
        f += s_Mod5[s_Steps];
        if (f > 4) f -= 5;
    }
    g_SoldierFrame = f;
}

void Soldier_Now(const IslandSoldier* s) WINGS_BANKED
{
    Now(s);
}

/* Bring a walker's x and frame up to the current update. */
static void Catch(IslandSoldier* s)
{
    Now(s);
    s->x = g_SoldierX; s->frame = g_SoldierFrame;
    s->delay -= (uint8_t)(g_Island.tick - s->base);
    s->base = g_Island.tick;
}

void Island_Kill(int16_t x, uint8_t r) WINGS_BANKED
{
    IslandSoldier* s = g_Island.soldier;
    uint8_t i;
    int16_t now;
    /* Soldiers are only ever on an island's land. */
    if (!g_Island.alive || x + r < g_SoldierLandLow || x - r >= g_SoldierLandHigh) return;
    x -= r;
    for (i = 0; i < ISLAND_SOLDIERS; ++i, ++s)
    {
        if (STATE(s) != ISLAND_SOLDIER_WALKING) continue;
        now = NowX(s);
        if ((uint16_t)(now - x) > 2u * r) continue;
        s->x = now;
        Sound_Effect(SOUND_SCREAM, (uint16_t)now);   /* 0x1ac6 */
        s->state += ISLAND_SOLDIER_DYING - ISLAND_SOLDIER_WALKING;
        s->frame = 5; s->delay = 2;
        g_Island.wait = 0;
    }
}

/* The plain steps ahead of a walker at x: steps that end on land and
 * outside every dugout (so the original's checks would change nothing). */
static uint8_t Plain(const IslandSoldier* s)
{
    int16_t x = s->x, room, edge;
    uint8_t island = s->state >> 4, j;
    if (s->dir < 0)
    {
        room = x - s_LandLeft[island];                     /* x - 3k >= left */
        for (j = 0; j < ISLAND_DUGOUTS; ++j)
        {
            edge = (int16_t)s_DugoutX[j] + 15;              /* x - 3k > A + 15 */
            if (edge < x && x - edge - 1 < room) room = x - edge - 1;
        }
    }
    else
    {
        room = s_LandRight[island] - 1 - x;                 /* x + 3k < right */
        for (j = 0; j < ISLAND_DUGOUTS; ++j)
        {
            edge = (int16_t)s_DugoutX[j] - 16;              /* x + 3k < A - 16 */
            if (edge > x && edge - 1 - x < room) room = edge - 1 - x;
        }
    }
    if (room < 3) return 0;
    if (room >= 765) return 254;               /* the update counter wraps at 256 */
    /* room / 3, maybe one short (safe: an early exact step), without
     * SDCC's slow division. */
    return (uint8_t)(((uint16_t)room * 85u) >> 8);
}

/* The original's step (0x3fba, 0x4046): the next walking frame, 3 px,
 * turning round at the water; a walker ending inside a dugout's 32 px mans
 * it (it holds fire 360 updates when it was empty and idle). Returns 1 when
 * he went in. */
static uint8_t Step(IslandSoldier* s)
{
    IslandBuilding* b;
    int8_t step = s->dir < 0 ? -3 : 3;
    uint8_t j;
    if (++s->frame > 4) s->frame = 0;
    if (Mission_Surface((uint16_t)(s->x + step)) == MISSION_SEA) { step = -step; s->dir = -s->dir; }
    s->x += step;
    if (s->x < 0) return 0;
    for (j = 0; j < ISLAND_DUGOUTS; ++j)
    {
        if (!ISLAND_HIT((uint16_t)s->x, s_DugoutX[j])) continue;
        b = &g_Island.dugout[j];
        if (!b->c && !b->garrison) b->c = ISLAND_GUN_FIRE_DELAY;
        ++b->garrison;
        g_Island.gunwork = 1;   /* the fire delay counts down */
        s->state = ISLAND_SOLDIER_FREE;
        --g_Island.out; --g_Island.alive;
        return 1;
    }
    return 0;
}

/* 0x3f5e, 0x5694: no soldier and no AA gun left. The island's bonus
 * (-$7b82 by map and island) is scored; the last island with targets
 * completes the mission (there are no mission ships yet). The ticker says
 * so: Message_Update takes g_Island.message. */
static void Cleared(uint8_t island, uint32_t* score)
{
    g_Island.bonus = s_IslandBonus[island];
    *score += g_Island.bonus;
    g_Island.cleared |= 1 << island;
    if (g_Island.left) --g_Island.left;
    if (g_Island.left) g_Island.message = ISLAND_MESSAGE_CLEARED;
    else { g_Island.message = ISLAND_MESSAGE_MISSION; g_Island.complete = 1; }
}

uint8_t Island_Soldiers(uint32_t* score) WINGS_BANKED
{
    IslandSoldier* s = g_Island.soldier;
    uint8_t i, k, next = 255;
    if (!g_Island.alive) return 0;
    ++g_Island.tick;
    if (g_Island.wait) { --g_Island.wait; return g_Island.alive; }
    for (i = 0; i < ISLAND_SOLDIERS; ++i, ++s)
    {
        switch (STATE(s))
        {
        case ISLAND_SOLDIER_DYING:
            /* 0x3f1e: frames 5..7, 3 updates each, then the corpse (8):
             * +25, and the island's last soldier clears it (step 5). */
            next = 0;
            if ((int8_t)--s->delay >= 0) break;
            s->delay = 2;
            if (++s->frame <= 7) break;
            s->state += ISLAND_SOLDIER_DEAD - ISLAND_SOLDIER_DYING;
            *score += ISLAND_SOLDIER_POINTS;
            ++g_Island.kills;
            --g_Island.alive;
            /* The island's last soldier clears it (0x3f5e). */
            if (!--g_Island.soldiers[s->state >> 4] && !g_Island.guns[s->state >> 4])
                Cleared(s->state >> 4, score);
            break;
        case ISLAND_SOLDIER_WALKING:
            k = (uint8_t)(g_Island.tick - s->base);
            if (k <= s->delay)
            {
                k = s->delay - k;   /* plain steps still ahead */
                if (k < next) next = k;
                break;
            }
            /* Due: the plain steps, then this update's exact step. */
            --g_Island.tick; Catch(s); ++g_Island.tick;
            s->base = g_Island.tick;
            if (Step(s)) break;
            s->delay = Plain(s);
            if (s->delay < next) next = s->delay;
            break;
        }
    }
    g_Island.wait = next;
    return g_Island.alive;
}
#endif
