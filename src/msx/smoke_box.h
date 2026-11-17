#ifndef WINGS_SMOKE_BOX_H
#define WINGS_SMOKE_BOX_H
/* A smoke-path shape's box on the page, clipped as it is drawn (smoke_draw.c,
 * which alone includes this): in Z80, as every shape drawn and erased
 * computes it (the C cost ~1,400 T-states; tests/test_smoke_box_z80.py).
 * The including file defines, by these names: the clip s_Left, s_Right,
 * s_Top, s_Limit (i16) and s_Heave (i8); the input s_BX, s_BY (i16); the
 * output s_BoxLeft, s_BoxRight, s_BoxTop, s_BoxBottom (i16). The C:
 *     const signed char* box = g_SmokeBox + frame * 4;
 *     s_BoxLeft = s_BX + box[0]; s_BoxRight = s_BoxLeft + (u8)box[2];
 *     s_BoxTop = s_BY - s_Heave + box[1]; s_BoxBottom = s_BoxTop + (u8)box[3];
 *     if (s_BoxLeft < s_Left) s_BoxLeft = s_Left;
 *     if (s_BoxRight > s_Right) s_BoxRight = s_Right;
 *     if (s_BoxTop < s_Top) s_BoxTop = s_Top;
 *     if (s_BoxBottom > s_Limit) s_BoxBottom = s_Limit;
 *     return s_BoxRight > s_BoxLeft && s_BoxBottom > s_BoxTop;
 * Signed compares flip the sign bits and compare unsigned. A = frame. */
static u8 Box(u8 frame) __naked
{
    (void)frame;
    __asm
        ld      l, a
        ld      h, #0
        add     hl, hl
        add     hl, hl
        ld      de, #_g_SmokeBox
        add     hl, de              ; HL -> dx, dy, width, height
        ld      a, (hl)
        inc     hl
        ld      e, a
        rlca
        sbc     a, a
        ld      d, a                ; DE = dx
        ld      a, (hl)
        inc     hl
        ld      c, (hl)             ; C = width
        inc     hl
        ld      b, (hl)             ; B = height
        push    bc
        push    af                  ; A = dy
        ld      hl, (_s_BX)
        add     hl, de              ; HL = left
        ld      a, c                ; right = left + width
        add     a, l
        ld      c, a
        ld      a, #0
        adc     a, h
        ld      b, a
        push    bc                  ; right
        ld      de, (_s_Left)         ; max(HL, _s_Left)
        ld      a, h
        xor     a, d
        jp      m, bld$
        ld      a, l
        sub     a, e
        ld      a, h
        sbc     a, d
        jr      nc, blk$
        ex      de, hl
        jr      blk$
bld$:
        bit     7, h
        jr      z, blk$
        ex      de, hl
blk$:
        ld      (_s_BoxLeft), hl
        pop     hl                  ; right
        ld      de, (_s_Right)         ; min(HL, _s_Right)
        ld      a, h
        xor     a, d
        jp      m, brd$
        ld      a, e
        sub     a, l
        ld      a, d
        sbc     a, h
        jr      nc, brk$
        ex      de, hl
        jr      brk$
brd$:
        bit     7, h
        jr      nz, brk$
        ex      de, hl
brk$:
        ld      (_s_BoxRight), hl
        pop     af                  ; dy
        ld      l, a
        rlca
        sbc     a, a
        ld      h, a
        ld      de, (_s_BY)
        add     hl, de
        ld      a, (_s_Heave)
        ld      e, a
        rlca
        sbc     a, a
        ld      d, a
        or      a, a
        sbc     hl, de              ; HL = top
        pop     bc                  ; B = height
        ld      a, b                ; bottom = top + height
        add     a, l
        ld      c, a
        ld      a, #0
        adc     a, h
        ld      b, a
        push    bc
        ld      de, (_s_Top)         ; max(HL, _s_Top)
        ld      a, h
        xor     a, d
        jp      m, btd$
        ld      a, l
        sub     a, e
        ld      a, h
        sbc     a, d
        jr      nc, btk$
        ex      de, hl
        jr      btk$
btd$:
        bit     7, h
        jr      z, btk$
        ex      de, hl
btk$:
        ld      (_s_BoxTop), hl
        pop     hl                  ; bottom
        ld      de, (_s_Limit)         ; min(HL, _s_Limit)
        ld      a, h
        xor     a, d
        jp      m, bbd$
        ld      a, e
        sub     a, l
        ld      a, d
        sbc     a, h
        jr      nc, bbk$
        ex      de, hl
        jr      bbk$
bbd$:
        bit     7, h
        jr      nz, bbk$
        ex      de, hl
bbk$:
        ld      (_s_BoxBottom), hl
        ; nonempty: right > left and bottom > top (signed)
        ld      de, (_s_BoxTop)     ; HL = bottom
        call    box_greater$
        or      a, a
        ret     z                   ; A = 0
        ld      hl, (_s_BoxRight)
        ld      de, (_s_BoxLeft)
box_greater$:                       ; A = 1 when HL > DE, else A = 0
        ld      a, h
        xor     a, d
        jp      m, box_gd$
        ld      a, e
        sub     a, l
        ld      a, d
        sbc     a, h                ; carry: DE < HL
        ld      a, #0
        rla
        ret
box_gd$:
        ld      a, d                ; signs differ: HL > DE when DE is negative
        rlca
        and     a, #1
        rra
        rla
        ret
    __endasm;
}
#endif
