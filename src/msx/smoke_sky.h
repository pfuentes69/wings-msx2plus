#ifndef TERRAIN_UNIFORM_COLOR_ASM   /* the ROM: a field of g_Map (map_rom/mission_tiles.h) */
#define TERRAIN_UNIFORM_COLOR_ASM _g_TerrainUniformColor
#endif
#ifndef WINGS_SMOKE_SKY_H
#define WINGS_SMOKE_SKY_H
/* Whether a smoke-path shape's box lies over plain sky on its page, so one
 * fill erases it (smoke_erase.c, which alone includes this): in Z80, as
 * every erased shape tests it (the C cost ~600 T-states a tile;
 * tests/test_smoke_sky_z80.py). The including file defines, by these
 * names: s_SkyPtr (const u16*: the page's tile cache at the first column
 * and row), s_SkySlot (that column's ring slot, 0..31), s_SkyCols and
 * s_SkyRows (u8, >= 1). Columns follow the 32-slot ring. The C:
 *     for each column, for each row: tile = cached row;
 *         if (tile >= TERRAIN_TILE_COUNT || TERRAIN_TILE_COLOR(tile)) return 0;
 *     return 1;
 * that is, every tile is uniform with colour 0. */
typedef char SmokeSkyUniform[(TERRAIN_UNIFORM_COUNT <= 255 && TERRAIN_UNIFORM_COUNT <= TERRAIN_TILE_COUNT) ? 1 : -1];
static u8 AllSky(void) __naked
{
    __asm
        ld      hl, (_s_SkyPtr)
        ld      a, (_s_SkySlot)
        ld      c, a                    ; C = ring slot
        ld      a, (_s_SkyCols)
        ld      b, a                    ; B = columns left
    sky_col$:
        push    hl
        push    bc
        ld      a, (_s_SkyRows)
        ld      b, a
    sky_row$:
        ld      e, (hl)
        inc     hl
        ld      a, (hl)
        inc     hl
        or      a, a
        jr      nz, sky_no$             ; tile >= 256: not uniform
        ld      a, e
        cp      a, #TERRAIN_UNIFORM_COUNT
        jr      nc, sky_no$
        push    hl
        ld      d, #0
        ld      hl, #TERRAIN_UNIFORM_COLOR_ASM
        add     hl, de
        ld      a, (hl)
        pop     hl
        or      a, a
        jr      nz, sky_no$
        djnz    sky_row$
        pop     bc
        pop     hl
        ld      de, #TERRAIN_MAP_ROWS*2
        add     hl, de                  ; the entry of the next slot
        inc     c
        bit     5, c
        jr      z, sky_next$
        ld      c, #0                   ; the ring wraps to slot 0
        ld      de, #-(TERRAIN_MAP_ROWS*2*32)
        add     hl, de
    sky_next$:
        djnz    sky_col$
        ld      a, #1
        ret
    sky_no$:
        pop     bc
        pop     hl
        xor     a, a
        ret
    __endasm;
}
#endif
