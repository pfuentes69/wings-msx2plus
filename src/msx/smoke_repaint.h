#ifndef WINGS_SMOKE_REPAINT_H
#define WINGS_SMOKE_REPAINT_H
/* One column of a smoke-path shape's repaint from the page's tile cache
 * (smoke_erase.c, RepaintTiles, which alone includes this): in Z80, one
 * VDP command per tile (the C cost ~1,000 T-states a tile before the VDP
 * setup; tests/test_smoke_repaint_z80.py). Rows are below 256, so bytes.
 * The including file defines, by these names: s_Cached (const u16*: the
 * cache at the first row), s_RepaintRow (that map row), s_Y8 (the first
 * VRAM row), s_Bottom8, s_Origin8 (VRAM row of map row 0), s_Page8,
 * s_Column (world x, for the decode), s_DecodedOnce, s_Decoded[]; the
 * caller sets the command's DX, NX = 8 and ARG = 0. Per tile, the C:
 *     next = min(origin + (row + 1) * 8, bottom); tile = *cached++;
 *     if (tile >= TERRAIN_TILE_COUNT) { decode the column once; tile = decoded[row]; }
 *     if (tile < TERRAIN_TILE_COUNT) {
 *         DY = page * 256 + y; NY = next - y;
 *         uniform: CLR = colour * 17, HMMV;
 *         else: SY = Terrain_TileY(tile) + (y - origin) - row * 8, SX = g_TileSourceX, HMMM;
 *         VDP_CommandSetupR32(); }
 *     y = next; ++row; while y < bottom. */
static void RepaintColumn(void) __naked
{
    __asm
    rc_loop$:
        ld      a, (_s_RepaintRow)      ; next = origin + (row + 1) * 8, at most bottom
        inc     a
        add     a, a
        add     a, a
        add     a, a
        ld      b, a
        ld      a, (_s_Origin8)
        add     a, b
        ld      b, a
        ld      a, (_s_Bottom8)
        cp      a, b
        jr      nc, rc_next$
        ld      b, a
    rc_next$:
        ld      a, b
        ld      (_s_Next8), a
        ld      hl, (_s_Cached)         ; tile = *cached++
        ld      e, (hl)
        inc     hl
        ld      d, (hl)
        inc     hl
        ld      (_s_Cached), hl
        ld      hl, #TERRAIN_TILE_COUNT - 1
        or      a, a
        sbc     hl, de
        jr      nc, rc_tile$            ; a tile id
        ld      a, (_s_DecodedOnce)     ; under an overlay: the tile from the map
        or      a, a
        jr      nz, rc_have$
        inc     a
        ld      (_s_DecodedOnce), a
        ld      hl, (_s_Column)
        ld      de, #_s_Decoded
        call    _Terrain_DecodeColumn
    rc_have$:
        ld      a, (_s_RepaintRow)
        ld      l, a
        ld      h, #0
        add     hl, hl
        ld      de, #_s_Decoded
        add     hl, de
        ld      e, (hl)
        inc     hl
        ld      d, (hl)
        ld      hl, #TERRAIN_TILE_COUNT - 1
        or      a, a
        sbc     hl, de
        jr      c, rc_skip$
    rc_tile$:
        ld      a, (_s_Y8)              ; DY = page * 256 + y
        ld      (_g_VDP_Command + 6), a
        ld      b, a
        ld      a, (_s_Page8)
        ld      (_g_VDP_Command + 7), a
        ld      a, (_s_Next8)           ; NY = next - y
        sub     a, b
        ld      (_g_VDP_Command + 10), a
        xor     a, a
        ld      (_g_VDP_Command + 11), a
        ld      a, d                    ; uniform: HMMV in its colour
        or      a, a
        jr      nz, rc_copy$
        ld      a, e
        cp      a, #TERRAIN_UNIFORM_COUNT
        jr      nc, rc_copy$
        ld      hl, #_g_TerrainUniformColor
        add     hl, de
        ld      a, (hl)
        ld      b, a
        add     a, a
        add     a, a
        add     a, a
        add     a, a
        add     a, b                    ; colour * 17
        ld      (_g_VDP_Command + 12), a
        ld      a, #VDP_CMD_HMMV
        jr      rc_issue$
    rc_copy$:
        ex      de, hl
        call    _Terrain_TileY          ; DE = the atlas row of the tile; g_TileSourceX
        ld      a, (_s_Origin8)         ; SY = it + (y - origin) - row * 8
        ld      b, a
        ld      a, (_s_Y8)
        sub     a, b
        ld      b, a
        ld      a, (_s_RepaintRow)
        add     a, a
        add     a, a
        add     a, a
        ld      c, a
        ld      a, b
        sub     a, c
        ld      l, a
        ld      h, #0
        add     hl, de
        ld      (_g_VDP_Command + 2), hl
        ld      a, (_g_TileSourceX)
        ld      (_g_VDP_Command + 0), a
        xor     a, a
        ld      (_g_VDP_Command + 1), a
        ld      a, #VDP_CMD_HMMM
    rc_issue$:
        ld      (_g_VDP_Command + 14), a
        call    _VDP_CommandSetupR32
    rc_skip$:
        ld      a, (_s_Next8)           ; y = next, ++row, while y < bottom
        ld      (_s_Y8), a
        ld      hl, #_s_RepaintRow
        inc     (hl)
        ld      b, a
        ld      a, (_s_Bottom8)
        cp      a, b
        ret     z
        jp      nc, rc_loop$
        ret
    __endasm;
}
#endif
