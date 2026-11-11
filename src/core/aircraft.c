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

uint8_t Aircraft_ManualPose(uint8_t pose, uint8_t left)
{
    uint8_t pitch = pose == 0 ? 0 : pose == 2 ? 8 : 4;
    return left ? g_PitchLeft[pitch] : g_PitchRight[pitch];
}

void Aircraft_Reset(AircraftState* state)
{
    state->facing_left = state->target_left = state->turning = state->step = state->tick = 0;
    state->shape = g_PitchRight[4];
}

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
