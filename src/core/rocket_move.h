#ifndef WINGS_ROCKET_MOVE_H
#define WINGS_ROCKET_MOVE_H
#include "combat.h"

/* One original tick of a rocket's motion (0x0aa6), hand-written Z80 on the
 * MSX: before ignition the drift, lit the acceleration; then x += vx and
 * the altitude += the whole pixels of vy + ay. Returns 1, having moved
 * nothing, on the tick it ignites (the caller aims it, then calls again).
 * In segment 29 with rockets.c, which alone calls it (a plain call). */
extern uint8_t g_RocketLeft;   /* the plane faces left this tick */
uint8_t Rocket_Move(CombatRocket* r);
/* n / d for a quotient below 65536 (the caller checks n's whole word < d):
 * 68000 divu.w, in Z80 (SDCC's long division is a 32-bit loop). */
uint16_t Rocket_Divide(const CombatFixed* n, uint16_t d);
#endif
