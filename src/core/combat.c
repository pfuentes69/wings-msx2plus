#include "combat.h"
#include "flight.h"
#include "mission.h"
#if WINGS_WORLD_WIDTH > 8191
#error Combat Q2 coordinates require a world no wider than 8191 pixels
#endif

/* Authored Q2 shot vectors for the ten original pitch poses. */
static const int8_t s_AimX[10]={12,24,34,46,48,46,42,34,24,12};
static const int8_t s_AimY[10]={-46,-42,-34,-12,0,12,24,34,42,46};

void Combat_Reset(CombatState* state)
{
    uint8_t i;
    for (i = 0; i < COMBAT_COUNT; ++i)
    {
        state->projectile[i].x = state->projectile[i].y = 0;
        state->projectile[i].vx = state->projectile[i].vy = 0;
        state->projectile[i].life = state->projectile[i].kind = 0;
    }
    state->phase = state->cooldown = state->secondary_cooldown = state->secondary_pending = 0;
    state->primary_pending = state->secondary_phase = 0;
    state->count = COMBAT_GUN_COUNT; state->aim_pitch=4;
    state->shots_fired = state->secondary_fired = state->impacts = 0;
}

static void Advance(CombatState* state, CombatProjectile* p)
{
    int16_t next;
    uint16_t floor;
    uint8_t surface;
    if (!p->kind) return;
    if (!--p->life) { p->kind = 0; return; }
    if (p->kind >= COMBAT_IMPACT) return;
    next = (int16_t)p->x + p->vx;
    if (next < 0 || (uint16_t)next >= (WINGS_WORLD_WIDTH * 4u)) { p->kind = 0; return; }
    p->x = next;
    if (p->kind == COMBAT_FALLING_BOMB && p->vy < 64) p->vy += 4;
    next = (int16_t)p->y + p->vy;
    if (next < 0) { p->kind = 0; return; }
    p->y = next;
    // Flat training surfaces only: visual deck is 32 pixels above sea/soil.
    // This is not the original collision solver or the carrier landing model.
    if (p->y < 1168u * 4) return;
    surface = Mission_Surface(p->x >> 2);
    floor = surface == MISSION_CARRIER ? 1168u * 4 : 1200u * 4;
    if (p->y >= floor)
    {
        p->y = floor; p->life = 6;
        p->kind = surface == MISSION_SEA ? COMBAT_SPLASH : COMBAT_IMPACT;
        if (state->impacts != 65535u) ++state->impacts;
    }
}

void Combat_Advance(CombatState* state, SortieState* sortie, uint16_t x, uint16_t y,
                 int16_t vx, int16_t vy, uint8_t left, uint8_t controls)
{
    CombatProjectile* p;
    int16_t muzzle, muzzle_y;
    int8_t aim_x, aim_y;
    uint8_t i, fire = (controls & COMBAT_FIRE) || state->primary_pending;
    state->primary_pending=0;
    if (state->cooldown) --state->cooldown;
    if (state->secondary_cooldown) --state->secondary_cooldown;
    for (i = 0; i < state->count; ++i) Advance(state, &state->projectile[i]);
    while (state->count>COMBAT_GUN_COUNT && !state->projectile[state->count-1].kind) --state->count;
    if (fire && !state->cooldown)
    {
        for (i = 0; i < COMBAT_GUN_COUNT; ++i)
        {
            p = &state->projectile[i];
            if (p->kind) continue;
            aim_x=s_AimX[state->aim_pitch]; aim_y=s_AimY[state->aim_pitch];
            if (left) aim_x=-aim_x;
            muzzle=(int16_t)x+aim_x/2;
            muzzle_y=(int16_t)y-2+aim_y/2;
            if (muzzle<0 || (uint16_t)muzzle>=WINGS_WORLD_WIDTH) break;
            p->x = muzzle * 4u; p->y = (muzzle_y > 0 ? muzzle_y : 0) * 4u;
            p->vx = aim_x + vx * 6 / 64;
            p->vy = aim_y + vy * 6 / 64;
            p->life = 12; p->kind = COMBAT_ROUND;
            state->cooldown = 3;
            if (state->shots_fired != 65535u) ++state->shots_fired;
            break;
        }
    }
    if (state->secondary_pending || (controls & COMBAT_BOMB))
    {
        state->secondary_pending = 0;
        for (i=COMBAT_GUN_COUNT;i<state->count;++i)
            if (!state->projectile[i].kind) break;
        if (sortie->weapon==WEAPON_BOMBS && sortie->stock && !state->secondary_cooldown &&
            i<COMBAT_COUNT && x < WINGS_WORLD_WIDTH)
        {
            if (i==state->count) ++state->count;
            p = &state->projectile[i];
            state->secondary_cooldown=6;
            if (++state->secondary_phase==4) {state->secondary_phase=0;++state->secondary_cooldown;}
            p->x = x * 4u; p->y = (y+4) * 4u;
            p->vx = vx * 6 / 64; p->vy = vy * 6 / 64;
            p->life = 100; p->kind = COMBAT_FALLING_BOMB;
            --sortie->stock;
            if (state->secondary_fired != 65535u) ++state->secondary_fired;
        }
    }
}

#ifndef WINGS_P1_FLIGHT
void Combat_Step(CombatState* state, SortieState* sortie, uint16_t x, uint16_t y,
                 int16_t vx, int16_t vy, uint8_t left, uint8_t controls)
{
    if (Combat_Clock(state, controls)) Combat_Advance(state,sortie,x,y,vx,vy,left,controls);
}

#endif
