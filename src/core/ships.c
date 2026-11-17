#include "ships.h"
#include "combat.h"
#include "flight.h"
#include "smoke.h"
#include "mission_ships.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_SHIPS)

#if SHIP_GUNS > SHIP_MAX_GUNS
#error The map has more ship guns than ShipsState holds
#endif

ShipsState g_Ships;

void Ships_Reset(void) WINGS_BANKED
{
    uint8_t i;
    for (i = 0; i < SHIP_MAX_GUNS; ++i) g_Ships.down[i] = g_Ships.puffs[i] = g_Ships.timer[i] = 0;
    g_Ships.smoking = 0; g_Ships.guns_down = 0;
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
