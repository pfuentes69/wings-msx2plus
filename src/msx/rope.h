#ifndef WINGS_ROPE_H
#define WINGS_ROPE_H
#include "core.h"
#include "banking.h"

/* The arresting rope during the cable arrest (Amiga 0x05c0), banked in
 * segment 21. The original draws one line, colour 3 (red), from the caught
 * cable on the deck (6 px below the plane's origin) to the hook (16 px
 * behind the plane, 5 px below the origin). The playfield strip under it is
 * saved and restored like the plane's background. */
/* Restore the strip saved on this page (skipped on a full page rebuild). */
void Rope_Restore(u8 page, u8 rebuilt) WINGS_BANKED;
/* Save the strip, then draw the rope from cable x to hook x (world pixels)
 * for a plane whose origin is on screen row origin_row. */
void Rope_Draw(u8 page, i16 cable, i16 hook, i16 origin_row, u16 camera, i16 limit) WINGS_BANKED;
#endif
