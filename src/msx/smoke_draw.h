#ifndef WINGS_MSX_SMOKE_DRAW_H
#define WINGS_MSX_SMOKE_DRAW_H
#include "core.h"
#include "banking.h"
#include "../generated/hellcat_frames.h"

/* Drawing the engine smoke and the dugout guns (banked, segment 22). Puffs are drawn behind the
 * plane and erased by repainting the terrain tiles under them (sky above
 * the terrain rows): no VRAM backup is needed. */
#define SMOKE_DRAWN_MAX 80   /* 8 puffs, 3 dugout guns, 16 soldiers, 15 rockets, 16 ship guns, 8 splashes, 4 planes and flashes, wrecks, parked */
typedef struct SmokeDrawn { u16 x; i16 row; u8 frame; } SmokeDrawn;
/* What each page shows: Smoke_Restore erases it, and the verification
 * reads the displayed page's list (the pixel oracle). */
extern SmokeDrawn g_SmokeDrawn[2][SMOKE_DRAWN_MAX];
extern u8 g_SmokeDrawnCount[2];

/* Erase the puffs drawn on this page (skipped on a full rebuild). Call
 * before the frame's new terrain columns. Returns 1 when the elevator's
 * columns were repainted (the elevator overlay must then redraw). */
/* smoke_erase.c (segment 30). */
u8 Smoke_Restore(u8 page, u8 rebuilt, u16 camera) WINGS_BANKED;
/* The clip each page was drawn with (Smoke_Draw), for Smoke_Restore. */
typedef struct SmokeClip { i16 left, right, top, limit; i8 heave; } SmokeClip;
extern SmokeClip g_SmokeClip[2];
/* Forget what both pages show (boot: RAM is not cleared; new plane). */
void Smoke_ClearPages(void) WINGS_BANKED;
/* Copy the smoke-path frames into their atlas places (boot). */
void Smoke_LoadPieces(void) WINGS_BANKED;
/* Draw the live puffs. shift: rows the plane is pushed down by the
 * near-view top clamp; heave: the carrier's vertical scroll (screen
 * positions stay fixed, as for aircraft and weapons); limit: first row not
 * to draw. g_SmokeDrawn rows are screen rows (before the heave). */
void Smoke_Draw(u8 page, u16 camera, u8 far, i16 shift, i8 heave, i16 limit) WINGS_BANKED;
#endif
