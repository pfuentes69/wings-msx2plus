#ifndef WINGS_MSX_MESSAGE_H
#define WINGS_MSX_MESSAGE_H
#include "core.h"
#include "banking.h"

/* The message ticker. The original scrolls its messages below the
 * dashboard; the port has no room there and uses a band at the top of the
 * play area instead (docs/island-combat.md). While a message runs, the top
 * lines show VRAM rows 0.. of the page (never scenery: it starts at row 24)
 * at their own horizontal scroll, the text (rows 1..12, the original's
 * font) entering on the right. Segment 25. */
#define MESSAGE_TEXT_MAX 180
/* Text rows 1..12, then sky down to the play area's own top lines under
 * its scroll, plus the 2 lines the split is requested early. */
#define MESSAGE_BAND(scroll) (15 + (scroll))
/* Start a message waiting in g_Island.message; advance the ticker by
 * vblanks * 2 px. Once per presented frame. */
void Message_Update(u8 vblanks) WINGS_BANKED;
/* While rendering a page: copy the text the other page wrote since (a VDP
 * block move; the whole ring after a rebuild cleared it) and set
 * g_MessageScroll[page], the text pixel at the band's right edge. */
void Message_Draw(u8 page, u8 rebuilt) WINGS_BANKED;
/* In the time left before the page is published: write the next piece of
 * text (one glyph at most, a few ms) into the page's band. Returns 0 when
 * the band is up to date. The page shows only what it holds, so with no
 * time to spare the ticker slows down instead of costing a frame. */
u8 Message_Work(u8 page) WINGS_BANKED;
extern u8 g_MessageActive;
extern u8 g_MessageWait;   /* updates before a waiting message starts (0: none counted) */
extern u16 g_MessageScroll[2];
#endif
