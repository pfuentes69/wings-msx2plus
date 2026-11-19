#pragma once
#include "core.h"
#include "banking.h"
/* The front end's artwork from the original (docs/front-end-art.md),
 * segment 49 with its data. */

/* "THE END" (world shape gmov) over the play view on this page, as the
 * original shows it when the last plane is lost (0xaf7c). The page's rows
 * 212.. (the aircraft backups, unused once the game has ended) hold it on
 * the way. camera: the view's, as published. */
void Screens_DrawEnd(u8 page, u16 camera) WINGS_BANKED;
