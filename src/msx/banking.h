#pragma once
/* Mission ROM code banking (ASCII8). See docs/rom-banking.md.
 *
 * Window 0 (4000h), 1 (6000h) and 2 (8000h) hold resident segments 0..2.
 * Window 1 is borrowed by Scenery_Read for data and always restored.
 * Window 3 (A000h) holds switchable code: segment 3 at boot, then whichever
 * segment the last banked call selected. Interrupt code must stay resident.
 *
 * A banked module places all its code and constants in one segment with
 * WINGS_CODE_SEGMENT and marks its public functions WINGS_BANKED. SDCC
 * routes those calls through ___sdcc_bcall_ehl, which restores the caller's
 * window-3 segment on return. Never hand out pointers to a banked module's
 * constants, and never call a banked function through a function pointer.
 *
 * mission-flight.js reads the WINGS_SEGMENT_* values below to link each
 * segment at (segment << 16) | A000h; tools/check_rom_layout.py verifies it. */

#define WINGS_SEGMENT_HUD 3     /* dashboard, weapons, arresting rope */
#define WINGS_SEGMENT_SCENE 16  /* menu, ship, carrier elevator, engine, landing */
#define WINGS_SEGMENT_FLIGHT 21 /* flight model, wave strip */
#define WINGS_SEGMENT_EFFECTS 22 /* the smoke path: drawing and its frame tables */
#define WINGS_SEGMENT_COMBAT 23 /* weapons, island targets */
#define WINGS_SEGMENT_MISSION 25 /* island soldiers, island cleared, messages (24 is the map data) */
#define WINGS_SEGMENT_SOUND 26  /* MSX-MUSIC: detection, its driver and effects (copied into RAM) */
#define WINGS_SEGMENT_GAME 27   /* the game state: phases, rank, missions, lives (core/game.c) */
#define WINGS_SEGMENT_SHIPS 28  /* enemy ships (core/ships.c) */
#define WINGS_SEGMENT_ROCKETS 29 /* rockets (core/rockets.c) and their tables */
#define WINGS_SEGMENT_PATCH 30  /* terrain column remap and band repaint (msx/terrain_patch.c), engine smoke (core/smoke.c) */
#define WINGS_SEGMENT_PLANES 31 /* enemy planes (core/planes.c) */
#define WINGS_SEGMENT_FIGHTERS 48 /* enemy fighters (core/fighters.c); banks 32.. hold map data, 48 is clear of it */
#define WINGS_SEGMENT_SCREENS 49 /* the weapon panel's artwork and its drawing (msx/screens.c, generated/screens_art.c) */
#define WINGS_SEGMENT_SCREEN_END 50 /* "THE END": its artwork and drawing (msx/screen_end.c, generated/screen_end_art.c) */

#if defined(WINGS_BANKED_CODE) && defined(__SDCC)
#define WINGS_BANKED __banked
#define WINGS_PRAGMA(text) _Pragma(#text)
#define WINGS_CODE_SEGMENT_(segment) WINGS_PRAGMA(codeseg SEG##segment)
#define WINGS_CODE_SEGMENT(segment) WINGS_CODE_SEGMENT_(segment)
#else
#define WINGS_BANKED
#define WINGS_CODE_SEGMENT(segment)
#endif
