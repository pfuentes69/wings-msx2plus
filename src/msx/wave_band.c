#include "wave_band.h"
#include "banking.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_FLIGHT)
#include "vdp.h"
#include "vdp_inl.h"

/* The wave strip's band loop in Z80 (docs/frame-budget.md, 2026-11-17):
 * SDCC's version cost ~1,800 T-states per VDP command over the carrier,
 * 6 ms a frame. Here the per-row fields are set once per row group and each
 * part only computes SX, DX, NX and the command. */

WaveBand g_WaveBand;
static u16 s_Sx, s_Pos;
static u8 s_Left, s_Take, s_StartLeft;
typedef char WaveBandLayout[sizeof(WaveBand) == 17 ? 1 : -1];

void Waves_DrawBand(void) __naked
{
    __asm
        ; s_StartLeft = start mod 96 (start signed, >= -30720): subtract
        ; 96 << k from start + 30720 = 96 * 320, k = 9 .. 0.
        ld hl, (_g_WaveBand + 8)
        ld de, #30720
        add hl, de
        ld de, #49152
    wb_mod$:
        or a
        sbc hl, de
        jr nc, wb_mod_keep$
        add hl, de
    wb_mod_keep$:
        srl d
        rr e
        ld a, d
        or a
        jr nz, wb_mod$
        ld a, e
        cp #96
        jr nc, wb_mod$
        ld a, l
        ld (_s_StartLeft), a
        xor a
        ld (_g_VDP_Command + 11), a     ; NY high
        ld (_g_VDP_Command + 13), a     ; ARG
        ld (_g_VDP_Command + 5), a      ; DX high
        ld (_g_VDP_Command + 9), a      ; NX high
    wb_group$:
        ; take = height, split at row 9 on the special frame
        ld a, (_g_WaveBand + 15)
        or a
        ret z
        ld b, a
        ld a, (_g_WaveBand + 16)
        or a
        jr z, wb_take$
        ld a, (_g_WaveBand + 14)
        cp #9
        jr nc, wb_take$
        add a, b
        cp #10
        jr c, wb_take$
        ld a, (_g_WaveBand + 14)
        neg
        add a, #9
        ld b, a
    wb_take$:
        ld a, b
        ld (_s_Take), a
        ld (_g_VDP_Command + 10), a     ; NY
        ; the source: the texture, or the tail piece from row 9
        ld a, (_g_WaveBand + 14)
        ld e, a
        ld d, #0
        ld hl, (_g_WaveBand + 0)
        ld bc, (_g_WaveBand + 2)
        ld a, (_g_WaveBand + 16)
        or a
        jr z, wb_source$
        ld a, e
        cp #9
        jr c, wb_source$
        ld hl, (_g_WaveBand + 4)
        ld bc, (_g_WaveBand + 6)
    wb_source$:
        ld (_s_Sx), hl
        ld h, b
        ld l, c
        add hl, de
        ld (_g_VDP_Command + 2), hl     ; SY = source + row
        ld hl, (_g_WaveBand + 12)
        add hl, de
        ld (_g_VDP_Command + 6), hl     ; DY = dy + row
        ld hl, (_g_WaveBand + 8)
        ld (_s_Pos), hl
        ld a, (_s_StartLeft)
        ld (_s_Left), a
    wb_part$:
        ; while (int16)(end - position) > 0
        ld hl, (_g_WaveBand + 10)
        ld de, (_s_Pos)
        or a
        sbc hl, de
        bit 7, h
        jr nz, wb_next$
        ld a, h
        or l
        jr z, wb_next$
        ; part = min(end - position, 96 - left, 256 - (position & 255))
        ld a, h
        or a
        ld a, l
        jr z, wb_small$
        ld a, #255
    wb_small$:
        ld c, a
        ld a, (_s_Left)
        ld b, a
        ld a, #96
        sub b
        cp c
        jr nc, wb_limit$
        ld c, a
    wb_limit$:
        ld a, e
        neg
        jr z, wb_seam$                  ; position on a page boundary: 256
        cp c
        jr nc, wb_seam$
        ld c, a
    wb_seam$:
        ld hl, (_s_Sx)                  ; SX = source x + left
        ld a, l
        add a, b
        ld l, a
        jr nc, wb_sx$
        inc h
    wb_sx$:
        ld (_g_VDP_Command + 0), hl
        ld a, e
        ld (_g_VDP_Command + 4), a      ; DX = position & 255
        ld a, (_g_WaveBand + 14)
        cp #2
        ld a, #0x98                     ; rows 0..1: LMMM, transparent
        jr c, wb_kind$
        bit 0, e
        jr nz, wb_pixel$
        ld a, c
        dec a
        jr z, wb_pixel$
        res 0, c                        ; byte-aligned: HMMM, even width
        ld a, #0xd0
        jr wb_kind$
    wb_pixel$:
        ld c, #1                        ; an odd pixel: LMMM, opaque
        ld a, #0x90
    wb_kind$:
        ld (_g_VDP_Command + 14), a
        ld a, c
        ld (_g_VDP_Command + 8), a      ; NX
        push bc
        call _VDP_CommandSetupR32
        pop bc
        ld hl, (_s_Pos)                 ; position += part
        ld b, #0
        add hl, bc
        ld (_s_Pos), hl
        ld a, (_s_Left)                 ; left += part, 96 wraps to 0
        add a, c
        cp #96
        jr nz, wb_left$
        xor a
    wb_left$:
        ld (_s_Left), a
        jr wb_part$
    wb_next$:
        ld a, (_s_Take)                 ; row += take; height -= take
        ld b, a
        ld a, (_g_WaveBand + 14)
        add a, b
        ld (_g_WaveBand + 14), a
        ld a, (_g_WaveBand + 15)
        sub b
        ld (_g_WaveBand + 15), a
        jp wb_group$
    __endasm;
}

#ifdef WINGS_WAVES_C_REFERENCE
static u8 Mod96(i16 x)
{
    u16 v = (u16)(x + 30720), step = 49152u;
    do { if (v >= step) v -= step; step >>= 1; } while (step >= 96);
    return (u8)v;
}

void Waves_DrawBandC(void)
{
    const WaveBand* b = &g_WaveBand;
    u8 take, row = b->row, height = b->height, special = b->special;
    u16 left, part, seam, position, sx, sy, limit, start_left = Mod96((i16)b->start);
    while (height)
    {
        take = height;
        if (special && row < 9 && row + take > 9) take = 9 - row;
        position = b->start; left = start_left;
        while ((i16)(b->end - position) > 0)
        {
            sx = b->source_x + left; sy = b->source_y + row; limit = 96 - left;
            if (special && row >= 9) { sx = b->tail_x + left; sy = b->tail_y + row; }
            part = b->end - position; if (part > limit) part = limit;
            seam = 256 - (position & 255); if (part > seam) part = seam;
            if (row < 2)
                VDP_CommandLMMM(sx, sy, position & 255, b->dy + row, part, take, VDP_OP_TIMP);
            else if ((position & 1) || part == 1)
            {
                part = 1;
                VDP_CommandLMMM(sx, sy, position & 255, b->dy + row, 1, take, VDP_OP_IMP);
            }
            else
            {
                part &= 65534u;
                VDP_CommandHMMM(sx, sy, position & 255, b->dy + row, part, take);
            }
            position += part; left += part; if (left == 96) left = 0;
        }
        row += take; height -= take;
    }
}
#endif
