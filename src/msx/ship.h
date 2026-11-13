#pragma once
#include "core.h"
extern u8 g_ShipHeave, g_ShipFrame;
void Ship_Load(void);
void Ship_Advance(u8 ticks);
void Ship_Draw(u8 page, u16 camera);

void Ship_DrawCrew(u8 page, u16 camera);
