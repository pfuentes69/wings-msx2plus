/* Hand-written Z80 leaf helpers for Terrain_DrawColumn (resident).
 * SDCC compiled the per-row decode and cache comparison into IX-frame code
 * costing ~200 T-states per row; these run at ~45-80. Semantics are tested
 * on an emulated Z80 by tests/test_column_ops_z80.py.
 * sdcccall(1): first pointer in HL, second in DE, u8 result in A. */
#include "column_ops.h"

#ifndef TERRAIN_MAP_ROWS
#include "../generated/mission_tiles.h"
#endif
typedef char ColumnOpsRows[(TERRAIN_MAP_ROWS > 0 && TERRAIN_MAP_ROWS < 128) ? 1 : -1];

/* Expand (count, tile low, tile high) runs until TERRAIN_MAP_ROWS entries
 * are written. Runs are generated to sum exactly to the column height. */
void Column_Decode(const unsigned char* run, unsigned short* out) __naked
{
    __asm
        ld      c, #TERRAIN_MAP_ROWS
    column_decode_run$:
        ld      b, (hl)                 ; count
        inc     hl
        ld      a, (hl)                 ; tile low
        inc     hl
        push    hl
        ld      h, (hl)                 ; tile high
        ld      l, a
        ld      a, b
        or      a, a
        jr      z, column_decode_next$
        ld      a, c
        sub     a, b
        ld      c, a
    column_decode_write$:
        ld      a, l
        ld      (de), a
        inc     de
        ld      a, h
        ld      (de), a
        inc     de
        djnz    column_decode_write$
    column_decode_next$:
        pop     hl
        inc     hl
        ld      a, c
        or      a, a
        jr      nz, column_decode_run$
        ret
    __endasm;
}

/* Number of leading entries where a[i] == b[i]. The caller guarantees a
 * mismatch exists (a sentinel), so there is no length argument. */
unsigned char Column_Equal(const unsigned short* a, const unsigned short* b) __naked
{
    __asm
        ld      b, #0
    column_equal_loop$:
        ld      a, (de)
        cp      a, (hl)
        jr      nz, column_equal_done$
        inc     hl
        inc     de
        ld      a, (de)
        cp      a, (hl)
        jr      nz, column_equal_done$
        inc     hl
        inc     de
        inc     b
        jr      column_equal_loop$
    column_equal_done$:
        ld      a, b
        ret
    __endasm;
}
