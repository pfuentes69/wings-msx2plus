#include "aircraft.h"
#include "../generated/hellcat_frames.h"

uint8_t Aircraft_Pitch(int16_t vx, int16_t vy)
{
    uint16_t x = vx < 0 ? -vx : vx;
    uint16_t y = vy < 0 ? -vy : vy;
    if (y <= 16) return 4;
    if (y * 4 < x) return vy < 0 ? 3 : 5;
    if (y * 2 < x) return vy < 0 ? 2 : 6;
    if (y < x) return vy < 0 ? 1 : 7;
    if (vy > 0 && y * 2 > x * 3) return 9;
    return vy < 0 ? 0 : 8;
}

/* Legacy fixed-pose viewer; the release derives poses from flight state. */
#ifndef WINGS_P1_FLIGHT
uint8_t Aircraft_ManualPose(uint8_t pose, uint8_t left)
{
    uint8_t pitch = pose == 0 ? 0 : pose == 2 ? 8 : 4;
    return left ? g_PitchLeft[pitch] : g_PitchRight[pitch];
}

#endif

void Aircraft_Reset(AircraftState* state)
{
    state->facing_left = state->target_left = state->turning = state->step = state->tick = 0;
    state->shape = g_PitchRight[4];
}

#ifndef WINGS_P1_FLIGHT
void Aircraft_RequestTurn(AircraftState* state)
{
    state->target_left ^= 1;
}

void Aircraft_StepSample(AircraftState* state, int16_t vx, int16_t vy, uint8_t sample_pose)
{
    if (vx < -16) state->target_left = 1;
    else if (vx > 16) state->target_left = 0;
    if (!state->turning && state->target_left != state->facing_left)
    {
        state->turning = 1;
        state->step = state->tick = 0;
    }
    if (state->turning)
    {
        state->shape = state->facing_left ? g_TurnLeftToRight[state->step] : g_TurnRightToLeft[state->step];
        if (++state->tick == 5)
        {
            state->tick = 0;
            if (++state->step == AIRCRAFT_TURN_STEPS)
            {
                state->turning = 0;
                state->facing_left ^= 1;
            }
        }
    }
    else if (sample_pose)
    {
        uint8_t pitch = Aircraft_Pitch(vx, vy);
        state->shape = state->facing_left ? g_PitchLeft[pitch] : g_PitchRight[pitch];
    }
}

void Aircraft_Step(AircraftState* state, int16_t vx, int16_t vy)
{
    Aircraft_StepSample(state, vx, vy, 1);
}

#endif

uint8_t Aircraft_FlightPitch(const FlightState* flight)
{
#ifdef WINGS_P1_FLIGHT
    return flight->frame; /* the original's pose for the commanded climb */
#else
    return Aircraft_Pitch(flight->vx,flight->vy);
#endif
}
#ifdef WINGS_P1_FLIGHT
/* Deck turn frame 0..6 (the original's hc21, hc20..hc1b) to the MSX taxi
 * sequence, 5 steps from a resting side view to the front view. */
static const uint8_t s_DeckTurn[7] = {0, 1, 2, 3, 3, 4, 5};
/* The original picks the shape from the flight state (0xc378, 0xabde). The
 * wheels are a separate overlay drawn by the renderer (Aircraft_Wheel). */
void Aircraft_SyncFlight(AircraftState* state, const FlightState* flight, uint16_t world)
{
    uint8_t left = flight->facing_left, pitch = flight->frame;
    (void)world;
    state->facing_left = state->target_left = left;
    state->turning = flight->turn != 0;
    state->step = flight->turn;
    if (flight->mode == FLIGHT_GROUND && !flight->fast_roll)
    {
        /* Tail down at rest or rolling slowly, or turning on the spot. */
        if (flight->turn)
            state->shape = g_TaxiTurn[left ? s_DeckTurn[flight->turn] : 10 - s_DeckTurn[flight->turn]];
        else state->shape = g_TailDownFrame[left];
    }
    else if (flight->turn) state->shape = left ? g_AirTurnLeft[flight->turn] : g_AirTurnRight[flight->turn];
    else state->shape = left ? g_PitchLeft[pitch] : g_PitchRight[pitch];
}

/* 0x0550: the wheel overlay for the pose, when the original draws it: not
 * turning, and flying, held by a cable, or rolling fast on deck (the slow
 * deck poses include their wheels). 255 when none. */
uint8_t Aircraft_Wheel(const FlightState* flight)
{
    if (flight->turn || flight->mode >= FLIGHT_DEAD || (flight->mode == FLIGHT_GROUND && !flight->fast_roll)) return 255;
    return (flight->facing_left ? 10 : 0) + flight->frame;
}
#endif
