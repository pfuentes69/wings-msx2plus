#include "flight.h"
#include "../msx/banking.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_FLIGHT)

/* Steps that only move the plane, batched (msx/step_batch.c); with the
 * flight model, out of the resident code. tests/test_flight_step_z80.py
 * checks them against single steps of Flight_StepWorldSample. */
#ifdef WINGS_P1_FLIGHT
#if defined(__SDCC)
typedef char FlightStepManyLayout[(WINGS_FLIGHT_MAX_Y > 255 && FLIGHT_TICK_STEPS == 12u) ? 1 : -1];
void Flight_StepMany(FlightState* state, uint32_t* x, uint8_t n) __naked
{
    (void)state; (void)x; (void)n;
    __asm
        ; sdcccall(1): HL = state, DE = x; stack: return, n (one byte,
        ; removed here). IX and IY are preserved.
        push    iy
        push    de                      ; [x][iy][ret][n]
        push    hl
        pop     iy                      ; IY = state
        ld      hl, #6
        add     hl, sp
        ld      b, (hl)                 ; B = n
        ld      c, 15 (iy)              ; C = step
        ld      e, 6 (iy)
        ld      d, 7 (iy)               ; DE = vx
        ld      a, 19 (iy)              ; xrem
        call    fsm_total$              ; HL = dx
        ex      de, hl
        ld      a, d
        add     a, a
        sbc     a, a                    ; A = sign of dx
        pop     hl                      ; HL = x pointer
        push    bc
        ld      b, a
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
        pop     bc
        ld      e, 8 (iy)
        ld      d, 9 (iy)               ; DE = vy
        ld      a, 20 (iy)              ; yrem
        call    fsm_total$              ; HL = dy
        ex      de, hl
        ld      a, d
        add     a, a
        sbc     a, a
        ld      l, a                    ; L = sign of dy
        ld      a, 2 (iy)
        add     a, e
        ld      2 (iy), a
        ld      a, 3 (iy)
        adc     a, d
        ld      3 (iy), a
        ld      a, 4 (iy)
        adc     a, l
        ld      4 (iy), a
        ld      a, 5 (iy)
        adc     a, l
        ld      5 (iy), a
        ld      a, c
        add     a, b
        cp      a, #12                  ; FLIGHT_TICK_STEPS
        jr      c, fsm_step$
        xor     a, a
    fsm_step$:
        ld      15 (iy), a
        pop     iy
        pop     hl                      ; return address
        inc     sp                      ; drop n
        jp      (hl)
    fsm_total$:                         ; HL = n x DE + the remainder's units; B = n, C = step kept
        ld      hl, #0
        push    bc
    fsm_mul$:
        add     hl, de
        djnz    fsm_mul$
        pop     bc
        or      a, a
        ret     z
        jp      p, fsm_up$
        neg
        call    fsm_count$
        ld      e, a
        ld      d, #0
        or      a, a
        sbc     hl, de
        ret
    fsm_up$:
        call    fsm_count$
        ld      e, a
        ld      d, #0
        add     hl, de
        ret
    fsm_count$:                         ; A = max(0, min(step + n, A) - step)
        ld      e, a
        ld      a, c
        add     a, b
        cp      a, e
        jr      c, fsm_min$
        ld      a, e
    fsm_min$:
        sub     a, c
        ret     nc
        xor     a, a
        ret
    __endasm;
}
#else
/* What n steps from step c add to a position moving v a step, one Q8 unit
 * more (rem > 0) or less (rem < 0) on each of the tick's first |rem|. */
static int16_t Moved(int16_t v, int8_t rem, uint8_t c, uint8_t n)
{
    int16_t sum = 0;
    uint8_t r, k = n;
    do sum += v; while (--k);
    if (!rem) return sum;
    r = rem > 0 ? (uint8_t)rem : (uint8_t)-rem;
    if (r <= c) return sum;
    k = (uint8_t)(r < (uint8_t)(c + n) ? r : c + n) - c;
    return rem > 0 ? sum + k : sum - k;
}

void Flight_StepMany(FlightState* state, uint32_t* x, uint8_t n)
{
    uint8_t c = state->step;
    *x += (uint32_t)(int32_t)Moved(state->vx, state->xrem, c, n);
    state->y += (FlightVertical)(int32_t)Moved(state->vy, state->yrem, c, n);
    c += n;
    state->step = c == FLIGHT_TICK_STEPS ? 0 : c;
}
#endif
#endif
