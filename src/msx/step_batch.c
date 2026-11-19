#include "step_batch.h"
#include "../core/world.h"
#include "../core/combat.h"
#include "../core/engine.h"
#include "../core/planes.h"
#include "../core/ships.h"
#include "../core/carrier.h"
#include "../core/game.h"
#include "../core/rockets.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_FLIGHT)

/* The step loop's state (world_flight.c). */
extern WorldState s_World;
extern uint8_t s_EngineSteps, s_AnimTick, s_ContactBottom, s_ContactSurface;
extern CombatState g_Combat;
extern uint8_t s_CrashSteps;
extern CarrierState g_Carrier;
extern EngineState g_Engine;
extern GameState g_Game;

/* The step loop's contact gate: at y the plane may touch the surface (the
 * exact, banked check then runs). */
static uint8_t MayTouch(FlightVertical y)
{
    int16_t base = (int16_t)WINGS_FLIGHT_MAX_Y - (int16_t)(y >> 8) - s_ContactBottom;
    return base < (int16_t)s_ContactSurface + 1 || base <= 0;
}

uint8_t Step_Batch(uint8_t left, uint8_t weapons) WINGS_BANKED
{
    FlightState* f = &s_World.flight;
    uint8_t c = f->step, n;
    if (!c) return 0;
    n = FLIGHT_TICK_STEPS - c;
    if (n > left) n = left;
    if (n > (uint8_t)(ENGINE_TICK_STEPS - 1 - s_EngineSteps)) n = ENGINE_TICK_STEPS - 1 - s_EngineSteps;
    if (n > (uint8_t)(11 - s_AnimTick)) n = 11 - s_AnimTick;
    if (Combat_Required(&g_Combat, weapons) && n > (uint8_t)(5 - g_Combat.phase)) n = 5 - g_Combat.phase;
    if (n < 2) return 0;
    /* Each step moves at most |vy| + 1 Q8 units, and the gate only opens
     * lower down: if the lowest the run could reach is clear, all of it is. */
    if (!FLIGHT_ON_DECK(f))
    {
        uint16_t v = (uint16_t)(f->vy < 0 ? -f->vy : f->vy) + 1, reach = 0;
        uint8_t k = n;
        do reach += v; while (--k);
        if (MayTouch(f->y + reach)) return 0;
    }
    Flight_StepMany(f, &s_World.x, n);
    s_EngineSteps += n; s_AnimTick += n;
    /* The weapon clock (Combat_Tick) runs on; with nothing to advance, its
     * ticks do nothing. */
    c = g_Combat.phase + n;
    while (c >= 6) c -= 6;
    g_Combat.phase = c;
    return n;
}

/* One original tick of the enemy planes, with the player as they see it
 * (from world_flight.c's step loop; banked for room). */
void Step_Planes(uint8_t weapons) WINGS_BANKED
{
    static PlanesPlayer player;
    player.x = (int16_t)(s_World.x >> 8);
    player.alt = (int16_t)(WINGS_FLIGHT_MAX_Y - (s_World.flight.y >> 8));
    player.facing = s_World.flight.facing_left ? -1 : 1;
    player.mode = s_CrashSteps ? PLANES_PLAYER_CRASHED :
                  s_World.flight.mode == FLIGHT_DEAD ? PLANES_PLAYER_ENGINE_OUT :
                  FLIGHT_ON_DECK(&s_World.flight) || g_Carrier.stage != CARRIER_DECK ? PLANES_PLAYER_DECK :
                  PLANES_PLAYER_FLYING;
    player.turn = s_World.flight.turn;
    player.speed = s_World.flight.speed;
    player.climb = s_World.flight.climb;
    { int16_t vx = s_World.flight.vx < 0 ? -s_World.flight.vx : s_World.flight.vx;
      player.hstep = (int16_t)(((int32_t)vx * 12) >> 8); }   /* Q8 a step, 12 steps a tick */
    player.engine = &g_Engine; player.sortie = &g_Game.sortie;
    /* The fire flag (0xb5b0): the gun held in flight, not turning. */
    player.gun = (weapons & COMBAT_FIRE) && player.mode == PLANES_PLAYER_FLYING && !player.turn;
    Planes_Tick(&player, weapons != 0, g_Ships.hull[SHIP_MAX] != 0, &g_Game.progress.score, &g_Game.progress.kills);
    if (g_Planes.drop) Torpedo_Drop(&g_Combat, g_Planes.drop_x, g_Planes.drop_alt, g_Planes.drop_speed, g_Planes.drop_facing);
}
