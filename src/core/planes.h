#ifndef WINGS_PLANES_H
#define WINGS_PLANES_H
#include <stdint.h>
#include "../msx/banking.h"
#include "engine.h"

/* Enemy planes (docs/research/amiga-enemy-planes.md, docs/enemy-planes.md):
 * 4 slots shared by fighters and torpedo planes, updated once per original
 * tick (0xe7d6) in the original's units. Step 1: the slots, spawning, the
 * speed step, motion, turns, the shape index, the torpedo-plane timer and
 * the torpedo plane's cruise and turns. Not yet: the drop, the player's gun,
 * the fighters' AI and fire. */

#define PLANES_MAX 4
#define PLANES_WRECKS 8
#define PLANES_LISTS_MAX 4
#define PLANES_PARKED_MAX 16
#define PLANES_LAUNCH_COOLDOWN 100
#define PLANE_KILL_POINTS 350
/* +0 state */
#define PLANE_FREE 0
#define PLANE_FLYING 2
#define PLANE_DOWN 4      /* shot down: falling, sliding */
#define PLANE_WRECK 16    /* burning on an island */
/* +2 behaviour */
#define PLANE_FIGHTER 1
#define PLANE_ATTACK 2
#define PLANE_ARMED 4     /* a torpedo plane still carrying its torpedo */
#define PLANE_TURNING 8
#define PLANE_DROPPED 16  /* a torpedo plane after the drop */
/* 0xe4d0 kinds */
#define PLANE_KIND_FIGHTER 0
#define PLANE_KIND_TORPEDO 1
/* The player's modes as the original's P.mode */
#define PLANES_PLAYER_FLYING 0
#define PLANES_PLAYER_DECK 1
#define PLANES_PLAYER_ENGINE_OUT 4
#define PLANES_PLAYER_CRASHED 8

#define PLANE_SPEED_MIN 900    /* -$50ac */
#define PLANE_SPEED_MAX 2600   /* -$50aa */
#define PLANE_HEALTH 240
#define PLANE_TURN_FRAMES 26
#define PLANE_SHAPE_TORPEDO 26 /* armed torpedo plane, level */
#define PLANE_SHAPE_RIGHT 28   /* + facing right */
#define PLANES_TIMER_NEW_PLANE 1350
#define PLANES_TIMER_DROP 500
#define PLANES_TIMER_FIRE 750
#define PLANES_SPAWN_DISTANCE 0x1800   /* 6144 px */

/* The enemy plane record (52 bytes at -$5dd4 in the original), by field. */
typedef struct Plane {
    uint8_t state;     /* +0 */
    uint8_t beh;       /* +2 */
    uint8_t rel;       /* +4: 1 behind the player, 3 ahead (same heading); 2 right, 4 left (opposite) */
    uint8_t hit;       /* +6 */
    int16_t health;    /* +8 */
    int16_t hits;      /* +a: gun hits to the next health loss */
    int16_t rank;      /* +c */
    int16_t t10;       /* +10: flee / overshoot timer */
    uint8_t firing;    /* +12 */
    int8_t facing;     /* +14: -1 left, +1 right */
    int16_t frame;     /* +16: turn frame 0..25 */
    int16_t t18;       /* +18: ticks to the next turn */
    int16_t rev;       /* +1a: turn reversals in a row */
    int16_t speed;     /* +1c */
    int16_t tspeed;    /* +1e */
    int16_t x;         /* +20 */
    int16_t vy;        /* +22: falling, 1/100 px */
    int16_t talt;      /* +24 */
    int16_t alt;       /* +26 */
    int16_t dist;      /* +28: |dx| to the player */
    uint8_t draws;     /* +2c: draw counter (the muzzle flash's phase) */
    uint8_t shape;     /* +30: 0..55, 0xd35a */
    int16_t sub;       /* +32: turn sub-step */
    uint8_t near, far; /* the shape's frames (smoke_draw.c: SMOKE_FRAME_PLANE.., SMOKE_FRAME_FAR_PLANE..) */
} Plane;

/* What the planes read of the player, after its move this tick. */
typedef struct PlanesPlayer {
    int16_t x, alt;
    int8_t facing;     /* -1 left, +1 right */
    uint8_t mode;      /* PLANES_PLAYER_* */
    uint8_t turn;      /* the player's turn frame 0..25 */
    int16_t speed;     /* airspeed */
    int16_t climb;     /* the commanded climb (-$5bfc): the gun hits only at 0 */
    uint8_t gun;       /* the fire flag (-$5c94): gun held, flying, not turning */
    int16_t hstep;     /* the horizontal step, px a tick (P +16) */
    EngineState* engine;   /* a fighter's fire damages them (0xde52) */
    SortieState* sortie;
} PlanesPlayer;

typedef struct PlanesState {
    Plane plane[PLANES_MAX];
    int16_t timer;     /* -$5f6a: ticks to the next torpedo plane (0: none due) */
    uint8_t fighters;  /* -$5e28: fighters airborne */
    uint8_t kills;     /* -$5c7f */
    uint8_t live;      /* slots in use (any state) */
    /* A drop this tick (0xe08c), for the caller to launch the torpedo:
     * the plane's x, altitude, speed and facing. */
    uint8_t drop;
    int16_t drop_x, drop_alt, drop_speed;
    int8_t drop_facing;
    /* Planes that came to rest on an island (0x0da6, -$5e24): x x facing,
     * drawn at altitude 4 for the rest of the mission. The original keeps
     * 40, unbounded; the port PLANES_WRECKS. */
    int16_t wreck[PLANES_WRECKS];
    uint8_t wrecks;
    /* Launches (0x1574): the cooldown all sources share, and each ship
     * list's planes left (they stand parked on the deck until launched). */
    int16_t cooldown;
    uint8_t left[PLANES_LISTS_MAX];
    /* The parked planes to draw (0x391e), refreshed each tick: x, altitude
     * less the ship's sink, facing left. */
    uint8_t parked;
    int16_t parked_x[PLANES_PARKED_MAX], parked_alt[PLANES_PARKED_MAX];
    uint8_t parked_left[PLANES_PARKED_MAX];
    /* The enemy sounds (0x21c6): any plane firing, the nearest one's
     * distance |dx| + |dalt| (65535: none). */
    uint8_t firing;
    uint16_t nearest;
    /* Ship lists with planes left (or launching): the tick has work even
     * with no plane in the air. Last: scripts read the fields above. */
    uint8_t lists;
} PlanesState;
extern PlanesState g_Planes;

/* The pilot window's arrow (0xf21a): for the first armed torpedo plane,
 * 1 (ltar) when the player is right of it or level, 2 (rtar) left; 0 none. */
static inline uint8_t Planes_Arrow(int16_t player_x)
{
    const Plane* e = g_Planes.plane;
    uint8_t i;
    for (i = 0; i < PLANES_MAX; ++i, ++e)
        if (e->state && (e->beh & 7) == PLANE_ARMED) return (int16_t)(player_x - e->x) >= 0 ? 1 : 2;
    return 0;
}

/* core/fighters.c (banked, segment 48): the lists' reset, a fighter's
 * behaviour for the tick (0xd9c6 / 0xdccc), and the launches (0x1574). */
void Fighters_Reset(void) WINGS_BANKED;
void Fighters_Behave(Plane* e, const PlanesPlayer* p) WINGS_BANKED;
void Fighters_Launch(int16_t px) WINGS_BANKED;
extern uint8_t g_PlanesFlee, g_PlanesParity;

/* Banked. A new game: all clear, kills too. A new mission: the slots. */
void Planes_NewGame(void) WINGS_BANKED;
void Planes_Reset(void) WINGS_BANKED;
/* A new plane on deck (0xb89a): the torpedo-plane timer restarts. */
void Planes_NewPlane(void) WINGS_BANKED;
/* 0xe4d0: a new plane in the last free slot; 0 if refused. */
uint8_t Planes_Spawn(uint8_t kind, int16_t x, int16_t alt, int8_t facing) WINGS_BANKED;
/* One original tick: the torpedo-plane timer (0xbc02), the update
 * (0xe7d6) and the player's gun (0xb682). fire: a fire input this tick;
 * carrier: the US carrier afloat. Points go to *score, planes at rest to
 * *kills. */
void Planes_Tick(const PlanesPlayer* player, uint8_t fire, uint8_t carrier,
                 uint32_t* score, uint16_t* kills) WINGS_BANKED;
#endif
