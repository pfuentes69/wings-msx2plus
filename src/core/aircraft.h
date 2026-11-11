#ifndef WINGS_AIRCRAFT_H
#define WINGS_AIRCRAFT_H
#include <stdint.h>

typedef struct AircraftState {
    uint8_t facing_left, target_left, turning, step, tick, shape;
} AircraftState;

void Aircraft_Reset(AircraftState* state);
void Aircraft_RequestTurn(AircraftState* state);
void Aircraft_Step(AircraftState* state, int16_t vx, int16_t vy);
/* Intermediate fixed ticks may defer idle pitch selection until presentation. */
void Aircraft_StepSample(AircraftState* state, int16_t vx, int16_t vy, uint8_t sample_pose);
uint8_t Aircraft_Pitch(int16_t vx, int16_t vy);
uint8_t Aircraft_ManualPose(uint8_t pose, uint8_t left);
#endif
