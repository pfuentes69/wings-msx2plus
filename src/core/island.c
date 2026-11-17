#include "island.h"
#include "smoke.h"
#include "../msx/terrain_patch.h"
#include "mission_tiles.h"
#include "mission_island.h"
#include "mission.h"
#include "ships.h"
#include "rockets.h"
#include "xorshift.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_COMBAT)

#ifdef WINGS_P1_FLIGHT  /* smoke.h: the debug ROM keeps the P0 flight */

#define ISLAND_SOLDIERS (ISLAND_GARRISON * (ISLAND_HUTS + ISLAND_DUGOUTS))
typedef char IslandFits[(ISLAND_COUNT <= ISLAND_MAX && ISLAND_HUTS <= ISLAND_MAX_HUTS &&
                         ISLAND_DUGOUTS <= ISLAND_MAX_DUGOUTS && ISLAND_SOLDIERS <= ISLAND_MAX_SOLDIERS &&
                         ISLAND_COUNT <= 16) ? 1 : -1];
#define STATE(s) ((s)->state & 7)   /* bit 3: PENDING, bits 4..7: island */

IslandState g_Island;
/* Buildings still releasing soldiers and wrecked huts still smoking:
 * with neither, Island_Tick has nothing to do. */
static uint8_t s_Releasing, s_Smoking;
/* Barrels shown last update; all dugouts' anchors (Island_Reset). */
static uint8_t s_GunsShown;
static uint16_t s_GunsLow, s_GunsHigh;


static uint16_t s_Random = 0x1d2bu;
static uint16_t Random(void)
{
    return Xorshift(&s_Random);
}

/* The soldiers' own generator (directions, release gaps), so that they do
 * not change the ground fire's hits (the original shares one). */
static uint16_t s_Muster = 0x6b35u;
static uint16_t Muster(void)
{
    return Xorshift(&s_Muster);
}


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
    g_Island.hits = g_Island.kills = 0;
    g_Island.gunwork = 0;
    s_GunsShown = 1;   /* clear the barrels on the next update */
    s_GunsLow = 65535u; s_GunsHigh = 0;
    for (i = 0; i < ISLAND_DUGOUTS; ++i)
    {
        if (s_DugoutX[i] < s_GunsLow) s_GunsLow = s_DugoutX[i];
        if (s_DugoutX[i] > s_GunsHigh) s_GunsHigh = s_DugoutX[i];
    }
    g_Island.out = g_Island.alive = g_Island.tick = g_Island.wait = 0;
    g_Island.cleared = g_Island.message = g_Island.complete = 0;
    g_Island.bonus = 0;
    /* 0x2de8: islands with at least one hut, dugout or AA gun. */

    s_Releasing = s_Smoking = 0;
    for (i = 0; i < ISLAND_MAX_SOLDIERS; ++i) g_Island.soldier[i].state = ISLAND_SOLDIER_FREE;
    Soldiers_Reset();
    for (i = 0; i < ISLAND_HUTS; ++i) g_Island.soldiers[s_HutIsland[i]] += ISLAND_GARRISON;
    for (i = 0; i < ISLAND_DUGOUTS; ++i) g_Island.soldiers[s_DugoutIsland[i]] += ISLAND_GARRISON;
    g_Island.left = 0;
    for (i = 0; i < ISLAND_COUNT; ++i) g_Island.left += g_Island.soldiers[i] || g_Island.guns[i];
}

/* 0x4b40: the garrison comes out, the first after 60 ticks. */
static void Evacuate(IslandBuilding* b)
{
    b->waiting += b->garrison;
    b->garrison = 0;
    if (!b->release) ++s_Releasing;
    b->release = 60;
    g_Island.gunwork = 1;   /* an emptied dugout calls for soldiers */
}


/* 0x1e82: a soldier comes out of a building into the first free slot (none
 * free: none comes out). Its direction byte is random when dir is 0; it
 * leaves by the left exit when negative, else the right one, (dir & 7) * 4
 * px further on, on frame dir & 3. Huts have both exits at the anchor;
 * dugouts at A - 44 and A + 16 (record +4/+6). */
static void Release(int16_t left, int16_t right, uint8_t island, int8_t dir)
{
    IslandSoldier* s = g_Island.soldier;
    uint8_t i;
    for (i = 0; i < ISLAND_SOLDIERS && STATE(s); ++i, ++s) {}
    if (i == ISLAND_SOLDIERS) return;
    if (!dir) dir = (int8_t)Muster();
    s->state = ISLAND_SOLDIER_WALKING | (island << 4);
    ++g_Island.out; ++g_Island.alive;
    s->dir = dir;
    s->frame = dir & 3;
    s->delay = 0;                 /* no plain steps counted: */
    s->base = g_Island.tick;      /* he takes an exact step next update */
    g_Island.wait = 0;
    s->x = (dir < 0 ? left : right) + (dir & 7) * 4;
}

/* 0x1de4: the next waiting soldier comes out when the release timer runs
 * out; the next one waits (rand >> 4) & 31 ticks, or 3. */
static uint8_t Due(IslandBuilding* b)
{
    uint8_t gap;
    if (!b->release || --b->release) return 0;
    if (--b->waiting)
    {
        gap = (uint8_t)(Muster() >> 4) & 31;
        b->release = gap ? gap : 3;
    }
    else --s_Releasing;
    return 1;
}

/* 0x4fee: an empty dugout takes a soldier from the nearest hut on its
 * island that still holds 2 or more, measured from the dugout's left exit
 * (ties: the later hut). He walks toward the dugout. */
static void Reinforce(uint8_t d)
{
    int16_t exit = (int16_t)s_DugoutX[d] - 44, dx;
    uint16_t nearest = 10000, distance;
    uint8_t i, best = 255;
    for (i = 0; i < ISLAND_HUTS; ++i)
    {
        if (s_HutIsland[i] != s_DugoutIsland[d] || g_Island.hut[i].garrison < 2) continue;
        dx = (int16_t)s_HutX[i] - exit;
        distance = dx < 0 ? -(uint16_t)dx : (uint16_t)dx;
        if (!distance || distance > nearest) continue;
        nearest = distance; best = i;
    }
    if (best == 255) return;
    --g_Island.hut[best].garrison;
    dx = (int16_t)s_HutX[best] - exit;
    Release((int16_t)s_HutX[best], (int16_t)s_HutX[best], s_HutIsland[best], dx < 0 ? 1 : -1);
}


/* 1 when the last Island_Bombed wrecked a hut or struck a dugout: a rocket
 * then flashes red (0x4744, 0x4812). */
static uint8_t s_Struck;

uint16_t Island_Bombed(uint16_t x) WINGS_BANKED
{
    uint8_t i;
    IslandBuilding* b;
    s_Struck = 0;
    for (i = 0; i < ISLAND_HUTS; ++i)
    {
        if (!ISLAND_HIT(x, s_HutX[i])) continue;
        b = &g_Island.hut[i];
        if (b->wrecked) return 0;   /* now hutb, id 5: no target */
        s_Struck = 1;
        b->wrecked = 1;
        Wreck(i, 1);
        b->c = 50; b->e = 1;
        ++s_Smoking;
        Evacuate(b);
        return ISLAND_HUT_POINTS;
    }
    for (i = 0; i < ISLAND_DUGOUTS; ++i)
    {
        if (!ISLAND_HIT(x, s_DugoutX[i])) continue;
        b = &g_Island.dugout[i];
        s_Struck = 1;
        if (!b->garrison) return 0;   /* dugouts cannot be destroyed */
        b->e = 200;
        Evacuate(b);
        return ISLAND_DUGOUT_POINTS;
    }
    return 0;
}

/* 0x46dc: a rocket impact flashes the background white, red when it hit
 * something. */
static void Flash(CombatState* combat, uint8_t color)
{
    if (!color) return;
    combat->sky_flash = 5;
    combat->sky_color = color;
}

void Island_Impacts(CombatState* combat, uint32_t* score) WINGS_BANKED
{
    const CombatProjectile* p = combat->projectile;
    uint16_t points = 0, x;
    uint8_t i, source;
    /* World x is signed: past the map's ends it matches no target. A
     * detonation sets life 6; Combat_Advance counts it down every tick.
     * Bombs, rockets and torpedoes damage buildings; their bursts (0x0cc0)
     * and cannon strikes (0x19f6, slots 0..1) kill walking soldiers within
     * 16 px and torpedoes in [x - 48, x + 16] (0x1a8c). */
    for (i = 0; i < combat->count; ++i, ++p)
    {
        if (p->life != 6 || p->kind < COMBAT_IMPACT) continue;
        source = (uint8_t)p->vx;
        if (source == COMBAT_TORPEDO_DUD) continue;   /* destroyed: no effect */
        x = (uint16_t)Combat_WorldX(combat, p->x);
        s_Struck = 0;
        if (i >= COMBAT_GUN_COUNT && p->kind == COMBAT_IMPACT) points += Island_Bombed(x);
        if (source == COMBAT_ROCKET_BURST || source == COMBAT_TORPEDO_BURST)
        {
            /* On land a rocket's impact flashes (a torpedo's does not);
             * over the sea or a deck only near a hull, where either may
             * destroy a ship's gun (0x4986, 0x49dc). */
            if (Mission_Surface(x) == MISSION_ISLAND)
            {
                if (source == COMBAT_ROCKET_BURST) Flash(combat, s_Struck ? COMBAT_SKY_RED : COMBAT_SKY_WHITE);
            }
            else Flash(combat, Ships_Rocket(x, score));
        }
        else if (source == COMBAT_TORPEDO_HIT)
        {
            /* A running torpedo: a hull hit (0x49a6), or land as a bomb.
             * It calls no 0x1a8c (0x0d7c). */
            if (p->kind == COMBAT_SPLASH) Flash(combat, Ships_Torpedo(x));
            continue;
        }
        Island_Kill((int16_t)x, 16);
        if (combat->torpedo.live) Torpedo_Kill(combat, (int16_t)x - 16, 32);
    }
    *score += points;
}

void Island_Tick(void) WINGS_BANKED
{
    IslandBuilding* b = g_Island.dugout;
    uint8_t i;
    int8_t dir;
    if (!s_Releasing && !s_Smoking) return;
    /* 0x1de4: garrisons come out, dugouts first. A dugout's soldiers walk
     * inland: right from the island's leftmost dugout, left from its
     * rightmost (1 in 32 the other way), random from any other. */
    for (i = 0; i < ISLAND_DUGOUTS; ++i, ++b)
    {
        if (!Due(b)) continue;
        dir = (s_DugoutSide[i] & 1) ? 1 : (s_DugoutSide[i] & 2) ? -1 : 0;
        if (!(Muster() & 31)) dir = -dir;
        Release((int16_t)s_DugoutX[i] - 44, (int16_t)s_DugoutX[i] + 16, s_DugoutIsland[i], dir);
    }
    b = g_Island.hut;
    for (i = 0; i < ISLAND_HUTS; ++i, ++b)
        if (Due(b)) Release((int16_t)s_HutX[i], (int16_t)s_HutX[i], s_HutIsland[i], 0);
    b = g_Island.hut;
    /* 0x4e18: up to 49 puffs at x + 16, altitude 17, the gap growing by a
     * tick after each. */
    for (i = 0; i < ISLAND_HUTS; ++i, ++b)
        if (b->c > 1 && !--b->e)
        {
            Smoke_Emit(s_HutX[i] + 16, WINGS_FLIGHT_MAX_Y - 17);
            if (--b->c == 1) --s_Smoking;
            b->e = 50 - b->c;
        }
}

#include "barrel.h"

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
    s_Altitude = (int16_t)WINGS_FLIGHT_MAX_Y - (int16_t)(flight->y >> 8);
    /* Nothing to do (most updates): no barrel shown, no dugout empty or
     * holding fire, and the plane not flying or out of every gun's reach
     * (the distant view's flash: 1100 px, beyond its screen). */
    if (!s_GunsShown && !g_Island.gunwork &&
        (!flying || (int16_t)(world - s_GunsLow) < -(s_Altitude > 186 ? 1100 : ISLAND_GUN_RANGE) ||
                    (int16_t)(world - s_GunsHigh) > (s_Altitude > 186 ? 1100 : ISLAND_GUN_RANGE)))
        return 0;
    s_Flight = flight; s_World = world; s_Engine = engine; s_Sortie = sortie;
    g_Island.gunwork = 0;
    /* The barrel row for dx = 0 (used up to altitude 186). */
    row = (uint8_t)(((uint8_t)(s_Altitude >> 5) - 1) * 8 + 3 + BARREL_BASE);
    for (i = ISLAND_DUGOUTS; i; --i, ++b, ++g)
    {
        g->frame = ISLAND_GUN_NONE;
        /* 0x3d78: an empty dugout waits for soldiers (step 4); a re-manned
         * one holds its fire for a while. 0x4d50: the gun shows and fires
         * only while the plane flies (the original's mode 0). */
        if (!b->garrison || b->c) g_Island.gunwork = 1;
        if (!b->garrison)
        {
            /* 0x3d8a: an empty dugout sends for a soldier every 200 updates. */
            if ((int16_t)--b->e <= 0)
            {
                b->e = ISLAND_REINFORCE_TICKS;
                Reinforce(ISLAND_DUGOUTS - i);
            }
            continue;
        }
        if ((b->c && --b->c) || !flying) continue;
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
    s_GunsShown = drawn;
    return drawn;
}
#endif
