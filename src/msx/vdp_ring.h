#ifndef WINGS_MSX_VDP_RING_H
#define WINGS_MSX_VDP_RING_H
#include "core.h"

/* A VDP block copy onto a 256-px ring page (resident, Z80). The caller sets
 * g_VDP_Command's SX, SY, DY, NY, ARG and CMD; this sets DX = ring and
 * NX = width (1..256) and issues the command, split in two where it crosses
 * x 256: the second part continues the source at DX 0. */
void Vdp_RingCopy(u8 ring, u16 width);

/* Fill the fixed fields of a copy for Vdp_RingCopy. */
#define VDP_RING_SET(sx, sy, dy, ny, cmd) do { \
    g_VDP_Command.SX = (sx); g_VDP_Command.SY = (sy); g_VDP_Command.DY = (dy); \
    g_VDP_Command.NY = (ny); g_VDP_Command.ARG = 0; g_VDP_Command.CMD = (u8)(cmd); } while (0)
#endif
