#include "rope.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "../generated/hellcat_frames.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_FLIGHT)

/* The original's colour 3 is red (12-bit 13,3,0); the 16-colour playfield
 * has no red, so the nearest entry, the dark orange-brown, is used. */
#define ROPE_COLOR 13

static u8 s_Valid[2], s_Width[2];
static u16 s_X[2], s_Y[2];

/* Save (or restore) the 2-row strip, splitting at the page seam. */
static void Strip(u8 page, u8 save)
{
    u16 ring = s_X[page], base = (u16)page * 256;
    u16 backup_x = page ? ROPE_BACKUP1_X : ROPE_BACKUP0_X, backup_y = page ? ROPE_BACKUP1_Y : ROPE_BACKUP0_Y;
    u8 offset = 0, width = s_Width[page], part;
    while (width)
    {
        part = width;
        if ((u16)(ring & 255) + part > 256) part = 256 - (ring & 255);
        if (save) VDP_CommandHMMM(ring & 255, base + s_Y[page], backup_x + offset, backup_y, part, 2);
        else VDP_CommandHMMM(backup_x + offset, backup_y, ring & 255, base + s_Y[page], part, 2);
        ring += part; offset += part; width -= part;
    }
}

void Rope_Restore(u8 page, u8 rebuilt) WINGS_BANKED
{
    if (s_Valid[page] && !rebuilt) Strip(page, 0);
    s_Valid[page] = 0;
}

/* A horizontal run of the rope in world x [from, to), clipped to the saved
 * strip [left, right). */
static void Run(u8 page, i16 from, i16 to, i16 row, i16 left, i16 right)
{
    u8 ring, width, part;
    if (from < left) from = left;
    if (to > right) to = right;
    if (to <= from) return;
    ring = from & 255; width = to - from;
    while (width)
    {
        part = width;
        if ((u16)ring + part > 256) part = 256 - ring;
        VDP_CommandLMMV(ring, (u16)page * 256 + row, part, 1, ROPE_COLOR, VDP_OP_IMP);
        ring += part; width -= part;
    }
}

void Rope_Draw(u8 page, i16 cable, i16 hook, i16 origin_row, u16 camera, i16 limit) WINGS_BANKED
{
    i16 low = cable < hook ? cable : hook, high = cable < hook ? hook : cable, half, left, right;
    /* Bresenham from the cable: the first half on the cable's row. */
    half = (high - low) / 2;
    left = low & ~1;
    if (left < (i16)camera + 8) left = (i16)camera + 8;
    right = (high + 2) & ~1;
    if (right > (i16)camera + 256) right = (i16)camera + 256;
    if (right <= left || origin_row + 6 >= limit || origin_row + 5 < 0) return;
    if (right - left > ROPE_BACKUP_WIDTH) right = left + ROPE_BACKUP_WIDTH;
    s_X[page] = left; s_Y[page] = origin_row + 5; s_Width[page] = right - left;
    Strip(page, 1);
    s_Valid[page] = 1;
    if (cable >= hook)
    {
        Run(page, cable - half, cable + 1, origin_row + 6, left, right);
        Run(page, hook, cable - half, origin_row + 5, left, right);
    }
    else
    {
        Run(page, cable, cable + half + 1, origin_row + 6, left, right);
        Run(page, cable + half + 1, hook + 1, origin_row + 5, left, right);
    }
}
