#include "flight.h"
#include "flight_model.h"

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
    /* A new plane (0xb7ec): on deck, at rest, facing left. */
    state->y = (FlightVertical)FLIGHT_DECK_Y * 256u;
    state->frame = 4;
    state->facing_left = 1;
    state->mode = FLIGHT_GROUND;
    state->turn = state->step = state->landing = state->fast_roll = state->throttle = 0;
    state->turn_clock = 2;
    state->xrem = state->yrem = 0;
    state->speed = state->climb = state->path = state->cancel = state->boost = 0;
#endif
}

#ifdef WINGS_P1_FLIGHT
uint8_t g_FlightCable;

/* Every simulation step: run the original's tick on the first step of each
 * group of FLIGHT_TICK_STEPS, then move by this tick's per-step share. The
 * share is vx/vy plus one Q8 unit on the first |xrem|/|yrem| steps, so a tick
 * moves exactly the original's whole-pixel step. Flight_Tick keeps the motion
 * inside the world and the sky, so no clamping is needed here.
 *
 * SDCC builds use the Z80 version below (150 calls a second); host builds
 * use the C reference, and tests/test_flight_step_z80.py compares them. */
#if defined(__SDCC) && !defined(WINGS_FLIGHT_C)
/* Offsets in FlightState (SDCC packs it): y 2, vx 6, vy 8, step 15, xrem 19, yrem 20. */
typedef char FlightStepCheckLayout[(sizeof(FlightState) == 31) ? 1 : -1];
void Flight_StepWorldSample(FlightState* state, uint32_t* x, uint8_t input, uint8_t sample_pose) __naked
{
    (void)state; (void)x; (void)input; (void)sample_pose;
    __asm
        ; sdcccall(1): HL = state, DE = x; stack: return, input, sample_pose.
        ; The callee removes the two argument bytes. IX is preserved.
        push    iy
        push    de                      ; [x][iy][ret][input][pose]
        push    hl
        pop     iy                      ; IY = state
        ld      a, 15 (iy)
        or      a, a
        jr      nz, fss_move$
        ; Flight_Tick(state, world, input): banked, arguments on the stack.
        ld      hl, #6
        add     hl, sp
        ld      a, (hl)                 ; input
        pop     hl
        push    hl
        inc     hl
        ld      e, (hl)
        inc     hl
        ld      d, (hl)                 ; DE = world pixel (x >> 8)
        push    iy
        push    af
        inc     sp
        push    de
        push    iy
        ld      e, #b_Flight_Tick
        ld      hl, #_Flight_Tick
        call    ___sdcc_bcall_ehl
        pop     af
        pop     af
        inc     sp
        pop     iy
        ld      a, 15 (iy)
    fss_move$:
        ld      c, a                    ; C = step
        ld      l, 6 (iy)
        ld      h, 7 (iy)
        ld      a, 19 (iy)
        call    fss_rem$                ; HL = dx
        ex      de, hl
        ld      a, d
        add     a, a
        sbc     a, a
        ld      b, a                    ; B = sign extension of dx
        pop     hl                      ; HL = x pointer
        ld      a, (hl)
        add     a, e
        ld      (hl), a
        inc     hl
        ld      a, (hl)
        adc     a, d
        ld      (hl), a
        inc     hl
        ld      a, (hl)
        adc     a, b
        ld      (hl), a
        inc     hl
        ld      a, (hl)
        adc     a, b
        ld      (hl), a
        ld      l, 8 (iy)
        ld      h, 9 (iy)
        ld      a, 20 (iy)
        call    fss_rem$                ; HL = dy
        ex      de, hl
        ld      a, d
        add     a, a
        sbc     a, a
        ld      b, a
        ld      a, 2 (iy)
        add     a, e
        ld      2 (iy), a
        ld      a, 3 (iy)
        adc     a, d
        ld      3 (iy), a
        ld      a, 4 (iy)
        adc     a, b
        ld      4 (iy), a
        ld      a, 5 (iy)
        adc     a, b
        ld      5 (iy), a
        ld      a, c
        inc     a
        cp      a, #12                  ; FLIGHT_TICK_STEPS
        jr      c, fss_step$
        xor     a, a
    fss_step$:
        ld      15 (iy), a
        pop     iy
        pop     hl                      ; return address
        pop     af                      ; drop input and sample_pose
        jp      (hl)
    fss_rem$:                           ; HL += sign(A) when step C < |A|
        or      a, a
        ret     z
        jp      p, fss_rem_up$
        neg
        cp      a, c
        ret     c
        ret     z
        dec     hl
        ret
    fss_rem_up$:
        cp      a, c
        ret     c
        ret     z
        inc     hl
        ret
    __endasm;
}
typedef char FlightStepCheckTick[(FLIGHT_TICK_STEPS == 12u) ? 1 : -1];
#else
void Flight_StepWorldSample(FlightState* state, uint32_t* x, uint8_t input, uint8_t sample_pose)
{
    int16_t dx, dy;
    uint8_t step = state->step;
    (void)sample_pose; /* the pose comes from the tick's pitch (Aircraft_SyncFlight) */
    if (!step) Flight_Tick(state, (uint16_t)(*x >> 8), input), step = state->step;
    dx = state->vx; dy = state->vy;
    if (state->xrem > 0) { if (step < (uint8_t)state->xrem) ++dx; }
    else if (step < (uint8_t)-state->xrem) --dx;
    if (state->yrem > 0) { if (step < (uint8_t)state->yrem) ++dy; }
    else if (step < (uint8_t)-state->yrem) --dy;
    state->step = step + 1 == FLIGHT_TICK_STEPS ? 0 : step + 1;
    *x += (uint32_t)(int32_t)dx;
    state->y += (FlightVertical)(int32_t)dy;
}
#endif

uint8_t Flight_GearDown(const FlightState* state, uint16_t world)
{
    if (FLIGHT_ON_DECK(state)) return 1;
    return world > FLIGHT_CARRIER_X - FLIGHT_GEAR_RANGE && world < FLIGHT_CARRIER_X + FLIGHT_GEAR_RANGE;
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
#endif
