#pragma once
#include "core.h"
#include "banking.h"
#include "../core/game.h"
void Menu_Draw(u8 page, const GameState* game) WINGS_BANKED;
/* The briefing's objectives: the map's islands with targets and ships to
 * sink (world_flight.c sets them at boot from the mission's set-up). */
extern u8 g_BriefIslands, g_BriefShips;
/* A key newly down while a name is typed (Game_Type's codes), or 0;
 * reset: what is held now counts as old. */
u8 Menu_Key(u8 reset) WINGS_BANKED;
