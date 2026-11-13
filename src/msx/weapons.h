#pragma once
#include "core.h"
#include "banking.h"
#include "../core/combat.h"
void Weapons_Init(void) WINGS_BANKED;
void Weapons_Restore(u8 page, u8 cleared) WINGS_BANKED;
void Weapons_Draw(u8 page, u16 camera, u8 far, u8 heave, const CombatState* state) WINGS_BANKED;

u8 Weapons_PendingRestore(void) WINGS_BANKED;
