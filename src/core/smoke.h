#ifndef WINGS_SMOKE_H
#define WINGS_SMOKE_H
#include <stdint.h>
#include "flight.h"
#include "../msx/banking.h"

/* Engine smoke from a damaged engine (Amiga 0x1bfc, 0x54e0, 0x0ee0): see
 * docs/flight-model.md. Positions are world pixels; y is the port's
 * screen-like world y (1200 = sea level). */
#define SMOKE_COUNT 8
#define SMOKE_STAGES 5       /* smk4 down to smk0 */
#define SMOKE_STAGE_FIRE 6   /* a hit's spark, smk5, then smk4..smk0 */
#define SMOKE_STAGE_TICKS 7  /* updates per stage */
typedef struct SmokePuff {
    uint16_t x, y;
    uint8_t xf, yf;    /* fractions */
    uint8_t vx, vy;    /* per tick: 1 + v/256 px right and up */
    uint8_t stage;     /* 6..1, 0 = free */
    uint8_t life;      /* updates left in this stage, 6..0 */
} SmokePuff;
extern SmokePuff g_Smoke[SMOKE_COUNT];

/* Banked (segment 30, with the terrain patches). */
void Smoke_Reset(void) WINGS_BANKED;
/* One original 12.5 Hz tick: advance the puffs, then (when emit) let an
 * engine with oil below 128 put out a puff at the nose. */
void Smoke_Tick(const FlightState* flight, uint16_t world, uint8_t oil, uint8_t emit) WINGS_BANKED;
/* A puff at world (x, y) if the pool has room (wrecked huts, 0x4e18). */
void Smoke_Emit(uint16_t x, uint16_t y) WINGS_BANKED;
/* A puff at world (x, y) starting at stage (1..SMOKE_STAGE_FIRE), if the
 * pool has room: enemy planes' hits and damage smoke. */
void Smoke_Puff(uint16_t x, uint16_t y, uint8_t stage) WINGS_BANKED;
/* A ground-fire hit (0x54e0 with effect type 6): a spark at the nose that
 * burns out into smoke, if the pool has room. */
void Smoke_Hit(const FlightState* flight, uint16_t world) WINGS_BANKED;
#endif
