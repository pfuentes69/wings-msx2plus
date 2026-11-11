#include "flight.h"

static int16_t Accelerate(int16_t velocity, uint8_t negative, uint8_t positive, int16_t limit)
{
    if (negative != positive)
    {
        velocity += positive ? 5 : -5;
        if (velocity > limit) velocity = limit;
        if (velocity < -limit) velocity = -limit;
    }
    else if (velocity > 0)
        velocity = velocity > 3 ? velocity - 3 : 0;
    else if (velocity < 0)
        velocity = velocity < -3 ? velocity + 3 : 0;
    return velocity;
}

static uint16_t Move(uint16_t position, int16_t* velocity, uint16_t limit)
{
    if (*velocity < 0 && position < (uint16_t)(-*velocity))
    {
        *velocity = 0;
        return 0;
    }
    if (*velocity > 0 && position > limit - (uint16_t)*velocity)
    {
        *velocity = 0;
        return limit;
    }
    return position + *velocity;
}

void Flight_Reset(FlightState* state)
{
    state->x = 104u * 256u;
    state->y = (FlightVertical)WINGS_FLIGHT_START_Y * 256u;
    state->vx = state->vy = 0;
    state->frame = 1;
    state->facing_left = 0;
}

static void StepControls(FlightState* state, uint8_t input)
{
    state->vx = Accelerate(state->vx, !!(input & FLIGHT_LEFT), !!(input & FLIGHT_RIGHT), 205);
    state->vy = Accelerate(state->vy, !!(input & FLIGHT_UP), !!(input & FLIGHT_DOWN), 154);
#if WINGS_FLIGHT_MAX_Y > 255
    if (state->vy < 0 && state->y < (uint16_t)-state->vy)
        { state->y = 0; state->vy = 0; }
    else if (state->vy > 0 && state->y > FLIGHT_MAX_Y - state->vy)
        { state->y = FLIGHT_MAX_Y; state->vy = 0; }
    else state->y += state->vy;
#else
    state->y = Move(state->y, &state->vy, FLIGHT_MAX_Y);
#endif
}

static void Orient(FlightState* state)
{
    if (state->vx < 0) state->facing_left = 1;
    else if (state->vx > 0) state->facing_left = 0;
    state->frame = state->vy < -16 ? 0 : state->vy > 16 ? 2 : 1;
}

void Flight_Step(FlightState* state, uint8_t input)
{
    StepControls(state, input);
    state->x = Move(state->x, &state->vx, FLIGHT_MAX_X);
    Orient(state);
}

void Flight_StepWorldSample(FlightState* state, uint32_t* x, uint8_t input, uint8_t sample_pose)
{
    int32_t next;
    StepControls(state, input);
    next = (int32_t)*x + state->vx;
    if (next < 0) { next = 0; state->vx = 0; }
    if (next > (int32_t)(WINGS_WORLD_WIDTH - 1) * 256)
    {
        next = (int32_t)(WINGS_WORLD_WIDTH - 1) * 256;
        state->vx = 0;
    }
    *x = next;
    if (sample_pose) Orient(state);
    else
    {
        // Facing persists when a later tick reaches a bound and zeros vx.
        if (state->vx < 0) state->facing_left = 1;
        else if (state->vx > 0) state->facing_left = 0;
    }
}

void Flight_StepWorld(FlightState* state, uint32_t* x, uint8_t input)
{
    Flight_StepWorldSample(state, x, input, 1);
}
