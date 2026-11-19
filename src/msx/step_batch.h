#pragma once
#include <stdint.h>
#include "banking.h"
/* Steps that only move the plane (docs/frame-budget.md, "Quiet steps"): up
 * to the next step with work (a tick's first, the engine's and the
 * original's tick, a weapon tick while weapons are busy) and never the
 * frame's last (left: the steps before it), as one Flight_StepMany. Not
 * when the plane may touch the surface. Returns the steps taken; 0: take
 * the next one the normal way. For the step loop in world_flight.c, in
 * flight (carrier at deck stage, no crash, engine running). */
uint8_t Step_Batch(uint8_t left, uint8_t weapons) WINGS_BANKED;
/* One original tick of the enemy planes (0xe7d6), the player as they see
 * it, and a torpedo plane's drop. */
void Step_Planes(uint8_t weapons) WINGS_BANKED;
