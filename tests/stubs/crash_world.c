/* The world around src/core/crash.c for host tests (tests/test_crash.py,
 * tests/test_flight_model.py): the globals the MSX build defines elsewhere,
 * and the ship, island and smoke calls recorded. */
#include "../../src/core/combat.h"
#include "../../src/core/game.h"
#include "../../src/core/ships.h"
#include "../../src/core/island.h"
#include "../../src/core/smoke.h"
#define LOG 128
CombatState g_Combat;
GameState g_Game;
uint8_t g_LastContact, g_ShipHeave;
uint8_t g_Splashes, g_Kills, g_Bombed, g_Rockets, g_Puffs;
int16_t g_SplashX[LOG], g_KillX[LOG], g_BombedX[LOG], g_RocketX[LOG];
uint8_t g_KillR[LOG];
uint16_t g_PuffX[LOG], g_PuffY[LOG];
uint8_t g_PuffStage[LOG];
uint16_t g_BombPoints;        /* what Island_Bombed returns */
uint8_t Ships_Find(uint16_t x)
{
    return x >= FLIGHT_DECK_LEFT && x <= FLIGHT_DECK_RIGHT ? SHIP_CARRIER : SHIP_NONE;
}
uint8_t Ships_Deck(uint8_t ship) { (void)ship; return 20; }
uint8_t Ships_Rocket(uint16_t x, uint32_t* score)
{
    (void)score;
    if (g_Rockets < LOG) g_RocketX[g_Rockets++] = (int16_t)x;
    return COMBAT_SKY_WHITE;
}
void Ships_AddSplash(int16_t x) { if (g_Splashes < LOG) g_SplashX[g_Splashes++] = x; }
uint16_t Island_Bombed(uint16_t x)
{
    if (g_Bombed < LOG) g_BombedX[g_Bombed++] = (int16_t)x;
    return g_BombPoints;
}
void Island_Kill(int16_t x, uint8_t r)
{
    if (g_Kills < LOG) { g_KillX[g_Kills] = x; g_KillR[g_Kills++] = r; }
}
void Smoke_Puff(uint16_t x, uint16_t y, uint8_t stage)
{
    if (g_Puffs < LOG) { g_PuffX[g_Puffs] = x; g_PuffY[g_Puffs] = y; g_PuffStage[g_Puffs++] = stage; }
}
