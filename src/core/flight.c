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
    state->y = 88u * 256u;
    state->vx = state->vy = 0;
    state->frame = 1;
    state->facing_left = 0;
}

void Flight_Step(FlightState* state, uint8_t input)
{
    state->vx = Accelerate(state->vx, !!(input & FLIGHT_LEFT), !!(input & FLIGHT_RIGHT), 205);
    state->vy = Accelerate(state->vy, !!(input & FLIGHT_UP), !!(input & FLIGHT_DOWN), 154);
    state->x = Move(state->x, &state->vx, FLIGHT_MAX_X);
    state->y = Move(state->y, &state->vy, FLIGHT_MAX_Y);
    if (state->vx < 0) state->facing_left = 1;
    else if (state->vx > 0) state->facing_left = 0;
    state->frame = state->vy < -16 ? 0 : state->vy > 16 ? 2 : 1;
}
