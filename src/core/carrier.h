#ifndef WINGS_CARRIER_H
#define WINGS_CARRIER_H
#include "flight.h"
#define CARRIER_RAISING 0
#define CARRIER_DECK 1
#define CARRIER_LOWERING 2
#define CARRIER_HOLD 3
#define CARRIER_X 7032u
#define CARRIER_DEPTH 32u
#define CARRIER_PIXEL_TICKS 18u
#define CARRIER_PRESENT_TICKS 6u

typedef struct CarrierState { uint8_t stage, depth, tick; } CarrierState;
void Carrier_Reset(CarrierState* state);
uint8_t Carrier_Step(CarrierState* state);
uint8_t Carrier_Request(CarrierState* state, const FlightState* flight, uint16_t world);
void Carrier_Raise(CarrierState* state);
#endif
