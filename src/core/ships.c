#include "ships.h"
#include "combat.h"
#include "flight.h"
#include "smoke.h"
#include "island.h"
#include "mission.h"
#include "barrel.h"
#include "mission_ships.h"
#include "xorshift.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_SHIPS)

#if SHIP_GUNS > SHIP_MAX_GUNS
#error The map has more ship guns than ShipsState holds
#endif

ShipsState g_Ships;

#if SHIP_GUNS
static uint16_t s_Random = 0x5a3cu;
static uint16_t Random(void)
{
    return Xorshift(&s_Random);
}
#endif

void Ships_Reset(void) WINGS_BANKED
{
    uint8_t i;
    for (i = 0; i < SHIP_MAX_GUNS; ++i) g_Ships.down[i] = g_Ships.puffs[i] = g_Ships.timer[i] = 0;
    for (i = 0; i < SHIP_SPLASHES; ++i) g_Ships.splash[i].life = 0;
    g_Ships.smoking = g_Ships.shown_count = g_Ships.splashes = 0;
    g_Ships.guns_down = g_Ships.hits = 0;
    g_Ships.nearest = 65535u;
    g_Ships.present = SHIP_COUNT != 0;
}

uint8_t Ships_Find(uint16_t x) WINGS_BANKED
{
#if SHIP_COUNT
    uint8_t i;
    for (i = 0; i < SHIP_COUNT; ++i)
        if (x >= s_ShipLeft[i] && x <= s_ShipRight[i]) return i;
#endif
    if (SHIP_CARRIER_RIGHT && x >= SHIP_CARRIER_LEFT && x <= SHIP_CARRIER_RIGHT) return SHIP_CARRIER;
    return SHIP_NONE;
}

uint8_t Ships_Deck(uint8_t ship) WINGS_BANKED
{
    return ship == SHIP_CARRIER || ship == SHIP_NONE ? 0 : s_ShipDeck[ship];
}

uint8_t Ships_Rocket(uint16_t x, uint32_t* score) WINGS_BANKED
{
    uint8_t ship = Ships_Find(x);
#if SHIP_COUNT
    uint8_t i, end;
    int16_t d;
#endif
    if (ship == SHIP_NONE) return 0;
    if (ship == SHIP_CARRIER) return COMBAT_SKY_WHITE;   /* no guns */
#if SHIP_COUNT
    /* 0x49dc: the first live gun in list order within 16 px. */
    end = s_ShipFirstGun[ship + 1];
    for (i = s_ShipFirstGun[ship]; i < end; ++i)
    {
        if (g_Ships.down[i]) continue;
        d = (int16_t)(x - s_ShipGunX[i]);
        if (d < 0) d = -d;
        if (d >= 16) continue;
        g_Ships.down[i] = 1;
        g_Ships.puffs[i] = SHIP_GUN_SMOKE; g_Ships.timer[i] = 1;
        ++g_Ships.smoking; ++g_Ships.guns_down;
        *score += SHIP_GUN_POINTS;
        return COMBAT_SKY_RED;
    }
#else
    (void)score;
#endif
    return COMBAT_SKY_WHITE;
}

uint16_t Ships_Aim(int16_t a, int16_t b) WINGS_BANKED
{
#if SHIP_GUNS
    uint8_t i;
    int16_t x;
    if (a > b) { x = a; a = b; b = x; }
    /* Every enemy ship has a bonus, and none is removed yet (sinking comes
     * later), so every gun of every ship counts. */
    for (i = 0; i < SHIP_GUNS; ++i)
    {
        x = (int16_t)s_ShipGunX[i];
        if (x >= a && x <= b) return (uint16_t)x;
    }
#else
    (void)a; (void)b;
#endif
    return 0;
}

void Ships_Tick(uint8_t flying) WINGS_BANKED
{
#if SHIP_GUNS
    uint8_t i, ship = 0;
    if (!g_Ships.smoking || !flying) return;
    /* Like an AA gun (0x4c3e): when the timer runs out a puff goes, and
     * the next comes a tick later each time (50 - puffs left), at the
     * deck. */
    for (i = 0; i < SHIP_GUNS; ++i)
    {
        while (i >= s_ShipFirstGun[ship + 1]) ++ship;
        if (g_Ships.puffs[i] <= 1 || --g_Ships.timer[i]) continue;
        if (--g_Ships.puffs[i] == 1) --g_Ships.smoking;
        g_Ships.timer[i] = SHIP_GUN_SMOKE - g_Ships.puffs[i];
        Smoke_Emit(s_ShipGunX[i], WINGS_FLIGHT_MAX_Y - s_ShipDeck[ship] - s_ShipGunRise[i]);
    }
#else
    (void)flying;
#endif
}

#if SHIP_GUNS
/* The update's inputs as statics: SDCC reaches them directly. */
static const FlightState* s_Flight;
static EngineState* s_Engine;
static SortieState* s_Sortie;
static uint16_t s_World;
static int16_t s_Altitude;

/* 0x4f5c, as the dugout guns': hit-scan fire at the plane, dx from the gun.
 * It also notes the nearest gun firing, for the sound (0x38ea). */
static void Fire(uint16_t distance)
{
    uint16_t far = distance, near = (uint16_t)s_Altitude;
    if (far > ISLAND_GUN_REACH) return;
    if (far < g_Ships.nearest) g_Ships.nearest = far;
    if (far < near) { near = far; far = (uint16_t)s_Altitude; }
    far += near >> 2;
    if ((Random() & 511) < far || (Random() & 2047) > 409) return;
    ++g_Ships.hits;
    Smoke_Hit(s_Flight, s_World);
    Engine_Hit(s_Engine, s_Sortie, (uint8_t)Random());
}

/* 0x52b0: a splash at x, a ricochet on land. */
static void Splash(int16_t x)
{
    ShipSplash* s = g_Ships.splash;
    uint8_t i;
    for (i = 0; i < SHIP_SPLASHES; ++i, ++s)
    {
        if (s->life) continue;
        s->x = x;
        s->land = Mission_Surface((uint16_t)x) == MISSION_ISLAND;
        s->life = s->land ? 4 : SHIP_SPLASH_LIFE;
        ++g_Ships.splashes;
        return;
    }
}

/* d / 40 by d / 8 (d <= 512): floor(floor(d / 8) / 5) is floor(d / 40). */
static const uint8_t s_Div40[65] = {
    0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4,
    5, 5, 5, 5, 5, 6, 6, 6, 6, 6, 7, 7, 7, 7, 7, 8, 8, 8, 8, 8, 9, 9, 9, 9, 9,
    10, 10, 10, 10, 10, 11, 11, 11, 11, 11, 12, 12, 12, 12, 12};

/* One live gun this update (the body of 0x4c3e's loop). Its state and the
 * loop's are statics: SDCC reaches them directly, where locals go through
 * the IX frame (the loop cost ~10 ms an update with 8 guns in range). */
static uint8_t s_Far, s_Row, s_Deck;
static uint16_t s_Distance;
static ShipGunShown* s_Shown;
static void Gun(uint8_t i)
{
    uint8_t frame;
    int16_t dx = (int16_t)(s_World - s_ShipGunX[i]);
    s_Distance = dx < 0 ? -(uint16_t)dx : (uint16_t)dx;
    /* 0x4efc: a shell splash near a low plane, likelier nearer:
     * (1 - d / 512) x 6 / 16 an update. */
    if (s_Altitude <= 200 && (Random() & 511) > s_Distance && (Random() & 15) < 6)
        Splash((int16_t)s_World + (int16_t)(Random() & 63) - 32);
    if (s_Far)
    {
        /* expl on half the updates; the gun fires on all of them. */
        frame = (Random() & 0x8000) ? ISLAND_GUN_NONE : ISLAND_GUN_FAR;
    }
    else
    {
        if (s_Distance > ISLAND_GUN_RANGE) return;
        frame = s_Div40[(uint8_t)(s_Distance >> 3)];   /* dx / 40, toward 0 */
        frame = s_Barrel[dx < 0 ? s_Row - frame : s_Row + frame];
        if (Random() & 0x8000) frame += ISLAND_GUN_FLASH;   /* 0x4cbe: 1 in 2 */
    }
    if (frame != ISLAND_GUN_NONE && g_Ships.shown_count < SHIP_SHOWN)
    {
        /* Drawn at the deck (+e) + the gun's rise + 13 (0x4c9a); the hull
         * is baked into the scenery without the bob. */
        s_Shown->x = s_ShipGunX[i];
        s_Shown->altitude = s_Deck + s_ShipGunRise[i] + SHIP_GUN_RISE;
        s_Shown->frame = frame;
        ++s_Shown; ++g_Ships.shown_count;
    }
    Fire(s_Distance);
}
#endif

uint8_t Ships_Guns(const FlightState* flight, uint16_t world, uint8_t flying,
                   EngineState* engine, SortieState* sortie) WINGS_BANKED
{
#if SHIP_GUNS
    ShipSplash* splash = g_Ships.splash;
    uint8_t ship, i, end;
    int16_t reach;
    /* Last update's splashes age a frame (0x52f8 counts down as it draws). */
    if (g_Ships.splashes)
        for (i = 0; i < SHIP_SPLASHES; ++i, ++splash)
            if (splash->life && !--splash->life) --g_Ships.splashes;
    g_Ships.shown_count = 0;
    g_Ships.nearest = 65535u;
    if (!flying) return g_Ships.splashes;   /* 0x4c3e: only while the plane flies */
    s_Altitude = (int16_t)WINGS_FLIGHT_MAX_Y - (int16_t)(flight->y >> 8);
    s_Flight = flight; s_World = world; s_Engine = engine; s_Sortie = sortie;
    s_Far = s_Altitude > 186;
    /* In the distant view a gun flashes wherever it is (0x4db8 gives frame 0
     * at any distance): look as far as the screen. Close up, 512 px. */
    reach = s_Far ? 1100 : ISLAND_GUN_RANGE;
    s_Row = (uint8_t)(((uint8_t)(s_Altitude >> 5) - 1) * 8 + 3 + BARREL_BASE);
    s_Shown = g_Ships.shown;
    for (ship = 0; ship < SHIP_COUNT; ++ship)
    {
        i = s_ShipFirstGun[ship]; end = s_ShipFirstGun[ship + 1];
        /* A ship's guns lie in x order: test its span first. */
        if ((int16_t)(world - s_ShipGunX[i]) < -reach || (int16_t)(world - s_ShipGunX[end - 1]) > reach)
            continue;
        s_Deck = s_ShipDeck[ship];
        for (; i < end; ++i)
            if (!g_Ships.down[i]) Gun(i);
    }
    return g_Ships.shown_count + g_Ships.splashes;
#else
    (void)flight; (void)world; (void)flying; (void)engine; (void)sortie;
    return 0;
#endif
}
