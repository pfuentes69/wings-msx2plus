#ifndef WINGS_SHIPS_H
#define WINGS_SHIPS_H
#include <stdint.h>
#include "../msx/banking.h"
#include "flight.h"
#include "engine.h"

/* Enemy ships (docs/research/amiga-ships.md, docs/rockets.md). Ships never
 * move; the map's ships and their guns come from the converter
 * (src/generated/map_<x>/mission_ships.h): the hull hit test, the guns
 * (barrels, fire at the plane, shell splashes), rocket hits on them and
 * their smoke. Not yet: torpedo hits, sinking, launched planes. */

#define SHIP_NONE 255
#define SHIP_CARRIER 254     /* the player's carrier: 0x4a4e tries it last */
#define SHIP_MAX_GUNS 40     /* the most on a map: o has 37 */
#define SHIP_GUN_POINTS 200
#define SHIP_GUN_SMOKE 50    /* puffs from a destroyed gun (+a) */

#define SHIP_SHOWN 16        /* barrels drawn at once */
#define SHIP_SPLASHES 4      /* shell splashes at once: the original keeps 21; the
                              * MSX cannot draw and erase more in a frame */
#define SHIP_GUN_RISE 13     /* a barrel's origin above the deck (0x4caa) */
#define SHIP_SPLASH_LIFE 6   /* splash frames over the sea, 4 on land (0x52b0) */

/* A barrel shown this update: x, altitude (its origin), the ISLAND_GUN_*
 * frame (0..6, + ISLAND_GUN_FLASH firing, ISLAND_GUN_FAR distant). */
typedef struct ShipGunShown { uint16_t x; uint8_t altitude, frame; } ShipGunShown;
/* A shell splash (0x52b0): life counts down a frame an update; land: a
 * ricochet (ric0) instead of the water (spl1..spl6). */
typedef struct ShipSplash { int16_t x; uint8_t life, land; } ShipSplash;

/* The gun records' +8, +a, +c: destroyed, smoke puffs left, ticks to the
 * next puff. */
typedef struct ShipsState {
    uint8_t down[SHIP_MAX_GUNS];
    uint8_t puffs[SHIP_MAX_GUNS];
    uint8_t timer[SHIP_MAX_GUNS];
    uint8_t smoking;        /* destroyed guns still smoking */
    uint16_t guns_down;     /* guns destroyed (diagnostic) */
    ShipGunShown shown[SHIP_SHOWN];
    uint8_t shown_count;
    ShipSplash splash[SHIP_SPLASHES];
    uint8_t splashes;       /* splashes alive */
    uint16_t nearest;       /* |dx| of the nearest gun firing (the sound), 65535 none */
    uint16_t hits;          /* hits on the plane (diagnostic) */
    uint8_t present;        /* the map has enemy ships */
} ShipsState;
extern ShipsState g_Ships;

/* Banked. */
void Ships_Reset(void) WINGS_BANKED;
/* 0x4a4e: the ship whose hull covers x (its columns from H to the end,
 * inclusive), the player's carrier last; SHIP_NONE if none. */
uint8_t Ships_Find(uint16_t x) WINGS_BANKED;
/* The deck's altitude (+e) of an enemy ship (not the carrier). */
uint8_t Ships_Deck(uint8_t ship) WINGS_BANKED;
/* 0x4986 for a rocket bursting over the sea or a deck at x: 0 when no hull
 * is there, COMBAT_SKY_WHITE over a hull, COMBAT_SKY_RED when it destroyed
 * a gun (the first live one within 16 px: +200). */
uint8_t Ships_Rocket(uint16_t x, uint32_t* score) WINGS_BANKED;
/* 0x11a6: the first gun, live or not, of an enemy ship with x between a and
 * b (either order, inclusive); 0 if none. */
uint16_t Ships_Aim(int16_t a, int16_t b) WINGS_BANKED;
/* Each original tick: destroyed guns smoke (0x4c3e), while the plane flies. */
void Ships_Tick(uint8_t flying) WINGS_BANKED;
/* Once a presented frame (the original's render loop, 0x38d2), the live
 * guns (0x4c3e) while the plane flies: shell
 * splashes near it, the barrels that follow it, hit-scan fire that damages
 * the engine (0x4f5c). Returns the barrels and splashes to draw. */
uint8_t Ships_Guns(const FlightState* flight, uint16_t world, uint8_t flying,
                   EngineState* engine, SortieState* sortie) WINGS_BANKED;
#endif
