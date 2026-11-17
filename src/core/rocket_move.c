#include "rocket_move.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_ROCKETS)

uint8_t g_RocketLeft;

#ifndef __SDCC
uint16_t Rocket_Divide(const CombatFixed* n, uint16_t d)
{
    return (uint16_t)((uint32_t)n->v / d);
}

/* The reference (and the host build): the original's tick 0x0aa6 without
 * its aim, removal and burst (docs/rockets.md). */
uint8_t Rocket_Move(CombatRocket* r)
{
    CombatFixed t;
    if (r->delay)
    {
        if (!--r->delay) return 1;   /* ignition: aim, then move lit */
        /* Not lit yet: it drops behind the plane, a pixel a tick each way. */
        r->x.w.whole += g_RocketLeft ? 1 : -1;
        --r->y;
    }
    else
    {
        t.v = r->ax; t.v += t.v; r->vx.v += t.v;
        t.v = r->ay; t.v += t.v; r->vy.v += t.v;
    }
    r->x.v += r->vx.v;
    /* The altitude moves by the whole pixels of vy + ay (ay as 16.16). */
    t.v = r->ay; t.v += t.v; t.v += r->vy.v;
    r->y += t.w.whole;
    return 0;
}
#else
/* HL = n, DE = d; the quotient in DE. Restoring division, 16 steps. */
uint16_t Rocket_Divide(const CombatFixed* n, uint16_t d) __naked
{
    (void)n; (void)d;
    __asm
        ld      c, (hl)             ; BC: the low word, shifted into the quotient
        inc     hl
        ld      b, (hl)
        inc     hl
        ld      a, (hl)
        inc     hl
        ld      h, (hl)
        ld      l, a                ; HL: the remainder, from the high word
        ld      a, #16
divide$:
        sla     c
        rl      b
        adc     hl, hl
        jr      c, over$            ; past 16 bits: certainly >= d
        sbc     hl, de
        jr      nc, one$
        add     hl, de
        jr      next$
over$:
        or      a, a
        sbc     hl, de
one$:
        inc     c
next$:
        dec     a
        jr      nz, divide$
        ld      e, c
        ld      d, b
        ret
    __endasm;
}

/* SDCC's long arithmetic through the rocket pointer cost ~5,000 T-states a
 * rocket a tick; this is ~1,100. HL = r; returns A. Offsets: x 0, vx 4,
 * vy 8, ax 12, ay 14, y 16, delay 18 (combat.h, checked below). */
typedef char RocketLayout[(sizeof(CombatRocket) == 23) ? 1 : -1];
uint8_t Rocket_Move(CombatRocket* r) __naked
{
    (void)r;
    __asm
        push    ix
        push    hl
        pop     ix
        ld      a, 18 (ix)
        or      a, a
        jr      z, lit$
        dec     a
        ld      18 (ix), a
        jr      nz, unlit$
        inc     a                   ; 1: ignition
        pop     ix
        ret
unlit$:
        ld      l, 2 (ix)           ; x.whole += left ? 1 : -1
        ld      h, 3 (ix)
        ld      a, (_g_RocketLeft)
        or      a, a
        jr      z, back$
        inc     hl
        jr      ahead$
back$:
        dec     hl
ahead$:
        ld      2 (ix), l
        ld      3 (ix), h
        ld      l, 16 (ix)          ; y -= 1
        ld      h, 17 (ix)
        dec     hl
        ld      16 (ix), l
        ld      17 (ix), h
        jr      move$
lit$:
        ld      l, 12 (ix)          ; vx += 2 ax
        ld      h, 13 (ix)
        ld      a, h
        rlca
        sbc     a, a                ; the sign word of 2 ax
        add     hl, hl
        ld      e, 4 (ix)
        ld      d, 5 (ix)
        add     hl, de
        ld      4 (ix), l
        ld      5 (ix), h
        ld      c, a
        ld      b, a
        ld      l, 6 (ix)
        ld      h, 7 (ix)
        adc     hl, bc
        ld      6 (ix), l
        ld      7 (ix), h
        ld      l, 14 (ix)          ; vy += 2 ay
        ld      h, 15 (ix)
        ld      a, h
        rlca
        sbc     a, a
        add     hl, hl
        ld      e, 8 (ix)
        ld      d, 9 (ix)
        add     hl, de
        ld      8 (ix), l
        ld      9 (ix), h
        ld      c, a
        ld      b, a
        ld      l, 10 (ix)
        ld      h, 11 (ix)
        adc     hl, bc
        ld      10 (ix), l
        ld      11 (ix), h
move$:
        ld      l, 0 (ix)           ; x += vx
        ld      h, 1 (ix)
        ld      e, 4 (ix)
        ld      d, 5 (ix)
        add     hl, de
        ld      0 (ix), l
        ld      1 (ix), h
        ld      l, 2 (ix)
        ld      h, 3 (ix)
        ld      e, 6 (ix)
        ld      d, 7 (ix)
        adc     hl, de
        ld      2 (ix), l
        ld      3 (ix), h
        ld      l, 14 (ix)          ; y += whole(vy + 2 ay)
        ld      h, 15 (ix)
        ld      a, h
        rlca
        sbc     a, a
        add     hl, hl
        ld      e, 8 (ix)
        ld      d, 9 (ix)
        add     hl, de
        ld      c, a
        ld      b, a
        ld      l, 10 (ix)
        ld      h, 11 (ix)
        adc     hl, bc
        ld      e, 16 (ix)
        ld      d, 17 (ix)
        add     hl, de
        ld      16 (ix), l
        ld      17 (ix), h
        xor     a, a
        pop     ix
        ret
    __endasm;
}
#endif
