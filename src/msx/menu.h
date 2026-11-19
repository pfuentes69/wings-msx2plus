#pragma once
#include "core.h"
#include "banking.h"
#include "../core/game.h"
void Menu_Draw(u8 page, const GameState* game) WINGS_BANKED;
/* The briefing's objectives: the map's islands with targets and ships to
 * sink (world_flight.c sets them at boot from the mission's set-up). */
extern u8 g_BriefIslands, g_BriefShips;
