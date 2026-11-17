#ifndef WINGS_SHIPS_H
#define WINGS_SHIPS_H
#include <stdint.h>
#include "../msx/banking.h"

/* Enemy ships (docs/research/amiga-ships.md, docs/rockets.md). Ships never
 * move; the map's ships and their guns come from the converter
 * (src/generated/map_<x>/mission_ships.h). So far: the hull hit test, rocket
 * hits on the guns and the destroyed guns' smoke. */

#define SHIP_NONE 255
#define SHIP_CARRIER 254     /* the player's carrier: 0x4a4e tries it last */
#define SHIP_MAX_GUNS 40     /* the most on a map: o has 37 */
#define SHIP_GUN_POINTS 200
#define SHIP_GUN_SMOKE 50    /* puffs from a destroyed gun (+a) */

/* The gun records' +8, +a, +c: destroyed, smoke puffs left, ticks to the
 * next puff. */
typedef struct ShipsState {
    uint8_t down[SHIP_MAX_GUNS];
    uint8_t puffs[SHIP_MAX_GUNS];
    uint8_t timer[SHIP_MAX_GUNS];
    uint8_t smoking;        /* destroyed guns still smoking */
    uint16_t guns_down;     /* guns destroyed (diagnostic) */
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
#endif
