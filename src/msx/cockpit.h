#pragma once
#include "core.h"
#include "banking.h"
#include "../generated/cockpit_art.h"

/* The pilot's window (docs/cockpit.md): the original's cockpit view (0x417e),
 * the ground ahead in 11 depth bands of pre-drawn shapes. A scene (what the
 * window shows, from the plane's place, altitude and facing) is composed
 * into a buffer in VRAM when it changes, and copied to each page that does
 * not show it yet. */
typedef struct CockpitState {
    u8 scene[COCKPIT_SCENE_BYTES];   /* what the buffer holds (layout: tools/convert_cockpit.py scene) */
    u8 generation;                   /* the buffer's picture; 255: none yet */
    u8 shown[2];                     /* the picture each page shows; 255: none */
} CockpitState;
extern CockpitState g_Cockpit;

/* The shapes into their VRAM slots (at boot, from bank COCKPIT_BANK). */
void Cockpit_Load(void) WINGS_BANKED;
/* The window on this page for the plane at world x, y (its row: altitude
 * WINGS_FLIGHT_MAX_Y - y), facing; with the torpedo plane's arrow. Returns
 * the picture's generation. */
u8 Cockpit_Draw(u8 page, u16 x, u16 y, u8 facing_left) WINGS_BANKED;
/* In idle time: a changed scene composed into the buffer (1), or nothing to
 * do (0). Without idle time, Cockpit_Draw composes it after a couple of
 * renders. */
u8 Cockpit_Work(void) WINGS_BANKED;
