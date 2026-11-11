#pragma once
#include "flight.h"

typedef struct WorldState {
    FlightState flight;
    uint32_t x;
    uint16_t camera;
} WorldState;

void World_Reset(WorldState* state);
void World_Step(WorldState* state, uint8_t input);
/* Defer derived camera/screen position until the last tick in a display group. */
void World_StepSample(WorldState* state, uint8_t input, uint8_t sample_view);
