#ifndef WINGS_CARRIER_H
#define WINGS_CARRIER_H
#include "flight.h"
#define CARRIER_RAISING 0
#define CARRIER_DECK 1
#define CARRIER_LOWERING 2
#define CARRIER_HOLD 3
#define CARRIER_DEPTH 32u
/* First playfield row below the elevator well's opening (its light lower
 * edge, row 142): the platform and the plane riding it are hidden from
 * there down while the lift moves. */
#define CARRIER_WELL_BOTTOM 142
#define CARRIER_PIXEL_TICKS 18u
#define CARRIER_PRESENT_TICKS 6u

typedef struct CarrierState { uint8_t stage, depth, tick; } CarrierState;
void Carrier_Reset(CarrierState* state);
uint8_t Carrier_Step(CarrierState* state);
uint8_t Carrier_Request(CarrierState* state, const FlightState* flight, uint16_t world);
void Carrier_Raise(CarrierState* state);
#endif
