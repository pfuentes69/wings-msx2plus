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
 * 2 torpedo, top to bottom) on the page shown at this camera, and the play
 * palette's colours 12..15 lent to it (Screens_WeaponColours). */
void Screens_WeaponPanel(u8 page, u16 camera, u8 line) WINGS_BANKED;
/* The highlight moves from one line to another (same page and camera). */
void Screens_WeaponLine(u8 page, u8 from, u8 to) WINGS_BANKED;
/* 1: colours 12..15 of the play palette lent to the panel; 0: back. */
void Screens_WeaponColours(u8 lent) WINGS_BANKED;
/* One weapon-selection update (first: the whole panel and the colours). */
void Screens_Weapons(u8 page, u16 camera, u8 first, const GameState* game) WINGS_BANKED;
/* msx/screen_end.c: the briefing full screen on black (the original's
 * rank.iff frame and its values), drawn on this page; its palette on (1)
 * or the play's back (0). The dashboard's rows are blacked: Dashboard_Restore
 * puts them back. */
void Screens_Briefing(u8 page, const GameState* game) WINGS_BANKED;
void Screens_BriefingColours(u8 on) WINGS_BANKED;
extern u8 g_BriefIslands, g_BriefShips;
/* msx/screen_end.c: rank selection full screen (the original's picture),
 * this line (0..6) highlighted; the highlight moved; its palette over the
 * whole screen on (1) or the play's and dashboard's back (0). */
void Screens_Rank(u8 page, u8 line) WINGS_BANKED;
void Screens_RankLine(u8 page, u8 line) WINGS_BANKED;
void Screens_RankColours(u8 on) WINGS_BANKED;
