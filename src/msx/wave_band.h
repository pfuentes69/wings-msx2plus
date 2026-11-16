#ifndef WINGS_MSX_WAVE_BAND_H
#define WINGS_MSX_WAVE_BAND_H
#include "core.h"

/* One band of the animated wave strip (src/msx/waves.c): rows row ..
 * row + height - 1 of the 96-px texture, tiled from world x start to end
 * (exclusive, signed) on the ring page. Rows 0..1 are copied transparent;
 * below them byte-aligned spans use HMMM and odd pixels 1-px LMMMs. On the
 * special frame (every 4th) rows from 9 come from the tail piece. */
typedef struct WaveBand {
    u16 source_x, source_y;   /* the texture frame's top-left in VRAM */
    u16 tail_x, tail_y;       /* the special frame's tail piece; tail_y less 9 */
    u16 start, end;           /* world x, signed */
    u16 dy;                   /* VRAM row of band row 0: page * 256 + 161 - heave */
    u8 row, height, special;  /* row and height are used up by the call */
} WaveBand;
extern WaveBand g_WaveBand;

/* Issue the band's VDP commands (Z80; segment 21, called from waves.c). */
void Waves_DrawBand(void);
#ifdef WINGS_WAVES_C_REFERENCE
/* The C it replaced, for tests/test_wave_band_z80.py. */
void Waves_DrawBandC(void);
#endif
#endif
