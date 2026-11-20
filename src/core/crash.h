#ifndef WINGS_CRASH_H
#define WINGS_CRASH_H
#include <stdint.h>
#include "flight.h"
#include "../msx/banking.h"

/* The player's crash, after the original (docs/research/amiga-player-crash.md):
 * every loss goes through FLIGHT_DEAD (mode 4): the plane falls, then slides
 * on the surface, then sinks (FLIGHT_SINKING, mode 6) or lies burning
 * (FLIGHT_WRECK, mode 8) for CRASH_TICKS ticks, or until fire is held after
 * CRASH_SKIP_TICKS; then the next plane. */
#define CRASH_TICKS 150       /* 0xaf7c: 12 s */
#define CRASH_SKIP_TICKS 30   /* fire ends the wait after 2.4 s */
#define CRASH_BURST_TICKS 75  /* 0xaed8: explosions or water bursts for 6 s */

typedef struct CrashState {
    int16_t dx, dy;   /* this tick's motion in px (dy down), for Flight_Tick */
    uint8_t clock;    /* -$5558: ticks in mode 6 or 8 */
    uint8_t next;     /* -$5556: the clock of the next burst */
    uint8_t sink;     /* -$555a: ticks to the next pixel down */
    uint8_t depth;    /* px sunk below the surface: the plane is drawn lower
                       * (its altitude stays at the surface, so no altitude
                       * read anywhere goes negative) */
    uint8_t puff;     /* -$437a: the wreck's fire puff every 4 ticks */
} CrashState;
extern CrashState g_Crash;

/* Banked (segment 27). */
/* 0xba80: a flying plane touched the sea, the ground, scenery or a deck
 * outside the landing rules: a burst and a rocket-type impact (not on the
 * sea or a low deck), then mode 4 with its speed. */
void Crash_Contact(FlightState* flight, uint16_t world) WINGS_BANKED;
/* One original tick of modes 4, 6 and 8 (0xafba, 0xc78c, 0xc7c6): sets
 * g_Crash.dx/dy, the tick's motion. */
void Crash_Tick(FlightState* flight, uint16_t world) WINGS_BANKED;
#endif
