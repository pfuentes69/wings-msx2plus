#pragma once
#include "core.h"
#include "../core/combat.h"
void Weapons_Init(void);
void Weapons_Restore(u8 page, u8 cleared);
void Weapons_Draw(u8 page, u16 camera, u8 far, u8 heave, const CombatState* state);

u8 Weapons_PendingRestore(void);
