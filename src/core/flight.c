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

#ifdef WINGS_P1_FLIGHT
/* The 150 Hz step works on a file-static copy of the state. SDCC addresses
 * a static field directly (ld a,(nn)); through a pointer, each access
 * reloads the pointer from the IX frame and adds the offset, which made this
 * step cost ~2,500 T-states. Not reentrant: called only from the main loop. */
static FlightState s_Work;

static void StepControls(uint8_t input)
{
    uint8_t horizontal = input & (FLIGHT_LEFT | FLIGHT_RIGHT);
    uint8_t vertical = input & (FLIGHT_UP | FLIGHT_DOWN);
    uint8_t mode = s_Work.mode, turn = s_Work.turn_ticks, left = s_Work.facing_left;
    int16_t speed = s_Work.vx, vy, target = 154, climb = 0;
    if (speed < 0) speed = -speed;
    if (horizontal == (FLIGHT_LEFT | FLIGHT_RIGHT)) horizontal = 0;
    if (vertical == (FLIGHT_UP | FLIGHT_DOWN)) vertical = 0;
    if (mode == FLIGHT_GROUND)
    {
        s_Work.vy = 0;
        if (turn)
        {
            s_Work.vx = 0;
            if (!--turn) s_Work.facing_left = s_Work.target_left;
            s_Work.turn_ticks = turn;
            return;
        }
        if (horizontal && ((horizontal == FLIGHT_LEFT) != left))
        {
            speed = Approach(speed, 0);
            s_Work.ground_tick = 0;
            if (!speed)
            {
                s_Work.target_left = horizontal == FLIGHT_LEFT;
                s_Work.turn_ticks = FLIGHT_TAXI_TURN_TICKS;
            }
        }
        else if (horizontal && speed < 205)
        {
            /* Retain fractional ground acceleration on the fixed simulation
             * clock; rounding each tick to Q8 would otherwise give zero. */
            if (++s_Work.ground_tick == FLIGHT_GROUND_ACCEL_TICKS)
            {
                s_Work.ground_tick = 0;
                ++speed;
            }
        }
        else
        {
            s_Work.ground_tick = 0;
            if (!horizontal) speed = Approach(speed, 0);
        }
        s_Work.vx = left ? -speed : speed;
        return;
    }
    if (horizontal)
    {
        target = 205;
        if (!turn && (horizontal == FLIGHT_LEFT) != left)
        {
            s_Work.target_left = !left;
            turn = FLIGHT_TURN_TICKS;
        }
        climb = vertical == FLIGHT_UP ? -96 : vertical == FLIGHT_DOWN ? 96 : 0;
        mode = FLIGHT_AIRBORNE;
    }
    else if (vertical == FLIGHT_UP)
    {
        target = 32;
        climb = 32;
        mode = FLIGHT_STALL;
    }
    else if (vertical || mode == FLIGHT_STALL_DIVE)
    {
        climb = 48;
        mode = FLIGHT_STALL_DIVE;
    }
    else mode = FLIGHT_AIRBORNE;
    s_Work.mode = mode;
    if (turn)
    {
        climb += 64;
        if (!--turn) left = s_Work.facing_left = s_Work.target_left;
        s_Work.turn_ticks = turn;
    }
    speed = Approach(speed, target);
    s_Work.vx = left ? -speed : speed;
    s_Work.vy = vy = Approach(s_Work.vy, climb);
#if WINGS_FLIGHT_MAX_Y > 255
    {
        /* Same clamps as the unsigned form: y + vy below 0 or, while
         * climbing down the screen, above FLIGHT_MAX_Y. */
        int32_t y = (int32_t)s_Work.y + vy;
        if (y < 0) { s_Work.y = 0; s_Work.vy = 0; }
        else if (vy > 0 && y > (int32_t)FLIGHT_MAX_Y) { s_Work.y = FLIGHT_MAX_Y; s_Work.vy = 0; }
        else s_Work.y = (FlightVertical)y;
    }
#else
    s_Work.y = Move(s_Work.y, &s_Work.vy, FLIGHT_MAX_Y);
#endif
}
#else
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
#endif

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

#ifdef WINGS_P1_FLIGHT
void Flight_StepWorldSample(FlightState* state, uint32_t* x, uint8_t input, uint8_t sample_pose)
{
    int32_t next;
    (void)sample_pose; /* P1 attitude and committed facing are sampled by Aircraft_SyncFlight. */
    s_Work = *state;
    StepControls(input);
    if (s_Work.mode == FLIGHT_GROUND && !s_Work.turn_ticks && s_Work.facing_left &&
        (*x >> 8) <= FLIGHT_LAUNCH_ZONE && s_Work.vx <= -FLIGHT_TAKEOFF_SPEED &&
        (input & (FLIGHT_LEFT | FLIGHT_RIGHT)) == FLIGHT_LEFT &&
        (input & (FLIGHT_UP | FLIGHT_DOWN)) == FLIGHT_UP)
        s_Work.mode = FLIGHT_AIRBORNE;
    next = (int32_t)*x + s_Work.vx;
    if (s_Work.mode == FLIGHT_GROUND)
    {
        /* Temporary safety stops. P2 will replace these with deck departure
         * and crash handling; takeoff is already airborne before this clamp. */
        if (next < (int32_t)FLIGHT_TAXI_MIN_X * 256)
        { next = (int32_t)FLIGHT_TAXI_MIN_X * 256; s_Work.vx = 0; s_Work.ground_tick = 0; }
        if (next > (int32_t)FLIGHT_TAXI_MAX_X * 256)
        { next = (int32_t)FLIGHT_TAXI_MAX_X * 256; s_Work.vx = 0; s_Work.ground_tick = 0; }
    }
    if (next < 0) { next = 0; s_Work.vx = 0; }
    if (next > (int32_t)(WINGS_WORLD_WIDTH - 1) * 256)
    {
        next = (int32_t)(WINGS_WORLD_WIDTH - 1) * 256;
        s_Work.vx = 0;
    }
    *x = next;
    *state = s_Work;
}
#else
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
#endif

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
