#ifndef WINGS_ROCKETS_H
#define WINGS_ROCKETS_H
#include "combat.h"

/* Rockets (docs/rockets.md): banked apart from the rest of combat. */
/* Launch one from the plane at (x, y) with velocity (vx, vy) (Q8 per 150 Hz
 * step) and state->path / speed; 0 when all slots are in flight. */
uint8_t Rockets_Launch(CombatState* state, uint16_t x, uint16_t y, int16_t vx, int16_t vy, uint8_t left) WINGS_BANKED;
/* One original 12.5 Hz tick of every rocket, the plane at (x, y). */
void Rockets_Step(CombatState* state, uint16_t x, uint16_t y, uint8_t left) WINGS_BANKED;
#endif
