#ifndef WINGS_COMBAT_H
#define WINGS_COMBAT_H
#include <stdint.h>
#include "game.h"
#include "../msx/banking.h"

#define COMBAT_FIRE 1
#define COMBAT_SECONDARY 2
#define COMBAT_BOMB COMBAT_SECONDARY
/* Slots 0..1 hold cannon strike effects. The original draws no travelling
 * cannon rounds: a per-pose flash/tracer overlay is drawn on the aircraft and
 * downward fire strikes the surface where the line of fire meets it. */
#define COMBAT_GUN_COUNT 2
/* Sixteen bomb slots, one more than the original's 15: four seconds of
 * releases at four a second, about a 100 px fall. */
#define COMBAT_COUNT 18
#define COMBAT_FALLING_BOMB 2
#define COMBAT_IMPACT 3
#define COMBAT_SPLASH 4

/* Unsigned Q2 world positions, signed Q2 velocity per 25 Hz weapon tick
 * (two units = one pixel per original 12.5 Hz tick). Bombs follow the
 * original (0x0b58): see docs/island-combat.md. */
typedef struct CombatProjectile {
    uint16_t x, y;
    int8_t vx, vy;
    uint8_t life, kind;
} CombatProjectile;

typedef struct CombatState {
    CombatProjectile projectile[COMBAT_COUNT];
    uint8_t phase, cooldown, secondary_cooldown, secondary_pending, primary_pending, secondary_phase;
    uint8_t count, aim_pitch; /* 0..9, same pitch convention as original aircraft poses. */
    uint16_t shots_fired, secondary_fired, impacts;
    /* Cannon flash: 0 none, else the overlay drawn next (1 = fa, 2 = fb).
     * Firing activates it; it expires flash_ticks weapon ticks after the
     * last shot. The renderer alternates 1/2 on every presented frame, as
     * the original alternates fa/fb on game frames. */
    uint8_t flash, flash_ticks;
} CombatState;

/* A bomb's life in weapon ticks: longer than any fall (6 s from the
 * ceiling). Its tumble pose follows its age. */
#define COMBAT_BOMB_LIFE 255
/* Detonation height above the sea (0x0bf0): 12, or the deck's 33 + 11. */
#define COMBAT_BURST_Y (1200u - 12u)
#define COMBAT_DECK_BURST_Y (1200u - 44u)

/* Cannon strikes need the surface within this height below the aircraft
 * (original executable: altitude < 0xa0 before computing a splash). */
#define COMBAT_GUN_RANGE 160

/* Banked (segment 23). */
void Combat_Reset(CombatState* state) WINGS_BANKED;
/* Called on the same 150 Hz fixed clock as flight; advances weapons every
 * six ticks. Both weapons repeat while held; bombs average four per second. */
void Combat_Step(CombatState* state, SortieState* sortie, uint16_t x, uint16_t y,
                 int16_t vx, int16_t vy, uint8_t left, uint8_t controls) WINGS_BANKED;

/* Keep the cheap clock inline so MSX callers only calculate Q8-to-Q2 flight
 * samples on actual weapon ticks, rather than passing them 150 times/second. */
static inline uint8_t Combat_Tick(CombatState* state)
{
    if (++state->phase != 6) return 0;
    state->phase = 0;
    return 1;
}
/* An empty, untriggered pool has no simulation changes to advance. Keep the
 * weapon clock running, but let callers avoid preparing unused flight samples. */
static inline uint8_t Combat_Required(const CombatState* state,uint8_t controls)
{
    return controls || state->primary_pending || state->secondary_pending || state->cooldown ||
        state->secondary_cooldown || state->count>COMBAT_GUN_COUNT || state->flash_ticks ||
        state->projectile[0].kind || state->projectile[1].kind;
}
static inline uint8_t Combat_Clock(CombatState* state, uint8_t controls)
{
    if (controls & COMBAT_BOMB) state->secondary_pending = 1;
    return Combat_Tick(state);
}
void Combat_Advance(CombatState* state, SortieState* sortie, uint16_t x, uint16_t y,
                    int16_t vx, int16_t vy, uint8_t left, uint8_t controls) WINGS_BANKED;
#endif
