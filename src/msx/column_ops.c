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

/* The rest of Terrain_DrawColumn: walk a decoded column against the page's
 * tile cache and redraw each changed run of tiles with one VDP command.
 * Same behaviour as the C loop it replaced (kept in mission_streamer.c as
 * the reference under WINGS_TERRAIN_C):
 *
 *   row = 0
 *   loop: skip rows equal to the cache (the decoded sentinel stops it);
 *         if row >= ROWS return
 *         tile = decoded[0]; count = 1; color = g_MissionTileColors[tile]
 *         solid colour (color != 255): extend over equal tiles
 *         atlas tile: extend over tile+1, tile+2 ... up to g_MissionTileLimit
 *         below the playfield (y % 256 >= 172, a close-view pan): cache only
 *         height = count * 8, cut at playfield row 172
 *         HMMV x, y, 8, height, color * 17   or
 *         HMMM tileX, tileY, x, y, 8, height
 *         copy the run into the cache; row += count
 *
 * In: HL = cache (TERRAIN_MAP_ROWS words), DE = decoded column (plus the
 * 65534 sentinel), g_ColumnX = destination x (ring), g_ColumnY = y of row 0.
 * Writes MSXgl's g_VDP_Command and calls VDP_CommandSetupR32/R36 (which
 * clobber A, B, C, HL). tests/test_column_runs_z80.py checks it against a
 * model of the C loop on an emulated Z80. */
unsigned char g_ColumnX;
unsigned short g_ColumnY;
static unsigned char s_Row, s_Count, s_Color, s_Limit;
static unsigned short s_Tile;
#define COLUMN_CMD_HMMM 0xD0
#define COLUMN_CMD_HMMV 0xC0
void Column_Runs(unsigned short* cache, const unsigned short* decoded) __naked
{
    (void)cache; (void)decoded;
    __asm
        xor     a, a
        ld      (_s_Row), a
    column_runs_loop$:
        ; Skip rows equal to the cache: B counts them.
        ld      b, #0
    column_runs_equal$:
        ld      a, (de)
        cp      a, (hl)
        jr      nz, column_runs_differ$
        inc     hl
        inc     de
        ld      a, (de)
        cp      a, (hl)
        jr      nz, column_runs_differ_high$
        inc     hl
        inc     de
        inc     b
        jr      column_runs_equal$
    column_runs_differ_high$:
        dec     hl
        dec     de
    column_runs_differ$:
        ld      a, (_s_Row)
        add     a, b
        ld      (_s_Row), a
        cp      a, #TERRAIN_MAP_ROWS
        ret     nc
        ; y += skipped * 8
        push    hl
        ld      l, b
        ld      h, #0
        add     hl, hl
        add     hl, hl
        add     hl, hl
        ld      bc, (_g_ColumnY)
        add     hl, bc
        ld      (_g_ColumnY), hl
        ; tile = decoded[0]; color = g_MissionTileColors[tile]
        ex      de, hl                  ; HL = decoded
        ld      e, (hl)
        inc     hl
        ld      d, (hl)
        dec     hl
        ld      (_s_Tile), de
        push    hl                      ; [decoded][cache]
        ld      hl, #_g_MissionTileColors
        add     hl, de
        ld      a, (hl)
        ld      (_s_Color), a
        ld      b, #1                   ; count
        inc     a
        jr      z, column_runs_atlas$
        ; Solid colour: extend while decoded[count] == tile.
        pop     hl
        push    hl
        inc     hl
        inc     hl
    column_runs_solid$:
        ld      a, (_s_Row)
        add     a, b
        cp      a, #TERRAIN_MAP_ROWS
        jr      nc, column_runs_counted$
        ld      a, (hl)
        cp      a, e
        jr      nz, column_runs_counted$
        inc     hl
        ld      a, (hl)
        cp      a, d
        jr      nz, column_runs_counted$
        inc     hl
        inc     b
        jr      column_runs_solid$
    column_runs_atlas$:
        ; Atlas tile: extend while count < limit and decoded[count] == tile + count.
        ld      hl, #_g_MissionTileLimit
        add     hl, de
        ld      a, (hl)
        ld      (_s_Limit), a
        pop     hl
        push    hl
        inc     hl
        inc     hl
        inc     de                      ; expected = tile + 1
    column_runs_stack$:
        ld      a, (_s_Row)
        add     a, b
        cp      a, #TERRAIN_MAP_ROWS
        jr      nc, column_runs_counted$
        ld      a, (_s_Limit)
        cp      a, b
        jr      z, column_runs_counted$
        jr      c, column_runs_counted$
        ld      a, (hl)
        cp      a, e
        jr      nz, column_runs_counted$
        inc     hl
        ld      a, (hl)
        cp      a, d
        jr      nz, column_runs_counted$
        inc     hl
        inc     b
        inc     de
        jr      column_runs_stack$
    column_runs_counted$:
        ld      a, b
        ld      (_s_Count), a
        ; Panned below the playfield: update the cache, draw nothing.
        ld      a, (_g_ColumnY)
        cp      a, #172
        jp      nc, column_runs_cache$
        ld      a, b
        ; height = count * 8, cut at playfield row 172.
        add     a, a
        add     a, a
        add     a, a
        ld      c, a                    ; C = height
        ld      a, (_g_ColumnY)         ; y % 256
        add     a, c
        jr      c, column_runs_cut$
        cp      a, #173
        jr      c, column_runs_command$
    column_runs_cut$:
        ld      a, (_g_ColumnY)
        neg
        add     a, #172
        ld      c, a
    column_runs_command$:
        ld      hl, (_g_ColumnY)
        ld      (_g_VDP_Command + 6), hl  ; DY
        ld      a, (_g_ColumnX)
        ld      l, a
        ld      h, #0
        ld      (_g_VDP_Command + 4), hl  ; DX
        ld      l, #8
        ld      (_g_VDP_Command + 8), hl  ; NX
        ld      l, c
        ld      (_g_VDP_Command + 10), hl ; NY
        xor     a, a
        ld      (_g_VDP_Command + 13), a  ; ARG
        ld      a, (_s_Color)
        cp      a, #255
        jr      z, column_runs_copy$
        ld      c, a                    ; CLR = color * 17
        add     a, a
        add     a, a
        add     a, a
        add     a, a
        add     a, c
        ld      (_g_VDP_Command + 12), a
        ld      a, #COLUMN_CMD_HMMV
        ld      (_g_VDP_Command + 14), a
        call    _VDP_CommandSetupR36
        jr      column_runs_cache$
    column_runs_copy$:
        ld      de, (_s_Tile)
        ld      hl, #_g_MissionTileX
        add     hl, de
        ld      a, (hl)
        ld      (_g_VDP_Command + 0), a   ; SX
        xor     a, a
        ld      (_g_VDP_Command + 1), a
        ld      hl, #_g_MissionTileY
        add     hl, de
        add     hl, de
        ld      a, (hl)
        inc     hl
        ld      h, (hl)
        ld      l, a
        ld      (_g_VDP_Command + 2), hl  ; SY
        ld      a, #COLUMN_CMD_HMMM
        ld      (_g_VDP_Command + 14), a
        call    _VDP_CommandSetupR32
    column_runs_cache$:
        ; Copy the run into the cache; both pointers advance past it.
        pop     hl                      ; HL = decoded
        pop     de                      ; DE = cache
        ld      a, (_s_Count)
        ld      c, a
        ld      a, (_s_Row)
        add     a, c
        ld      (_s_Row), a
        ld      b, #0
        push    hl                      ; y += count * 8
        ld      l, c
        ld      h, b
        add     hl, hl
        add     hl, hl
        add     hl, hl
        push    de
        ld      de, (_g_ColumnY)
        add     hl, de
        ld      (_g_ColumnY), hl
        pop     de
        pop     hl
        sla     c                       ; bytes = count * 2
        ldir
        ex      de, hl                  ; HL = cache, DE = decoded
        jp      column_runs_loop$
    __endasm;
}

/* Mark the overlay's map rows first..last dirty in every ring column from
 * left & ~7 up to right (Z80: ~150 T-states a column; SDCC's per-column
 * function cost ~440 a call, 2 ms a frame over the carrier). */
DirtyRange g_DirtyRange;
static unsigned short s_ColBase, s_CacheBase;
static unsigned char s_Count;
/* The column stride, 2 * 19 bytes, is built from shifts below. */
typedef char DirtyRows19[TERRAIN_MAP_ROWS == 19 ? 1 : -1];
typedef char DirtyRangeLayout[sizeof(DirtyRange) == 7 ? 1 : -1];
void Terrain_DirtyOverlay(void) __naked
{
    __asm
        ; n = ((right + 7) >> 3) - (left >> 3) columns
        ld hl, (_g_DirtyRange + 2)
        ld de, #7
        add hl, de
        srl h
        rr l
        srl h
        rr l
        srl h
        rr l
        ex de, hl
        ld hl, (_g_DirtyRange + 0)
        ld a, l
        rrca
        rrca
        rrca
        and #31
        ld c, a                         ; c: the first ring column
        srl h
        rr l
        srl h
        rr l
        srl h
        rr l
        ex de, hl
        or a
        sbc hl, de
        bit 7, h
        ret nz
        ld a, l
        or a
        ret z
        ld b, a                         ; b: columns
        ld a, (_g_DirtyRange + 6)       ; rows: last - first + 1
        ld hl, #_g_DirtyRange + 5
        sub (hl)
        inc a
        ld (_s_Count), a
        ld hl, #_g_TerrainColumns
        ld de, #_g_TerrainCached
        ld a, (_g_DirtyRange + 4)
        or a
        jr z, dirty_page$
        ld hl, #_g_TerrainColumns + 64
        ld de, #_g_TerrainCached + 32 * TERRAIN_MAP_ROWS * 2
    dirty_page$:
        ld (_s_ColBase), hl
        ld a, (_g_DirtyRange + 5)       ; + first row
        add a, a
        add a, e
        ld e, a
        jr nc, dirty_first$
        inc d
    dirty_first$:
        ld (_s_CacheBase), de
        ld l, c                         ; + column * 38 bytes
        ld h, #0
        add hl, hl
        push de
        ld d, h
        ld e, l
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, de
        add hl, de
        add hl, de
        pop de
        add hl, de
    dirty_column$:
        push hl
        ld hl, (_s_ColBase)             ; the column's map column: invalid
        ld a, c
        add a, a
        add a, l
        ld l, a
        jr nc, dirty_col$
        inc h
    dirty_col$:
        ld (hl), #0xff
        inc hl
        ld (hl), #0xff
        pop hl
        push hl
        ld a, (_s_Count)
        ld e, a
    dirty_row$:
        ld (hl), #0xff
        inc hl
        ld (hl), #0xff
        inc hl
        dec e
        jr nz, dirty_row$
        pop hl
        ld de, #38
        add hl, de
        inc c
        ld a, c
        cp #32
        jr nz, dirty_next$
        ld c, #0
        ld hl, (_s_CacheBase)
    dirty_next$:
        djnz dirty_column$
        ret
    __endasm;
}
