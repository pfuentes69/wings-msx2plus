#ifndef WINGS_ISLAND_H
#define WINGS_ISLAND_H
#include <stdint.h>
#include "combat.h"
#include "../msx/banking.h"

/* Island ground targets (Amiga 0x2de8, 0x310c, 0x46dc, 0x4e18): see
 * docs/research/amiga-island-combat.md and docs/island-combat.md. The map
 * layout comes from src/generated/mission_island.h. */
#define ISLAND_MAX 4
#define ISLAND_MAX_HUTS 8
#define ISLAND_MAX_DUGOUTS 8
#define ISLAND_GARRISON 5
#define ISLAND_HUT_POINTS 150
#define ISLAND_DUGOUT_POINTS 200

/* The original's 16-byte hut and dugout records, fields +8..+e. */
typedef struct IslandBuilding {
    uint8_t garrison;  /* soldiers inside */
    uint8_t waiting;   /* soldiers waiting to come out */
    uint8_t release;   /* ticks to the next one */
    uint8_t wrecked;   /* hut only */
    uint16_t c;        /* hut: smoke puffs left; dugout: fire delay */
    uint16_t e;        /* hut: smoke timer; dugout: reinforcement timer */
} IslandBuilding;

typedef struct IslandState {
    IslandBuilding hut[ISLAND_MAX_HUTS], dugout[ISLAND_MAX_DUGOUTS];
    uint8_t soldiers[ISLAND_MAX];  /* soldiers left alive, inside or out */
    uint8_t guns[ISLAND_MAX];      /* AA guns left */
} IslandState;
extern IslandState g_Island;

/* Banked (segment 23). */
void Island_Reset(void) WINGS_BANKED;
/* A bomb (or rocket) detonating on the ground at world x: wrecks a hut or
 * empties a manned dugout whose 32 px it falls in. Returns the points. */
uint16_t Island_Bombed(uint16_t x) WINGS_BANKED;
/* Island_Bombed for every bomb that hit the ground this weapon tick; the
 * points go to *score. */
void Island_Impacts(const CombatState* combat, uint32_t* score) WINGS_BANKED;
/* One original 12.5 Hz tick: wrecked huts smoke. */
void Island_Tick(void) WINGS_BANKED;
#endif
