#ifndef WINGS_SHIPS_H
#define WINGS_SHIPS_H
#include <stdint.h>
#include "../msx/banking.h"
#include "flight.h"
#include "engine.h"
#include "combat.h"

/* Enemy ships (docs/research/amiga-ships.md, docs/rockets.md). Ships never
 * move; the map's ships and their guns come from the converter
 * (src/generated/map_<x>/mission_ships.h): the hull hit test, the guns
 * (barrels, fire at the plane, shell splashes), rocket hits on them and
 * their smoke, torpedo hits on the hull, sinking (docs/ship-sinking.md).
 * Not yet: launched planes. */

#define SHIP_NONE 255
#define SHIP_CARRIER 254     /* the player's carrier: 0x4a4e tries it last */
#define SHIP_MAX_GUNS 40     /* the most on a map: o has 37 */
#define SHIP_MAX 4           /* one of each kind; the carrier's hull after them */
#define SHIP_CARRIER_HITS 4  /* the player's carrier (+c) */
#define SHIP_SINK_BONUS 10   /* the sinking step that scores the bonus (0x1d04) */
#define SHIP_SINK_STEPS 120  /* the step at which the sea takes the ship (0x1d98) */
#define SHIP_GUN_POINTS 200
#define SHIP_GUN_SMOKE 50    /* puffs from a destroyed gun (+a) */

#define SHIP_SHOWN 16        /* barrels drawn at once */
#define SHIP_SPLASHES 6      /* splashes at once: the original keeps 21; the
                              * MSX cannot draw and erase more in a frame */
#define SHIP_GUN_SPLASHES 4  /* of them, shell splashes (the rest: the wake) */
#define SHIP_WAKE_LIFE 4     /* a wake splash: spl4 down to spl1 */
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
    uint8_t hull[SHIP_MAX + 1];  /* +c: torpedo hits left; the carrier's last */
    uint16_t hull_hits;     /* torpedo hits on hulls (diagnostic) */
    /* The sinking clock (0x1cd8), per ship: +14 steps taken (1 px each),
     * +16 ticks to the next, +18 the interval after it. */
    uint8_t step[SHIP_MAX], wait[SHIP_MAX], interval[SHIP_MAX];
    uint8_t sinking;        /* ships whose clock runs */
    uint8_t left;           /* enemy ships still to sink for the mission (-$5c8d) */
} ShipsState;
extern ShipsState g_Ships;
/* Bit i: ship i has gone under (step 120); its columns are sea for
 * Mission_Surface (generated, resident). */
extern uint8_t g_ShipsGone;

/* Banked. */
void Ships_Reset(void) WINGS_BANKED;
/* 0x4a4e: the ship whose hull covers x (its columns from H to the end,
 * inclusive), the player's carrier last; SHIP_NONE if none. A ship gone
 * under still counts: the original keeps its record. */
uint8_t Ships_Find(uint16_t x) WINGS_BANKED;
/* The deck's altitude (+e) of an enemy ship (not the carrier). */
uint8_t Ships_Deck(uint8_t ship) WINGS_BANKED;
/* 0x4986 for a rocket bursting over the sea or a deck at x: 0 when no hull
 * is there, COMBAT_SKY_WHITE over a hull, COMBAT_SKY_RED when it destroyed
 * a gun (the first live one within 16 px: +200). */
uint8_t Ships_Rocket(uint16_t x, uint32_t* score) WINGS_BANKED;
/* 0x4986 for a running torpedo striking at x: 0 when no hull is there,
 * else one hit off the hull (the sinking at 0 is the next step) and
 * COMBAT_SKY_RED. */
uint8_t Ships_Torpedo(uint16_t x) WINGS_BANKED;
/* 0x52ac: a splash at x (a ricochet on land), if the list has room: a shot-
 * down plane sliding (docs/enemy-planes.md). */
void Ships_AddSplash(int16_t x) WINGS_BANKED;
/* 0x11a6: the first gun, live or not, of an enemy ship with x between a and
 * b (either order, inclusive); 0 if none. */
uint16_t Ships_Aim(int16_t a, int16_t b) WINGS_BANKED;
/* Each original tick: the sinking clocks (0x1cae; a bonus goes to score),
 * and destroyed guns smoke (0x4c3e) while the plane flies. */
void Ships_Tick(uint8_t flying, uint32_t* score) WINGS_BANKED;
/* Once a presented frame (the original's render loop, 0x38d2): the
 * splashes age, a running torpedo leaves its wake, and while the plane
 * flies the live guns (0x4c3e) throw shell splashes near it (each
 * destroys a torpedo within 10 px), turn their barrels to it and fire
 * hit-scan rounds that damage the engine (0x4f5c). Returns the barrels
 * and splashes to draw. */
uint8_t Ships_Guns(const FlightState* flight, uint16_t world, uint8_t flying,
                   EngineState* engine, SortieState* sortie, CombatState* combat) WINGS_BANKED;
#endif
