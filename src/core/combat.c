#include "combat.h"
#include "flight.h"
#include "mission.h"
#include "ships.h"
#include "rockets.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_COMBAT)

/* Line of fire per original pitch pose, measured from the fb01..fb0a tracer
 * art (nearest pixel to the aircraft origin to the far tracer tip). The
 * flash overlay shows the same direction; tests recompute these values. */
static const uint8_t s_TracerX[10]={10,10,10,10,11,11,10,10,9,5};
static const int8_t s_TracerY[10]={-6,-4,-3,-3,0,3,5,7,8,9};

void Combat_Reset(CombatState* state) WINGS_BANKED
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
    state->flash = state->flash_ticks = 0;
    for (i = 0; i < COMBAT_ROCKETS; ++i) state->rocket[i].live = 0;
    state->rockets = state->rocket_tick = 0;
    state->sky_flash = state->sky_color = 0;
    state->plane_x = 0;
    state->torpedo.live = state->torpedo.sound = 0;
    state->enemy.live = state->enemy.sound = 0;   /* a new plane clears the enemy's too (0x3756) */
}

/* height <= COMBAT_GUN_RANGE and tracer runs <= 11 keep this in 16 bits. */
static uint16_t Reach(uint16_t height, uint8_t pitch)
{
    return (uint16_t)(height * s_TracerX[pitch]) / (uint8_t)s_TracerY[pitch];
}

/* Hit-scan cannon strike: no projectile travels. Like the original, only
 * downward fire within range of the surface produces a visible strike. */
static void Strike(CombatState* state, uint16_t x, uint16_t y, uint8_t left)
{
    CombatProjectile* p;
    uint16_t floor = 1200u, reach, target;
    uint8_t i, pitch = state->aim_pitch, surface;
    if (pitch > 9 || s_TracerY[pitch] <= 0 || y >= floor || floor - y > COMBAT_GUN_RANGE) return;
    reach = Reach(floor - y, pitch);
    /* World x is a ring read as signed: past the map's ends the line meets
     * the open sea (Mission_Surface is sea outside the map). */
    target = left ? x - reach : x + reach;
    surface = Mission_Surface(target);
    if (surface == MISSION_CARRIER)
    {
        // The deck stands 32 pixels above the sea: stop the line there.
        floor = 1168u;
        if (y >= floor) return;
        reach = Reach(floor - y, pitch);
        target = left ? x - reach : x + reach;
        surface = Mission_Surface(target);
        if (surface != MISSION_CARRIER) floor = 1200u;
    }
    for (i = 0; i < COMBAT_GUN_COUNT; ++i)
    {
        p = &state->projectile[i];
        if (p->kind) continue;
        p->x = target * 4u; p->y = floor * 4u;
        p->vx = p->vy = 0; p->life = 6;
        p->kind = surface == MISSION_SEA ? COMBAT_SPLASH : COMBAT_IMPACT;
        if (state->impacts != 65535u) ++state->impacts;
        return;
    }
}

/* The original's bomb (0x0b58), each 12.5 Hz tick: vx -= trunc(whole
 * pixels of vx / 10), x += vx; vy += 0.375 (down), y += vy. At the 25 Hz
 * weapon tick the Q2 velocity units are half-pixels per original tick:
 * gravity is 3/8 of a unit a tick, drag applies every second tick. */
static void Fall(CombatProjectile* p)
{
    uint8_t age = COMBAT_BOMB_LIFE - p->life, q = 0;
    int8_t v;
    p->vy += (uint8_t)(((age + 1) * 3) >> 3) - (uint8_t)((age * 3) >> 3);
    if (!(age & 1)) return;
    v = p->vx >> 1;                       /* whole pixels per original tick */
    if (v < 0) { while (v <= -10) { v += 10; ++q; } p->vx += 2 * q; }
    else { while (v >= 10) { v -= 10; ++q; } p->vx -= 2 * q; }
}

/* 0x0bf0: the altitude ordnance bursts at over x: 12 above the sea or an
 * island, 11 above a deck. The carrier's deck stands at 33 (as the port
 * lands on it); an enemy ship's at its +e less the bob (0x5714). */
static uint8_t s_Surface;
static uint8_t BurstAltitude(CombatState* state, uint16_t x)
{
    uint8_t ship;
    s_Surface = Mission_Surface(x);
    if (s_Surface != MISSION_CARRIER) return 12;
    ship = Ships_Find(x);
    if (ship == SHIP_NONE || ship == SHIP_CARRIER) return 44;
    return Ships_Deck(ship) - state->bob + 11;
}

/* A burst at x, drawn on the surface under it (12 px below the burst):
 * a splash on the sea, an impact on land or a deck. Bomb bursts use their
 * own slot; a rocket takes a free one. */
static void Burst(CombatState* state, CombatProjectile* p, uint16_t x, uint8_t altitude, int8_t source)
{
    p->x = x * 4u; p->y = (WINGS_FLIGHT_MAX_Y - altitude + 12) * 4u;
    p->vx = source; p->vy = 0; p->life = 6;
    p->kind = s_Surface == MISSION_SEA ? COMBAT_SPLASH : COMBAT_IMPACT;
    if (state->impacts != 65535u) ++state->impacts;
}

static void Advance(CombatState* state, CombatProjectile* p)
{
    int16_t next, x;
    uint8_t altitude;
    if (!p->kind) return;
    if (!--p->life) { p->kind = 0; return; }
    if (p->kind >= COMBAT_IMPACT) return;
    Fall(p);
    p->x += p->vx;   /* the ring wraps */
    next = (int16_t)p->y + p->vy;
    if (next < 0) { p->kind = 0; return; }
    p->y = next;
    /* 0x0bf0: it bursts 12 px above the sea or island (it falls through
     * huts and trees), or 11 above the deck. The burst is drawn on the
     * surface (32 px up on the carrier). */
    if (p->y < COMBAT_DECK_BURST_Y * 4) return;
    x = Combat_WorldX(state, p->x);
    altitude = BurstAltitude(state, (uint16_t)x);
    if (p->y >= (WINGS_FLIGHT_MAX_Y - altitude) * 4u) Burst(state, p, (uint16_t)x, altitude, 0);
}

void Combat_Advance(CombatState* state, SortieState* sortie, uint16_t x, uint16_t y,
                 int16_t vx, int16_t vy, uint8_t left, uint8_t controls) WINGS_BANKED
{
    CombatProjectile* p;
    uint8_t i, fire = (controls & COMBAT_FIRE) || state->primary_pending;
    state->primary_pending=0;
    state->plane_x = (int16_t)x;
    if (state->flash_ticks && !--state->flash_ticks) state->flash = 0;
    if (state->cooldown) --state->cooldown;
    if (state->secondary_cooldown) --state->secondary_cooldown;
    // Walk a pointer with a local count: SDCC 4.6.0 #16555 miscompiled the
    // indexed form, re-adding the count offset to HL every iteration and so
    // reading the loop bound from unrelated RAM (see docs/sdcc-pitfalls.md).
    for (i = state->count, p = state->projectile; i; --i, ++p) Advance(state, p);
    while (state->count>COMBAT_GUN_COUNT && !state->projectile[state->count-1].kind) --state->count;
    /* Rockets and the torpedo move on the original's 12.5 Hz tick: every
     * second call. */
    if ((state->rockets || state->torpedo.live || state->enemy.live) && (state->rocket_tick ^= 1))
    {
        Rockets_Step(state, x, y, left);
        /* A torpedo meeting the sea makes a splash (Sound_Bursts): count it
         * as an event the caller passes on. */
        if (state->torpedo.sound == 1 || state->enemy.sound == 1)
        {
            if (state->torpedo.sound == 1) state->torpedo.sound = 2;   /* Sound_Bursts clears it */
            if (state->enemy.sound == 1) state->enemy.sound = 2;
            if (state->impacts != 65535u) ++state->impacts;
        }
    }
    if (fire && !state->cooldown)
    {
        state->cooldown = 3;
        // Keep the overlay visible until one tick after the next shot is due.
        if (!state->flash) state->flash = 1;
        state->flash_ticks = 4;
        if (state->shots_fired != 65535u) ++state->shots_fired;
        Strike(state, x, y, left);
    }
    if (state->secondary_pending || (controls & COMBAT_BOMB))
    {
        state->secondary_pending = 0;
        for (i=COMBAT_GUN_COUNT;i<state->count;++i)
            if (!state->projectile[i].kind) break;
        if (sortie->weapon==WEAPON_ROCKETS && sortie->stock && !state->secondary_cooldown)
        {
            /* Held, rockets repeat at the bombs' rate (the user's observed
             * rate; docs/combat-prototype.md). */
            if (Rockets_Launch(state, x, y, vx, vy, left))
            {
                state->secondary_cooldown = 6;
                if (++state->secondary_phase==4) {state->secondary_phase=0;++state->secondary_cooldown;}
                --sortie->stock;
                if (state->secondary_fired != 65535u) ++state->secondary_fired;
            }
        }
        else if (sortie->weapon==WEAPON_TORPEDO && sortie->stock && !state->secondary_cooldown)
        {
            /* 0x088e: no altitude, speed or heading check at release. */
            if (Torpedo_Launch(state, x, y, vx, vy, left))
            {
                state->secondary_cooldown = 6;
                --sortie->stock;
                if (state->secondary_fired != 65535u) ++state->secondary_fired;
            }
        }
        else if (sortie->weapon==WEAPON_BOMBS && sortie->stock && !state->secondary_cooldown &&
            i<COMBAT_COUNT)
        {
            if (i==state->count) ++state->count;
            p = &state->projectile[i];
            state->secondary_cooldown=6;
            if (++state->secondary_phase==4) {state->secondary_phase=0;++state->secondary_cooldown;}
            p->x = x * 4u; p->y = (y+4) * 4u;
            /* At the plane's velocity (0x07f2): Q8 per 150 Hz step x 6 / 64. */
            p->vx = vx * 6 / 64; p->vy = vy * 6 / 64;
            p->life = COMBAT_BOMB_LIFE; p->kind = COMBAT_FALLING_BOMB;
            --sortie->stock;
            if (state->secondary_fired != 65535u) ++state->secondary_fired;
        }
    }
}

#ifndef WINGS_P1_FLIGHT
void Combat_Step(CombatState* state, SortieState* sortie, uint16_t x, uint16_t y,
                 int16_t vx, int16_t vy, uint8_t left, uint8_t controls) WINGS_BANKED
{
    if (Combat_Clock(state, controls)) Combat_Advance(state,sortie,x,y,vx,vy,left,controls);
}

#endif
