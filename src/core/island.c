#include "island.h"
#include "smoke.h"
#include "../msx/terrain_patch.h"
#include "../generated/mission_tiles.h"
#include "../generated/mission_island.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_COMBAT)

#ifdef WINGS_P1_FLIGHT  /* smoke.h: the debug ROM keeps the P0 flight */

typedef char IslandFits[(ISLAND_COUNT <= ISLAND_MAX && ISLAND_HUTS <= ISLAND_MAX_HUTS &&
                         ISLAND_DUGOUTS <= ISLAND_MAX_DUGOUTS) ? 1 : -1];

IslandState g_Island;

/* The wrecked hut's columns (0x46dc writes id 5, hutb, into all four): the
 * converter rendered both views of each hut wrecked into variant columns. */
static void Wreck(uint8_t hut, uint8_t wrecked)
{
    uint8_t i;
    for (i = 0; i < s_HutNearCount[hut]; ++i)
        Terrain_Remap(s_HutNearFirst[hut] + i, wrecked ? s_HutNearVariant[hut] + i : s_HutNearFirst[hut] + i);
    for (i = 0; i < s_HutFarCount[hut]; ++i)
        Terrain_Remap(TERRAIN_FAR_COLUMN + s_HutFarFirst[hut] + i,
                      wrecked ? s_HutFarVariant[hut] + i : TERRAIN_FAR_COLUMN + s_HutFarFirst[hut] + i);
}

void Island_Reset(void) WINGS_BANKED
{
    uint8_t i;
    IslandBuilding* b = g_Island.hut;   /* RAM is not cleared at boot */
    for (i = 0; i < ISLAND_MAX_HUTS + ISLAND_MAX_DUGOUTS; ++i, ++b)
    {
        if (i == ISLAND_MAX_HUTS) b = g_Island.dugout;
        if (i < ISLAND_HUTS && b->wrecked) Wreck(i, 0);
        b->garrison = ISLAND_GARRISON;
        b->waiting = b->release = b->wrecked = 0;
        b->c = b->e = 0;
    }
    for (i = 0; i < ISLAND_MAX; ++i) g_Island.soldiers[i] = g_Island.guns[i] = 0;
    for (i = 0; i < ISLAND_MAX_DUGOUTS; ++i)
    {
        g_Island.gun[i].x = i < ISLAND_DUGOUTS ? s_DugoutX[i] : 0;
        g_Island.gun[i].frame = ISLAND_GUN_NONE;
    }
    g_Island.hits = 0;
    for (i = 0; i < ISLAND_HUTS; ++i) g_Island.soldiers[s_HutIsland[i]] += ISLAND_GARRISON;
    for (i = 0; i < ISLAND_DUGOUTS; ++i) g_Island.soldiers[s_DugoutIsland[i]] += ISLAND_GARRISON;
}

/* 0x4b40: the garrison comes out, the first after 60 ticks. */
static void Evacuate(IslandBuilding* b)
{
    b->waiting += b->garrison;
    b->garrison = 0;
    b->release = 60;
}

/* An object anchored at a covers [a - 16, a + 16): the impact column's
 * anchor within columns -1..+2 (0x4ae4). */
#define ISLAND_HIT(x, a) ((uint16_t)((x) - (a) + 16u) < 32u)

uint16_t Island_Bombed(uint16_t x) WINGS_BANKED
{
    uint8_t i;
    IslandBuilding* b;
    for (i = 0; i < ISLAND_HUTS; ++i)
    {
        if (!ISLAND_HIT(x, s_HutX[i])) continue;
        b = &g_Island.hut[i];
        if (b->wrecked) return 0;
        b->wrecked = 1;
        Wreck(i, 1);
        b->c = 50; b->e = 1;
        Evacuate(b);
        return ISLAND_HUT_POINTS;
    }
    for (i = 0; i < ISLAND_DUGOUTS; ++i)
    {
        if (!ISLAND_HIT(x, s_DugoutX[i])) continue;
        b = &g_Island.dugout[i];
        if (!b->garrison) return 0;   /* dugouts cannot be destroyed */
        b->e = 200;
        Evacuate(b);
        return ISLAND_DUGOUT_POINTS;
    }
    return 0;
}

void Island_Impacts(const CombatState* combat, uint32_t* score) WINGS_BANKED
{
    const CombatProjectile* p = &combat->projectile[COMBAT_GUN_COUNT];
    uint16_t points = 0;
    uint8_t i;
    /* A detonation sets life 6; Combat_Advance counts it down every tick. */
    for (i = COMBAT_GUN_COUNT; i < combat->count; ++i, ++p)
        if (p->kind == COMBAT_IMPACT && p->life == 6) points += Island_Bombed(p->x >> 2);
    *score += points;
}

void Island_Tick(void) WINGS_BANKED
{
    IslandBuilding* b = g_Island.hut;
    uint8_t i;
    /* 0x4e18: up to 49 puffs at x + 16, altitude 17, the gap growing by a
     * tick after each. */
    for (i = 0; i < ISLAND_HUTS; ++i, ++b)
        if (b->c > 1 && !--b->e)
        {
            Smoke_Emit(s_HutX[i] + 16, WINGS_FLIGHT_MAX_Y - 17);
            --b->c;
            b->e = 50 - b->c;
        }
}

/* The barrel by altitude row and dx / 40 (0x4db8): DATA -$63e2, read as one
 * byte array at ((altitude >> 5) - 1) * 8 + dx / 40 + 3. The index runs
 * from -17 (below altitude 32, dx -512) to 47 (altitude 186, dx 512); the
 * ends read the neighbouring constant tables, kept as they are. */
#define BARREL_BASE 17
static const uint8_t s_Barrel[65] = {
    2, 2, 3, 3, 3, 1, 2, 3, 3, 0, 1, 2, 3, 0, 1, 2, 3,
    0, 0, 0, 3, 3, 6, 6, 6,  0, 1, 1, 3, 3, 5, 5, 6,  1, 1, 2, 3, 3, 4, 5, 5,
    1, 2, 2, 3, 3, 4, 4, 5,  2, 2, 3, 3, 3, 3, 4, 4,  1, 2, 3, 2, 1, 2, 3, 2};

static uint16_t s_Random = 0x1d2bu;
static uint16_t Random(void)
{
    s_Random ^= s_Random << 7;
    s_Random ^= s_Random >> 9;
    s_Random ^= s_Random << 8;
    return s_Random;
}

/* The update's inputs as statics: SDCC reaches them directly, where
 * arguments and locals go through the IX frame. */
static const FlightState* s_Flight;
static EngineState* s_Engine;
static SortieState* s_Sortie;
static uint16_t s_World;
static int16_t s_Altitude;

/* 0x4f5c: hit-scan fire at the plane, dx from the gun. */
static void Fire(int16_t dx)
{
    uint16_t far = dx < 0 ? -(uint16_t)dx : (uint16_t)dx, near = (uint16_t)s_Altitude;
    if (far > ISLAND_GUN_REACH) return;
    if (far < near) { near = far; far = (uint16_t)s_Altitude; }
    far += near >> 2;
    /* About 20% x (1 - d / 512) per gun and update. */
    if ((Random() & 511) < far || (Random() & 2047) > 409) return;
    ++g_Island.hits;
    Smoke_Hit(s_Flight, s_World);
    Engine_Hit(s_Engine, s_Sortie, (uint8_t)Random());
}

uint8_t Island_Guns(const FlightState* flight, uint16_t world, uint8_t flying,
                    EngineState* engine, SortieState* sortie) WINGS_BANKED
{
    IslandBuilding* b = g_Island.dugout;
    IslandGun* g = g_Island.gun;
    uint8_t i, drawn = 0, frame, row;
    uint16_t distance;
    int16_t dx;
    s_Flight = flight; s_World = world; s_Engine = engine; s_Sortie = sortie;
    s_Altitude = (int16_t)WINGS_FLIGHT_MAX_Y - (int16_t)(flight->y >> 8);
    /* The barrel row for dx = 0 (used up to altitude 186). */
    row = (uint8_t)(((uint8_t)(s_Altitude >> 5) - 1) * 8 + 3 + BARREL_BASE);
    for (i = ISLAND_DUGOUTS; i; --i, ++b, ++g)
    {
        g->frame = ISLAND_GUN_NONE;
        /* 0x3d78: an empty dugout waits for soldiers (step 4); a re-manned
         * one holds its fire for a while. 0x4d50: the gun shows and fires
         * only while the plane flies (the original's mode 0). */
        if (!b->garrison || (b->c && --b->c) || !flying) continue;
        dx = (int16_t)(world - g->x);
        if (s_Altitude > 186)
        {
            /* The distant view: a flash on half the updates, and the gun
             * fires only then. */
            if (!(Random() & 0x8000)) continue;
            frame = ISLAND_GUN_FAR;
        }
        else
        {
            distance = dx < 0 ? -(uint16_t)dx : (uint16_t)dx;
            if (distance > ISLAND_GUN_RANGE) continue;
            /* dx / 40, truncated toward 0 (divs.w) */
            for (frame = 0; distance >= 40; distance -= 40) ++frame;
            frame = s_Barrel[dx < 0 ? row - frame : row + frame];
            /* The muzzle flash on 6 updates in 16. */
            if ((uint8_t)(Random() >> 8) >> 4 <= 5) frame += ISLAND_GUN_FLASH;
        }
        g->frame = frame;
        ++drawn;
        Fire(dx);
    }
    return drawn;
}
#endif
