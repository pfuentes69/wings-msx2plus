#include "flight.h"

#ifndef WINGS_P1_FLIGHT
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

#endif

#if !defined(WINGS_P1_FLIGHT) || WINGS_FLIGHT_MAX_Y <= 255
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

#endif

void Flight_Reset(FlightState* state)
{
    state->x = 104u * 256u;
    state->y = (FlightVertical)WINGS_FLIGHT_START_Y * 256u;
    state->vx = state->vy = 0;
    state->frame = 1;
    state->facing_left = 0;
#ifdef WINGS_P1_FLIGHT
    state->y = (FlightVertical)FLIGHT_DECK_Y * 256u;
    state->facing_left = state->target_left = 1;
    state->mode = FLIGHT_GROUND;
    state->turn_ticks = state->ground_tick = 0;
#endif
}

#ifdef WINGS_P1_FLIGHT
static int16_t Approach(int16_t value, int16_t target)
{
    if (value < target) return target - value < 5 ? target : value + 5;
    if (value > target) return value - target < 5 ? target : value - 5;
    return value;
}
#endif

static void StepControls(FlightState* state, uint8_t input)
{
#ifdef WINGS_P1_FLIGHT
    uint8_t horizontal = input & (FLIGHT_LEFT | FLIGHT_RIGHT);
    uint8_t vertical = input & (FLIGHT_UP | FLIGHT_DOWN);
    int16_t speed = state->vx < 0 ? -state->vx : state->vx;
    int16_t target = 154, climb = 0;
    if (horizontal == (FLIGHT_LEFT | FLIGHT_RIGHT)) horizontal = 0;
    if (vertical == (FLIGHT_UP | FLIGHT_DOWN)) vertical = 0;
    if (state->mode == FLIGHT_GROUND)
    {
        state->vy = 0;
        if (state->turn_ticks)
        {
            state->vx = 0;
            if (!--state->turn_ticks) state->facing_left = state->target_left;
            return;
        }
        if (horizontal && ((horizontal == FLIGHT_LEFT) != state->facing_left))
        {
            speed = Approach(speed,0);
            state->ground_tick = 0;
            if (!speed)
            {
                state->target_left = horizontal == FLIGHT_LEFT;
                state->turn_ticks = FLIGHT_TAXI_TURN_TICKS;
            }
        }
        else if (horizontal && speed < 205)
        {
            /* Retain fractional ground acceleration on the fixed simulation
             * clock; rounding each tick to Q8 would otherwise give zero. */
            if (++state->ground_tick == FLIGHT_GROUND_ACCEL_TICKS)
            {
                state->ground_tick = 0;
                ++speed;
            }
        }
        else
        {
            state->ground_tick = 0;
            if (!horizontal) speed = Approach(speed, 0);
        }
        state->vx = state->facing_left ? -speed : speed;
        state->vy = 0;
        return;
    }
    if (horizontal)
    {
        target = 205;
        if (!state->turn_ticks && (horizontal == FLIGHT_LEFT) != state->facing_left)
        {
            state->target_left = !state->facing_left;
            state->turn_ticks = FLIGHT_TURN_TICKS;
        }
        climb = vertical == FLIGHT_UP ? -96 : vertical == FLIGHT_DOWN ? 96 : 0;
        state->mode = FLIGHT_AIRBORNE;
    }
    else if (vertical || state->mode == FLIGHT_STALL_DIVE)
    {
        target = vertical == FLIGHT_UP ? 32 : 154;
        climb = vertical == FLIGHT_UP ? 32 : 48;
        state->mode = vertical == FLIGHT_UP ? FLIGHT_STALL : FLIGHT_STALL_DIVE;
    }
    else state->mode = FLIGHT_AIRBORNE;
    if (state->turn_ticks)
    {
        climb += 64;
        if (!--state->turn_ticks) state->facing_left = state->target_left;
    }
    speed = Approach(speed, target);
    state->vx = state->facing_left ? -speed : speed;
    state->vy = Approach(state->vy, climb);
#else
    state->vx = Accelerate(state->vx, !!(input & FLIGHT_LEFT), !!(input & FLIGHT_RIGHT), 205);
    state->vy = Accelerate(state->vy, !!(input & FLIGHT_UP), !!(input & FLIGHT_DOWN), 154);
#endif
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

#ifndef WINGS_P1_FLIGHT
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

#endif

void Flight_StepWorldSample(FlightState* state, uint32_t* x, uint8_t input, uint8_t sample_pose)
{
    int32_t next;
    StepControls(state, input);
#ifdef WINGS_P1_FLIGHT
    if (state->mode == FLIGHT_GROUND && !state->turn_ticks && state->facing_left &&
        (*x >> 8) <= FLIGHT_LAUNCH_ZONE && state->vx <= -FLIGHT_TAKEOFF_SPEED &&
        (input & (FLIGHT_LEFT | FLIGHT_RIGHT)) == FLIGHT_LEFT &&
        (input & (FLIGHT_UP | FLIGHT_DOWN)) == FLIGHT_UP)
        state->mode = FLIGHT_AIRBORNE;
#endif
    next = (int32_t)*x + state->vx;
#ifdef WINGS_P1_FLIGHT
    if (state->mode == FLIGHT_GROUND)
    {
        /* Temporary safety stops. P2 will replace these with deck departure
         * and crash handling; takeoff is already airborne before this clamp. */
        if (next < (int32_t)FLIGHT_TAXI_MIN_X * 256)
        { next = (int32_t)FLIGHT_TAXI_MIN_X * 256; state->vx = 0; state->ground_tick = 0; }
        if (next > (int32_t)FLIGHT_TAXI_MAX_X * 256)
        { next = (int32_t)FLIGHT_TAXI_MAX_X * 256; state->vx = 0; state->ground_tick = 0; }
    }
#endif
    if (next < 0) { next = 0; state->vx = 0; }
    if (next > (int32_t)(WINGS_WORLD_WIDTH - 1) * 256)
    {
        next = (int32_t)(WINGS_WORLD_WIDTH - 1) * 256;
        state->vx = 0;
    }
    *x = next;
#ifndef WINGS_P1_FLIGHT
    if (sample_pose) Orient(state);
    else
    {
        // Facing persists when a later tick reaches a bound and zeros vx.
        if (state->vx < 0) state->facing_left = 1;
        else if (state->vx > 0) state->facing_left = 0;
    }
#else
    (void)sample_pose; /* P1 attitude and committed facing are sampled by Aircraft_SyncFlight. */
#endif
}

#ifndef WINGS_P1_FLIGHT
void Flight_StepWorld(FlightState* state, uint32_t* x, uint8_t input)
{
    Flight_StepWorldSample(state, x, input, 1);
}

#endif

#ifdef WINGS_P1_FLIGHT
uint8_t Flight_GearDown(const FlightState* state, uint16_t world)
{
    if (state->mode == FLIGHT_GROUND) return 1;
    /* Keep departure clear of the approach region so wheels retract on lift-off.
     * Inbound distance/height thresholds are explicit MSX tuning for now. */
    return state->facing_left && !state->turn_ticks && state->vy >= 0 &&
        world >= FLIGHT_DECK_LEFT + 128u && world <= FLIGHT_DECK_RIGHT + 192u &&
        state->y >= (FlightVertical)(FLIGHT_DECK_Y - 80u) * 256u &&
        state->y <= (FlightVertical)FLIGHT_DECK_Y * 256u;
}
#endif
