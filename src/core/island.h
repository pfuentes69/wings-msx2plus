#ifndef WINGS_ISLAND_H
#define WINGS_ISLAND_H
#include <stdint.h>
#include "combat.h"
#include "engine.h"
#include "flight.h"
#include "../msx/banking.h"

/* Island ground targets (Amiga 0x2de8, 0x310c, 0x46dc, 0x4e18): see
 * docs/research/amiga-island-combat.md and docs/island-combat.md. The map
 * layout comes from src/generated/map_<map>/mission_island.h. */
#define ISLAND_MAX 4
#define ISLAND_MAX_HUTS 8
#define ISLAND_MAX_DUGOUTS 8
#define ISLAND_GARRISON 5
#define ISLAND_HUT_POINTS 150
#define ISLAND_DUGOUT_POINTS 200

/* Dugout guns (0x3d78, 0x4d50, 0x4f5c). The drawn shape: gun0..gun6
 * (0..6), with the muzzle flash gnf0..gnf6 (7..13), or the distant view's
 * flash (14), at altitude 20 over the dugout's anchor. */
#define ISLAND_GUN_NONE 255
#define ISLAND_GUN_FLASH 7
#define ISLAND_GUN_FAR 14
#define ISLAND_GUN_ALTITUDE 20
#define ISLAND_GUN_RANGE 512   /* the barrel is drawn within this |dx| */
#define ISLAND_GUN_REACH 448   /* and hits within this one */
#define ISLAND_GUN_FIRE_DELAY 360u  /* updates before a re-manned gun fires */

/* Island soldiers (0x1de4, 0x1e82, 0x3eee, 0x1a8c, 0x4fee). */
#define ISLAND_MAX_SOLDIERS 20        /* 5 per hut and dugout; mission A has 20 */
#define ISLAND_SOLDIER_FREE 0
#define ISLAND_SOLDIER_WALKING 1
#define ISLAND_SOLDIER_DYING 2
#define ISLAND_SOLDIER_DEAD 3
#define ISLAND_SOLDIER_ALTITUDE 12
#define ISLAND_SOLDIER_POINTS 25
#define ISLAND_REINFORCE_TICKS 200
/* g_Island.message: what the ticker should show (Message_Update takes it). */
#define ISLAND_MESSAGE_NONE 0
#define ISLAND_MESSAGE_CLEARED 1   /* "All enemy forces on island ... Bonus %ld points" */
#define ISLAND_MESSAGE_MISSION 2   /* ... + "Good work ! ... return to carrier ..." */
#define ISLAND_MESSAGE_PROMOTION 3 /* ... + "Congratulations! ... victory ceremony!!" (the rank's last mission) */
/* An object anchored at a covers [a - 16, a + 16): the impact column's
 * anchor within columns -1..+2 (0x4ae4). */
#define ISLAND_HIT(x, a) ((uint16_t)((x) - (a) + 16u) < 32u)

/* The original's 16-byte hut and dugout records, fields +8..+e. */
typedef struct IslandBuilding {
    uint8_t garrison;  /* soldiers inside */
    uint8_t waiting;   /* soldiers waiting to come out */
    uint8_t release;   /* ticks to the next one */
    uint8_t wrecked;   /* hut only */
    uint16_t c;        /* hut: smoke puffs left; dugout: fire delay */
    uint16_t e;        /* hut: smoke timer; dugout: reinforcement timer */
} IslandBuilding;

typedef struct IslandGun {
    uint16_t x;      /* the dugout's anchor */
    uint8_t frame;   /* ISLAND_GUN_* shape this update */
} IslandGun;

/* The original's 8-byte soldier record (+0 x, +2 direction, +3 frame, +4
 * death delay, +5 island, +6 state). */
typedef struct IslandSoldier {
    int16_t x;        /* walking: at update `base` (see Soldier_Now) */
    int8_t dir;       /* the direction byte: its sign is the way it walks */
    uint8_t frame;    /* 0..4 walking (at `base`), 5..7 dying, 8 dead */
    uint8_t delay;    /* walking: plain steps after `base`; dying: updates left on this frame */
    uint8_t state;    /* ISLAND_SOLDIER_* (bits 0..2); the island in bits 4..7 */
    uint8_t base;     /* walking: the update (g_Island.tick) x and frame are from */
} IslandSoldier;

typedef struct IslandState {
    IslandBuilding hut[ISLAND_MAX_HUTS], dugout[ISLAND_MAX_DUGOUTS];
    uint8_t soldiers[ISLAND_MAX];  /* soldiers left alive, inside or out */
    uint8_t guns[ISLAND_MAX];      /* AA guns left */
    IslandGun gun[ISLAND_MAX_DUGOUTS];
    uint16_t hits;                 /* ground-fire hits on the plane (diagnostic) */
    IslandSoldier soldier[ISLAND_MAX_SOLDIERS];
    uint16_t kills;                /* soldiers killed (the original's -$42c2) */
    uint8_t out;                   /* soldier slots in use (walking, dying, dead) */
    uint8_t alive;                 /* soldiers walking or dying */
    uint8_t tick;                  /* soldiers' updates, mod 256 */
    uint8_t wait;                  /* updates with nothing due (soldiers.c) */
    uint8_t gunwork;               /* a dugout is empty or holds fire: Island_Guns must run */
    uint8_t cleared;               /* islands cleared (bits): the flag comes down */
    uint8_t left;                  /* islands with targets not yet cleared (-$5c7b) */
    uint8_t message;               /* ISLAND_MESSAGE_* waiting for the ticker */
    uint16_t bonus;                /* the last island's bonus */
    uint8_t complete;              /* the mission is complete: return to the carrier */
    uint8_t sunk;                  /* the message is a ship's ". . . %s sunk": its kind + 1 */
} IslandState;
extern IslandState g_Island;

/* Banked (segment 23). */
void Island_Reset(void) WINGS_BANKED;
/* A bomb (or rocket) detonating on the ground at world x: wrecks a hut or
 * empties a manned dugout whose 32 px it falls in. Returns the points. */
uint16_t Island_Bombed(uint16_t x) WINGS_BANKED;
/* Island_Bombed for every bomb or rocket that hit the ground this weapon
 * tick, and a rocket's flash and ship guns; the points go to *score. */
void Island_Impacts(CombatState* combat, uint32_t* score) WINGS_BANKED;
/* One original 12.5 Hz tick: wrecked huts smoke, garrisons come out. */
void Island_Tick(void) WINGS_BANKED;
/* One original update of the soldiers: walking, dying (+25 each, into
 * *score), re-manning dugouts. */
uint8_t Island_Soldiers(uint32_t* score) WINGS_BANKED;   /* returns soldiers walking or dying */
/* src/core/soldiers.c (banked, segment 25). The islands' land extents,
 * for the walk: from Island_Reset. */
void Soldiers_Reset(void) WINGS_BANKED;
/* Walking soldiers within r px of world x start to die (0x1a8c): bombs and
 * cannon strikes r 16, the plane's crash r 8. */
void Island_Kill(int16_t x, uint8_t r) WINGS_BANKED;
/* A soldier's position and frame now, in g_SoldierX / g_SoldierFrame. */
extern int16_t g_SoldierX;
extern int16_t g_SoldierLandLow, g_SoldierLandHigh;   /* where soldiers can be */
extern uint8_t g_SoldierFrame;
void Soldier_Now(const IslandSoldier* s) WINGS_BANKED;
/* One original update of the dugout guns: choose each manned gun's shape
 * and, while the plane flies (flying) at world x, fire at it. A hit sparks
 * at the nose and wears the engine. Returns the number of guns drawn. */
uint8_t Island_Guns(const FlightState* flight, uint16_t world, uint8_t flying,
                    EngineState* engine, SortieState* sortie) WINGS_BANKED;
#endif
