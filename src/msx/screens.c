#include "screens.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "../generated/screens_art.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_SCREENS)

#define END_X ((256 - END_PLATE_WIDTH) / 2)
#define END_Y 56

void Screens_DrawEnd(u8 page, u16 camera) WINGS_BANKED
{
    u8 row, x = (u8)camera + END_X, first;
    u16 base = (u16)page * 256;
    const u8* source = g_EndPlate;
    /* Into the page's spare rows as it is, then over the view without its
     * transparent (0) pixels, centred in the view: the page is a ring
     * scrolled by the camera, so the copy splits at its seam. */
    for (row = 0; row < END_PLATE_HEIGHT; ++row, source += END_PLATE_WIDTH / 2)
        VDP_WriteVRAM(source, (base + 212 + row) * 128, 0, END_PLATE_WIDTH / 2);
    first = (u16)x + END_PLATE_WIDTH > 256 ? (u8)(256 - x) : END_PLATE_WIDTH;
    VDP_CommandLMMM(0, base + 212, x, base + END_Y, first, END_PLATE_HEIGHT, VDP_OP_TIMP);
    if (first < END_PLATE_WIDTH)
        VDP_CommandLMMM(first, base + 212, 0, base + END_Y, END_PLATE_WIDTH - first, END_PLATE_HEIGHT, VDP_OP_TIMP);
    VDP_CommandWait();
}
