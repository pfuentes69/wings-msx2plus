#pragma once
#include "core.h"
#include "banking.h"
#include "../core/game.h"
/* The front end's artwork from the original (docs/front-end-art.md),
 * segment 49 with its data. */

/* msx/screen_end.c (segment 50): "THE END" (world shape gmov) over the play view on this page, as the
 * original shows it when the last plane is lost (0xaf7c). The page's rows
 * 212.. (the aircraft backups, unused once the game has ended) hold it on
 * the way. camera: the view's, as published. */
void Screens_DrawEnd(u8 page, u16 camera) WINGS_BANKED;

/* Weapon selection (the original's panel over the carrier view, top
 * right): the panel with this line highlighted (0 rockets, 1 bombs,
 * 2 torpedo, top to bottom) on the page shown at this camera (its colours:
 * SCREENS_WEAPON). */
void Screens_WeaponPanel(u8 page, u16 camera, u8 line) WINGS_BANKED;
/* The highlight moves from one line to another (same page and camera). */
void Screens_WeaponLine(u8 page, u8 from, u8 to) WINGS_BANKED;
/* One weapon-selection update (first: the whole panel). */
void Screens_Weapons(u8 page, u16 camera, u8 first, const GameState* game) WINGS_BANKED;
/* msx/screen_end.c: the briefing full screen on black, drawn on this page
 * (its colours: SCREENS_BRIEF). The dashboard's rows are blacked:
 * Dashboard_Restore puts them back. */
void Screens_Briefing(u8 page, const GameState* game) WINGS_BANKED;
extern u8 g_BriefIslands, g_BriefShips;
/* msx/screen_end.c: rank selection full screen (the original's picture),
 * this line (0..6) highlighted (its colours: SCREENS_RANK); the highlight
 * moved. */
void Screens_Rank(u8 page, u8 line) WINGS_BANKED;
void Screens_RankLine(u8 page, u8 line) WINGS_BANKED;
/* msx/screen_end.c: the intro's screen (GAME_INTRO_*: the title, the
 * credits, the story's pages) full screen on this page (its colours:
 * SCREENS_TITLE for the title, else SCREENS_INTRO). */
void Screens_Intro(u8 page, u8 screen) WINGS_BANKED;

/* msx/screen_end.c: the colours a screen is shown in. Set as its page is
 * published (or before drawing on the page shown), so no screen is ever
 * seen in another's colours: the play area's palette (the line interrupt
 * reloads it each frame) and the VDP's at once, the dashboard's, the
 * column mask (off for the full-screen ones, which are not scrolled) and the
 * border's colour. */
#define SCREENS_PLAY   0   /* the play's palettes, the mask on */
#define SCREENS_WEAPON 1   /* the play's, colours 12..15 lent to the weapon panel */
#define SCREENS_BRIEF  2   /* the briefing's over the play area, black */
#define SCREENS_RANK   3   /* rank selection's over the whole screen */
#define SCREENS_TITLE  4   /* the intro's title over the whole screen */
#define SCREENS_INTRO  5   /* the intro's credits and story */
void Screens_Palette(u8 which) WINGS_BANKED;
