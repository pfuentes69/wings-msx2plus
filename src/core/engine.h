#ifndef WINGS_ENGINE_H
#define WINGS_ENGINE_H
#include <stdint.h>
#include "game.h"
#include "../msx/banking.h"

/* Fuel, oil, engine failure and instrument readings, recovered from the Amiga
 * executable (docs/research/amiga-fuel-oil.md). The original runs its logic
 * at 12.5 Hz (one tick per 4 PAL VBlanks): one tick is 12 steps of the port's
 * 150 Hz simulation clock. */
#define ENGINE_TICK_STEPS 12u
#define ENGINE_FUEL_FULL 192u     /* new plane / hold refuel */
#define ENGINE_OIL_FULL 128u      /* undamaged engine */
#define ENGINE_OIL_SEIZE 96u      /* the engine seizes below this */
#define ENGINE_OIL_WARN 116u      /* oil lamp blinks below this */
#define ENGINE_FUEL_WARN 64u      /* fuel lamp blinks at or below this */
#define ENGINE_FUEL_TICKS 28u     /* one fuel unit per 28 ticks of flight */
#define ENGINE_LEAK_TICKS 80u     /* a damaged engine loses one oil unit per 80 ticks */
#define ENGINE_OIL_BLINK 10u
#define ENGINE_FUEL_BLINK 8u
#define ENGINE_NEEDLE_FULL 22u    /* 23 original needle frames */
#define ENGINE_THROTTLE_FRAMES 6u /* oil reads higher while under power */

#define ENGINE_LAMP_OIL 1u
#define ENGINE_LAMP_FUEL 2u

typedef struct EngineState {
    uint8_t fuel_ticks;   /* ticks until the next fuel unit burns */
    uint8_t leak_ticks;   /* ticks until a damaged engine leaks an oil unit */
    uint8_t dry;          /* fuel went below zero (the original's fuel < 0) */
    uint8_t failed;       /* seized or out of fuel: no power, no guns */
    int8_t oil_blink, fuel_blink;
    uint8_t oil_needle, fuel_needle, lamps; /* what the instruments show */
    uint8_t random;
} EngineState;

/* Banked (segment 16): the main loop counts ENGINE_TICK_STEPS simulation
 * steps and calls Engine_Tick once per original tick. */
/* A new plane, or a visit to the hold: full tanks, undamaged, clocks reset. */
void Engine_Reset(EngineState* engine, SortieState* sortie) WINGS_BANKED;
/* One original 12.5 Hz tick. Fuel burns and oil leaks only while flying with
 * a running engine; instruments and lamps update while warnings are enabled
 * (flying or on deck). Returns 1 on the tick the engine fails. */
uint8_t Engine_Tick(EngineState* engine, SortieState* sortie, uint8_t flying, uint8_t throttle, uint8_t warnings) WINGS_BANKED;
/* Inject damage (enemy fire arrives in P3-P5; tests use it now). */
void Engine_Damage(EngineState* engine, SortieState* sortie, uint8_t oil, uint8_t fuel) WINGS_BANKED;
/* Instrument targets for the current state. */
uint8_t Engine_OilFrame(const SortieState* sortie, uint8_t throttle) WINGS_BANKED;
uint8_t Engine_FuelFrame(const SortieState* sortie) WINGS_BANKED;
#endif
