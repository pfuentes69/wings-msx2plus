#include "island.h"
#include "smoke.h"
#include "../msx/terrain_patch.h"
#include "../generated/mission_tiles.h"
#include "../generated/mission_island.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_ISLAND)

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
#endif
