#ifndef WINGS_XORSHIFT_H
#define WINGS_XORSHIFT_H
#include <stdint.h>
/* The 16-bit xorshift (7, 9, 8) the modules use as their random source:
 *     s ^= s << 7; s ^= s >> 9; s ^= s << 8;
 * SDCC compiles the 7- and 9-bit shifts into bit-by-bit loops (several
 * hundred T-states a number); on the Z80 this is the classic 15-instruction
 * form (John Metcalf's), the same sequence (tests/test_xorshift_z80.py).
 * Include from one .c file per segment: the function is static. */
#ifdef __SDCC
static uint16_t Xorshift(uint16_t* seed) __naked
{
    (void)seed;
    __asm
        push    hl                  ; HL = seed
        ld      a, (hl)
        inc     hl
        ld      h, (hl)
        ld      l, a                ; HL = s
        ld      a, h
        rra
        ld      a, l
        rra
        xor     a, h
        ld      h, a
        ld      a, l
        rra
        ld      a, h
        rra
        xor     a, l
        ld      l, a
        xor     a, h
        ld      h, a
        ex      de, hl              ; DE = the new s, returned
        pop     hl
        ld      (hl), e
        inc     hl
        ld      (hl), d
        ret
    __endasm;
}
#else
static inline uint16_t Xorshift(uint16_t* seed)
{
    uint16_t s = *seed;
    s ^= s << 7;
    s ^= s >> 9;
    s ^= s << 8;
    return *seed = s;
}
#endif
#endif
