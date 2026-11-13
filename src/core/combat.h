#ifndef WINGS_COMBAT_H
#define WINGS_COMBAT_H
#include <stdint.h>
#include "game.h"

#define COMBAT_FIRE 1
#define COMBAT_SECONDARY 2
#define COMBAT_BOMB COMBAT_SECONDARY
#define COMBAT_GUN_COUNT 2
/* Sixteen bomb slots cover the 100-tick lifetime at four releases/second. */
#define COMBAT_COUNT 18
#define COMBAT_ROUND 1
#define COMBAT_FALLING_BOMB 2
#define COMBAT_IMPACT 3
#define COMBAT_SPLASH 4

/* Unsigned Q2 world positions, signed Q2 velocity per 25 Hz weapon tick.
 * Parameters are authored for this prototype, not recovered Amiga physics. */
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
} CombatState;

void Combat_Reset(CombatState* state);
/* Called on the same 150 Hz fixed clock as flight; advances weapons every
 * six ticks. Both weapons repeat while held; bombs average four per second. */
void Combat_Step(CombatState* state, SortieState* sortie, uint16_t x, uint16_t y,
                 int16_t vx, int16_t vy, uint8_t left, uint8_t controls);

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
        state->secondary_cooldown || state->count>COMBAT_GUN_COUNT ||
        state->projectile[0].kind || state->projectile[1].kind;
}
static inline uint8_t Combat_Clock(CombatState* state, uint8_t controls)
{
    if (controls & COMBAT_BOMB) state->secondary_pending = 1;
    return Combat_Tick(state);
}
void Combat_Advance(CombatState* state, SortieState* sortie, uint16_t x, uint16_t y,
                    int16_t vx, int16_t vy, uint8_t left, uint8_t controls);
#endif
