#ifndef WINGS_SMOKE_PIECE_H
#define WINGS_SMOKE_PIECE_H
/* One piece of a smoke-path shape, clipped and copied (smoke_draw.c, which
 * alone includes this): in Z80, as every drawn shape copies its pieces
 * (the C cost ~1,000 T-states a piece; tests/test_smoke_piece_z80.py). The
 * including file defines, by these names: the clip s_Left, s_Right, s_Top,
 * s_Limit (i16); the shape's position s_X, s_Row (i16); s_Page (u8);
 * scratch s_PL, s_PR, s_PT, s_PB (i16). The C:
 *     s_PL = s_X + piece->dx; s_PR = s_PL + piece->width;
 *     s_PT = s_Row + piece->dy; s_PB = s_PT + piece->height;
 *     g_VDP_Command.SX = piece->atlas_x; g_VDP_Command.SY = piece->atlas_y;
 *     if (s_PL < s_Left) { g_VDP_Command.SX += s_Left - s_PL; s_PL = s_Left; }
 *     if (s_PR > s_Right) s_PR = s_Right;
 *     if (s_PT < s_Top) { g_VDP_Command.SY += s_Top - s_PT; s_PT = s_Top; }
 *     if (s_PB > s_Limit) s_PB = s_Limit;
 *     if (s_PR <= s_PL || s_PB <= s_PT) return;
 *     g_VDP_Command.DY = ((u16)s_Page << 8) + s_PT; g_VDP_Command.NY = s_PB - s_PT;
 *     g_VDP_Command.ARG = 0; g_VDP_Command.CMD = VDP_CMD_LMMM + VDP_OP_TIMP;
 *     Vdp_RingCopy((u8)s_PL, s_PR - s_PL);
 * AircraftShape: dx +2, dy +3, width +4, height +5, atlas_x +6, atlas_y +7.
 * VDP_Command: SX +0, SY +2, DY +6, NY +10, ARG +13, CMD +14. HL = piece. */
static void Piece(const AircraftShape* piece) __naked
{
    (void)piece;
    __asm
        push    hl
        pop     iy                      ; IY = piece
        ld      a, 2 (iy)               ; PL = X + dx
        ld      e, a
        rlca
        sbc     a, a
        ld      d, a
        ld      hl, (_s_X)
        add     hl, de
        ld      (_s_PL), hl
        ld      e, 4 (iy)               ; PR = PL + width
        ld      d, #0
        add     hl, de
        ld      (_s_PR), hl
        ld      a, 3 (iy)               ; PT = Row + dy
        ld      e, a
        rlca
        sbc     a, a
        ld      d, a
        ld      hl, (_s_Row)
        add     hl, de
        ld      (_s_PT), hl
        ld      e, 5 (iy)               ; PB = PT + height
        ld      d, #0
        add     hl, de
        ld      (_s_PB), hl
        ld      l, 6 (iy)               ; SX = atlas_x
        ld      h, #0
        ld      (_g_VDP_Command + 0), hl
        ld      l, 7 (iy)               ; SY = atlas_y
        ld      h, 8 (iy)
        ld      (_g_VDP_Command + 2), hl
        ld      de, (_s_PL)             ; PL < Left: SX += Left - PL, PL = Left
        ld      hl, (_s_Left)
        call    piece_lt$
        jr      nc, piece_right$
        ld      hl, (_s_Left)
        ld      de, (_s_PL)
        or      a, a
        sbc     hl, de
        ld      de, (_g_VDP_Command + 0)
        add     hl, de
        ld      (_g_VDP_Command + 0), hl
        ld      hl, (_s_Left)
        ld      (_s_PL), hl
    piece_right$:
        ld      de, (_s_Right)          ; Right < PR: PR = Right
        ld      hl, (_s_PR)
        call    piece_lt$
        jr      nc, piece_top$
        ld      hl, (_s_Right)
        ld      (_s_PR), hl
    piece_top$:
        ld      de, (_s_PT)             ; PT < Top: SY += Top - PT, PT = Top
        ld      hl, (_s_Top)
        call    piece_lt$
        jr      nc, piece_bottom$
        ld      hl, (_s_Top)
        ld      de, (_s_PT)
        or      a, a
        sbc     hl, de
        ld      de, (_g_VDP_Command + 2)
        add     hl, de
        ld      (_g_VDP_Command + 2), hl
        ld      hl, (_s_Top)
        ld      (_s_PT), hl
    piece_bottom$:
        ld      de, (_s_Limit)          ; Limit < PB: PB = Limit
        ld      hl, (_s_PB)
        call    piece_lt$
        jr      nc, piece_empty$
        ld      hl, (_s_Limit)
        ld      (_s_PB), hl
    piece_empty$:
        ld      de, (_s_PL)             ; nothing unless PL < PR and PT < PB
        ld      hl, (_s_PR)
        call    piece_lt$
        ret     nc
        ld      de, (_s_PT)
        ld      hl, (_s_PB)
        call    piece_lt$
        ret     nc
        ld      hl, (_s_PB)             ; NY = PB - PT
        ld      de, (_s_PT)
        or      a, a
        sbc     hl, de
        ld      (_g_VDP_Command + 10), hl
        ld      a, (_s_Page)            ; DY = page * 256 + PT
        add     a, d
        ld      d, a
        ld      (_g_VDP_Command + 6), de
        xor     a, a
        ld      (_g_VDP_Command + 13), a
        ld      a, #(VDP_CMD_LMMM + VDP_OP_TIMP)
        ld      (_g_VDP_Command + 14), a
        ld      hl, (_s_PR)             ; Vdp_RingCopy((u8)PL, PR - PL)
        ld      de, (_s_PL)
        or      a, a
        sbc     hl, de
        ex      de, hl                  ; DE = width, HL = PL
        ld      a, l
        jp      _Vdp_RingCopy
    piece_lt$:                          ; carry when DE < HL, signed (flips D, H)
        ld      a, d
        xor     a, #0x80
        ld      d, a
        ld      a, h
        xor     a, #0x80
        ld      h, a
        ld      a, e
        sub     a, l
        ld      a, d
        sbc     a, h
        ret
    __endasm;
}
#endif
