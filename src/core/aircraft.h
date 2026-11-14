#ifndef WINGS_AIRCRAFT_H
#define WINGS_AIRCRAFT_H
#include <stdint.h>
#include "flight.h"

typedef struct AircraftState {
    uint8_t facing_left, target_left, turning, step, tick, shape;
} AircraftState;

#ifdef WINGS_P1_FLIGHT
void Aircraft_SyncFlight(AircraftState* state, const FlightState* flight, uint16_t world);
/* Landing-gear overlay sprite (g_WheelFirst index) for the pose, or 255. */
uint8_t Aircraft_Wheel(const FlightState* flight);
#endif

void Aircraft_Reset(AircraftState* state);
void Aircraft_RequestTurn(AircraftState* state);
void Aircraft_Step(AircraftState* state, int16_t vx, int16_t vy);
/* Intermediate fixed ticks may defer idle pitch selection until presentation. */
void Aircraft_StepSample(AircraftState* state, int16_t vx, int16_t vy, uint8_t sample_pose);
uint8_t Aircraft_FlightPitch(const FlightState* flight);
uint8_t Aircraft_Pitch(int16_t vx, int16_t vy);
#ifndef WINGS_P1_FLIGHT
uint8_t Aircraft_ManualPose(uint8_t pose, uint8_t left);
#endif
#endif
