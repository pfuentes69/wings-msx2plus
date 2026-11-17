#ifndef WINGS_ROCKETS_H
#define WINGS_ROCKETS_H
#include "combat.h"

/* Rockets (docs/rockets.md): banked apart from the rest of combat. */
/* Launch one from the plane at (x, y) with velocity (vx, vy) (Q8 per 150 Hz
 * step) and state->path / speed; 0 when all slots are in flight. */
uint8_t Rockets_Launch(CombatState* state, uint16_t x, uint16_t y, int16_t vx, int16_t vy, uint8_t left) WINGS_BANKED;
/* Release the torpedo (docs/torpedo.md); 0 while one is in the water. */
uint8_t Torpedo_Launch(CombatState* state, uint16_t x, uint16_t y, int16_t vx, int16_t vy, uint8_t left) WINGS_BANKED;
/* 0x1ae2: the torpedo, falling or running, within r px of x explodes
 * without effect. */
void Torpedo_Kill(CombatState* state, int16_t x, uint8_t r) WINGS_BANKED;
/* One original 12.5 Hz tick of every rocket and the torpedo, the plane at (x, y). */
void Rockets_Step(CombatState* state, uint16_t x, uint16_t y, uint8_t left) WINGS_BANKED;
#endif
