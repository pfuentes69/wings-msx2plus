#include "rockets.h"
#include "rocket_move.h"
#include "flight.h"
#include "mission.h"
#include "ships.h"
#include "../generated/rocket_tables.h"
#include "xorshift.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_ROCKETS)

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

/* A free burst slot (bombs' slots, which bursts share), or 0. */
static CombatProjectile* Slot(CombatState* state)
{
    CombatProjectile* p = &state->projectile[COMBAT_GUN_COUNT];
    uint8_t i;
    for (i = COMBAT_GUN_COUNT; i < COMBAT_COUNT; ++i, ++p)
        if (!p->kind)
        {
            if (i >= state->count) state->count = i + 1;
            return p;
        }
    return 0;
}

/* Rockets (docs/rockets.md), after the original's 0x08fe (launch), 0x0aa6
 * (each tick) and 0x099a (aim), with its tables: sine Q15, tangent Q8 and
 * arctangent, 1024 steps a turn. */
static int16_t Sine(int16_t a)                       /* 0x5108 */
{
    uint16_t i = (uint16_t)a & 1023;
    if (i < 256) return s_Sine[i];
    if (i < 512) return s_Sine[512 - i];
    if (i < 768) return -s_Sine[i - 512];
    return -s_Sine[1024 - i];
}
#define Cosine(a) Sine((int16_t)((a) + 256))          /* 0x5104 */

/* 0x5ca6 for y, x >= 0: atan(y / x), 0..256. */
static uint16_t Arctangent(uint16_t y, uint16_t x)
{
    uint16_t small = y, big = x, r;
    CombatFixed n;
    if (y == x) return y ? 128 : 0;
    if (y > x) { small = x; big = y; }
    n.w.whole = (int16_t)small; n.w.fraction = 0;
    r = Rocket_Divide(&n, big);
    r = (r >> 8) + ((r >> 7) & 1);                     /* lsr #8, addx: rounded */
    return y > x ? 256 - s_Arctangent[r] : s_Arctangent[r];
}

/* The plane at the rocket's tick: 0x1a46 reads its x, altitude and facing. */
static int16_t s_PlaneX, s_PlaneAltitude;
static uint8_t s_PlaneLeft;

/* 0x1a46: where a line at angle a (< 0, down) from the plane meets the
 * sea, or 0. The divide is divu.w: on overflow the dividend stays. */
static int16_t Ground(int16_t a)
{
    CombatFixed dividend;
    uint16_t d;
    uint8_t i;
    if (a >= 0) return 0;
    if (a == -255) a = -254;
    i = (uint8_t)-a;
    /* The altitude x 256 as 16.16 words. */
    dividend.w.whole = (int16_t)((uint16_t)s_PlaneAltitude >> 8);
    dividend.w.fraction = (uint16_t)s_PlaneAltitude << 8;
    d = s_Tangent[i < 128 ? i : 127];
    d = (uint16_t)dividend.w.whole >= d ? dividend.w.fraction : Rocket_Divide(&dividend, d);
    return s_PlaneLeft ? s_PlaneX - (int16_t)d : s_PlaneX + (int16_t)d;
}

/* 0x099a, at ignition: a rocket fired downward is re-aimed at a ship gun
 * between the sea points of half its angle and that +-20 (live or not),
 * at the launch airspeed / 100. Its launch acceleration stays. */
static void Aim(CombatRocket* r)
{
    int16_t a = r->angle >> 1, centre, up, down, dx;
    uint16_t target;
    int32_t vx;
    if (a >= 0) return;
    if (!(centre = Ground(a)) || !(up = Ground(a + 20)) || !(down = Ground(a - 20))) return;
    target = Ships_Aim(centre, up);
    if (!target) target = Ships_Aim(centre, down);
    /* 0x115c tries the islands' AA guns next; maps a and j have none. */
    if (!target) return;
    dx = (int16_t)(target - (uint16_t)r->x.w.whole);
    if (dx < 0) dx = -dx;
    a = -(int16_t)Arctangent((uint16_t)r->y, (uint16_t)dx);
    vx = (int32_t)Cosine(a) * r->speed;
    r->vx.v = r->vx.v < 0 ? -vx : vx;
    r->vy.v = (int32_t)Sine(a) * r->speed;
}

static uint16_t s_RocketRandom = 0x2f4du;
uint8_t Rockets_Launch(CombatState* state, uint16_t x, uint16_t y, int16_t vx, int16_t vy, uint8_t left) WINGS_BANKED
{
    CombatRocket* r = state->rocket;
    int16_t angle, frame, step;
    uint8_t delay, i;
    for (i = 0; i < COMBAT_ROCKETS && r->live; ++i, ++r) {}
    if (i == COMBAT_ROCKETS) return 0;
    /* The plane's steps per original tick (Q8 per 1/150 s step x 12). */
    step = (int16_t)(((int32_t)(vx < 0 ? -vx : vx) * 12 + 128) >> 8);
    r->vx.w.whole = left ? -step : step; r->vx.w.fraction = 0;
    step = (int16_t)(((int32_t)(vy < 0 ? -vy : vy) * 12 + 128) >> 8);
    r->vy.w.whole = vy > 0 ? -step : step;   /* the port's y grows downward */
    r->vy.w.fraction = 0;
    r->x.w.whole = (int16_t)x; r->x.w.fraction = 0;
    r->y = (int16_t)(WINGS_FLIGHT_MAX_Y - y + 11);      /* 0x08ba: altitude + 11 */
    /* -$5bfa = path x 1024 / 18000 (2048 steps a turn); the rocket's angle
     * is half that. Acceleration 2 cos, 2 sin in 16.16. */
    angle = (int16_t)(((int32_t)state->path * 1024) / 18000);
    r->angle = (int8_t)(angle >> 1);
    r->speed = (uint8_t)((uint16_t)state->speed / 100);
    r->ay = Sine(r->angle);
    r->ax = r->vx.v < 0 ? -Cosine(r->angle) : Cosine(r->angle);
    /* Ignition after 4, 8 or 12 ticks, 8 twice as likely. */
    Xorshift(&s_RocketRandom);
    delay = (uint8_t)((s_RocketRandom << 1 | s_RocketRandom >> 15) & 12);
    r->delay = delay ? delay : 8;
    frame = 4 - (angle >> 5);
    if (frame < 0) frame = 0;
    if (frame > 9) frame = 9;
    r->frame = (uint8_t)frame + (r->vx.v < 0 ? 10 : 0);
    r->live = 1;
    ++state->rockets;
    return 1;
}

/* One original tick of a rocket (0x0aa6). The plane is at s_Plane*. */
static void Fly(CombatState* state, CombatRocket* r)
{
    CombatProjectile* p;
    int16_t d;
    uint8_t altitude;
    if (Rocket_Move(r)) { r->live = 2; Aim(r); Rocket_Move(r); }   /* ignition: aimed, then lit */
    /* Gone 1280 px from the plane (5760 in the distant view): the whole
     * pixels of |plane x - x| in 16.16 (the plane's x has no fraction). */
    d = s_PlaneX - r->x.w.whole;
    if (d > 0 || (!d && !r->x.w.fraction)) { if (r->x.w.fraction) --d; }
    else d = -d;
    if (d - 640 - (state->far ? 4480 : 0) > 640)
    {
        r->live = 0; --state->rockets;
        return;
    }
    if (r->y > 44) return;
    altitude = BurstAltitude(state, (uint16_t)r->x.w.whole);
    if (r->y > (int16_t)altitude) return;
    /* The burst: the sounds, the impact handler and the soldiers within
     * 16 px follow from its impact slot (Island_Impacts, Sound_Bursts). */
    r->live = 0; --state->rockets;
    if ((p = Slot(state))) Burst(state, p, (uint16_t)r->x.w.whole, altitude, COMBAT_ROCKET_BURST);
}

/* The torpedo (docs/torpedo.md), after the original's 0x088e (release),
 * 0x0b58 (fall), 0x0bf0..0x0d32 (meeting the surface) and 0x0d50 (run). */
uint8_t Torpedo_Launch(CombatState* state, uint16_t x, uint16_t y, int16_t vx, int16_t vy, uint8_t left) WINGS_BANKED
{
    CombatTorpedo* t = &state->torpedo;
    int16_t step;
    if (t->live) return 0;
    /* As a rocket: the plane's whole-pixel steps per original tick, its x,
     * its altitude + 11 (0x08ba). */
    step = (int16_t)(((int32_t)(vx < 0 ? -vx : vx) * 12 + 128) >> 8);
    t->vx.w.whole = left ? -step : step; t->vx.w.fraction = 0;
    step = (int16_t)(((int32_t)(vy < 0 ? -vy : vy) * 12 + 128) >> 8);
    t->vy.w.whole = vy > 0 ? -step : step;   /* the port's y grows downward */
    t->vy.w.fraction = 0;
    t->x.w.whole = (int16_t)x; t->x.w.fraction = 0;
    t->y = (int16_t)(WINGS_FLIGHT_MAX_Y - y + 11);
    t->left = left;
    t->sound = 0;
    t->live = TORPEDO_FALLING;
    return 1;
}

void Torpedo_Drop(CombatState* state, int16_t x, int16_t altitude, int16_t speed, int8_t facing) WINGS_BANKED
{
    CombatTorpedo* t = &state->enemy;
    t->vx.v = (int32_t)speed * 0x28f;
    if (facing < 0) t->vx.v = -t->vx.v;
    t->vy.v = 0;
    t->x.w.whole = x; t->x.w.fraction = 0;
    t->y = altitude + 15;
    t->left = facing < 0;
    t->sound = 0;
    t->live = TORPEDO_FALLING;
}

/* A torpedo ends in a burst at x, altitude, made by source (combat.h). */
static void TorpedoBurst(CombatState* state, CombatTorpedo* t, uint8_t altitude, int8_t source)
{
    CombatProjectile* p = Slot(state);
    t->live = 0;
    if (p) Burst(state, p, (uint16_t)t->x.w.whole, altitude, source);
}

static void Torpedo(CombatState* state, CombatTorpedo* t)
{
    int16_t altitude;
    uint8_t burst;
    if (t->live == TORPEDO_FALLING)
    {
        /* 0x0b58, the bomb's fall: vx -= trunc(whole vx / 10) whole pixels
         * (divs), x += vx; vy -= 0.375; the altitude keeps no fraction, so
         * it moves by floor(vy). */
        t->vx.w.whole -= t->vx.w.whole / 10;
        t->x.v += t->vx.v;
        t->vy.v -= 0x6000;
        altitude = t->y + t->vy.w.whole;
        burst = BurstAltitude(state, (uint16_t)t->x.w.whole);
        if (altitude > (int16_t)burst) { t->y = altitude; return; }
        t->y = burst;
        /* 0x0c7a..0x0d32: on a deck or land it explodes as a bomb does; on
         * the sea too, faster than 5 px a tick down; otherwise it runs. */
        if (s_Surface != MISSION_SEA || t->vy.w.whole < -5)
        {
            TorpedoBurst(state, t, burst, COMBAT_TORPEDO_BURST);
            return;
        }
        t->sound = 1;
        t->vx.v = t->vx.w.whole < 0 ? -TORPEDO_SPEED : TORPEDO_SPEED;
        t->life = TORPEDO_LIFE;
        t->live = TORPEDO_RUNNING;
    }
    /* 0x0d50, the same tick it meets the sea and each tick after: gone
     * without a trace when its life runs out; else it moves, and the
     * first column that is not sea stops it. Its wake is drawn by the
     * ships' splashes (Ships_Guns). */
    if (!--t->life) { t->live = 0; return; }
    t->x.v += t->vx.v;
    s_Surface = Mission_Surface((uint16_t)t->x.w.whole);
    if (s_Surface != MISSION_SEA)
    {
        /* On a hull, drawn as the sea explosion (+1f is the sea's 0). */
        if (s_Surface == MISSION_CARRIER) s_Surface = MISSION_SEA;
        TorpedoBurst(state, t, 12, COMBAT_TORPEDO_HIT);
    }
}

/* 0x1ae2: every torpedo within r px of x explodes, harmlessly (state 8,
 * no impact): the player's and the enemy's (0x1b24). Its burst is only
 * drawn. */
static void Kill(CombatState* state, CombatTorpedo* t, int16_t x, uint8_t r)
{
    int16_t d;
    if (!t->live) return;
    d = t->x.w.whole - x;
    if (d < 0) d = -d;
    if (d > r) return;
    s_Surface = t->live == TORPEDO_RUNNING ? MISSION_SEA : MISSION_ISLAND;
    TorpedoBurst(state, t, t->y < 12 ? 12 : (uint8_t)(t->y > 255 ? 255 : t->y), COMBAT_TORPEDO_DUD);
}
void Torpedo_Kill(CombatState* state, int16_t x, uint8_t r) WINGS_BANKED
{
    Kill(state, &state->torpedo, x, r);
    Kill(state, &state->enemy, x, r);
}

void Rockets_Step(CombatState* state, uint16_t x, uint16_t y, uint8_t left) WINGS_BANKED
{
    CombatRocket* r = state->rocket;
    uint8_t i;
    if (state->torpedo.live) Torpedo(state, &state->torpedo);
    if (state->enemy.live) Torpedo(state, &state->enemy);
    if (!state->rockets) return;
    s_PlaneX = (int16_t)x; s_PlaneAltitude = (int16_t)(WINGS_FLIGHT_MAX_Y - y); s_PlaneLeft = g_RocketLeft = left;
    for (i = COMBAT_ROCKETS; i; --i, ++r)
        if (r->live) Fly(state, r);
}
