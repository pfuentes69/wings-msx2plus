#pragma once
#include "core.h"
#include "banking.h"
extern u8 g_ShipHeave, g_ShipFrame;
void Ship_Load(void) WINGS_BANKED;
void Ship_Advance(u8 ticks) WINGS_BANKED;
void Ship_Draw(u8 page, u16 camera) WINGS_BANKED;

void Ship_DrawCrew(u8 page, u16 camera, u8 cleared) WINGS_BANKED;
