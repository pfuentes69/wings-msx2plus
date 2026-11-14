#ifndef WINGS_FLIGHT_MODEL_H
#define WINGS_FLIGHT_MODEL_H
#include "flight.h"
#include "../msx/banking.h"

#ifdef WINGS_P1_FLIGHT
/* One original 12.5 Hz tick (banked, segment 21): controls, then this tick's
 * motion, which Flight_StepWorldSample spreads over the next
 * FLIGHT_TICK_STEPS steps. world is the plane's world x in pixels. */
void Flight_Tick(FlightState* state, uint16_t world, uint8_t input) WINGS_BANKED;
#endif
#endif
