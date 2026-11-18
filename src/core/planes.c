#include "planes.h"
#include "flight.h"
#include "xorshift.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_PLANES)

/* Enemy planes, from the pseudo-code in docs/research/amiga-enemy-planes.md
 * (addresses are the Amiga executable's). Every value is the original's
 * word; comparisons are signed. */

PlanesState g_Planes;

/* The US carrier's landing range, L and R (-$5c02 / -$5c00, 0xb7bc): its
 * hull x 4, 16 px in at each end. The hull is CARRIER_X - 440 ..
 * CARRIER_X + 335 inclusive (mission_ships.h SHIP_CARRIER_LEFT/RIGHT). */
#define CARRIER_L ((int16_t)(CARRIER_X - 440u + 16u))
#define CARRIER_R ((int16_t)(CARRIER_X + 336u - 16u))

/* Horizontal speed factor x 100 by turn frame (-$54f2, as flight_model.c). */
static const uint8_t s_TurnFactor[PLANE_TURN_FRAMES] = {
    100, 98, 95, 91, 86, 81, 75, 70, 60, 50, 40, 30, 23, 20, 0, 5, 25, 45, 60, 70, 75,
    81, 86, 91, 95, 98};
/* Altitude step by |target - altitude| / 20 (-$4e06). */
static const uint8_t s_AltStep[6] = {1, 2, 2, 3, 4, 5};

static uint16_t s_Random;   /* seeded by Planes_NewGame: no initialisers in a banked module */
/* rand(n) (0xcac8): 0..n-1. The original's source is the beam position. */
static uint8_t Rand(uint8_t n)
{
    return (uint8_t)(Xorshift(&s_Random) % n);
}

void Planes_Reset(void) WINGS_BANKED
{
    uint8_t i;
    for (i = 0; i < PLANES_MAX; ++i) g_Planes.plane[i].state = PLANE_FREE, g_Planes.plane[i].beh = 0;
    g_Planes.fighters = 0;
    g_Planes.live = 0;
    g_Planes.timer = 0;
}

void Planes_NewGame(void) WINGS_BANKED
{
    /* 0xe608 clears every field: also those a spawn keeps. RAM is not
     * cleared at boot on the FS-A1WX. */
    uint8_t* p = (uint8_t*)&g_Planes;
    uint16_t n;
    for (n = 0; n < sizeof g_Planes; ++n) p[n] = 0;
    s_Random = 0x3c5au;
}

void Planes_NewPlane(void) WINGS_BANKED
{
    g_Planes.timer = PLANES_TIMER_NEW_PLANE;
}

uint8_t Planes_Spawn(uint8_t kind, int16_t x, int16_t alt, int8_t facing) WINGS_BANKED
{
    Plane* e = 0;
    uint8_t i;
    /* The last free slot; a torpedo plane only while none is armed. */
    for (i = 0; i < PLANES_MAX; ++i)
    {
        Plane* p = &g_Planes.plane[i];
        if (p->state == PLANE_FREE) e = p;
        else if (kind != PLANE_KIND_FIGHTER && (p->beh & PLANE_ARMED)) return 0;
    }
    if (!e) return 0;
    e->state = PLANE_FLYING;
    e->facing = facing;
    e->x = x;
    e->talt = 50;
    e->speed = e->tspeed = PLANE_SPEED_MIN;
    e->health = PLANE_HEALTH;
    e->hits = 5 + Rand(3);
    e->rel = e->hit = 0;
    e->rank = e->frame = e->t18 = 0;
    if (kind == PLANE_KIND_FIGHTER)
    {
        e->beh = PLANE_FIGHTER;
        e->alt = alt;
        ++g_Planes.fighters;
    }
    else
    {
        e->beh = PLANE_ARMED;
        e->alt = 50;
    }
    ++g_Planes.live;
    return 1;
}

/* 0xd3b4: the relation to the player and the distance. */
static void Relation(Plane* e, const PlanesPlayer* p)
{
    int16_t dx = e->x - p->x;
    if (p->facing == e->facing)
    {
        e->rel = 1;
        if ((int16_t)(dx ^ p->facing) >= 0)
        {
            e->rel = 3;
            if (!e->t10) e->t10 = 550;
        }
    }
    else e->rel = dx < 0 ? 4 : 2;
    e->dist = dx < 0 ? -dx : dx;
}

/* 0xd476: rank among the planes behind the player, nearest first; a stale
 * relation of a free slot counts (the original does not test it). */
static void Rank(void)
{
    Plane* a = g_Planes.plane;
    uint8_t i, j;
    for (i = 0; i < PLANES_MAX; ++i)
    {
        int16_t r = 1;
        if (!a[i].beh || a[i].rel != 1) continue;
        for (j = 0; j < i; ++j)
        {
            if (a[j].rel != 1) continue;
            if (a[j].dist < a[i].dist) ++r;
            else ++a[j].rank;
        }
        a[i].rank = r;
    }
}

/* 0xe64e: the speed toward the target (it settles at target + 10). */
static void Speed(Plane* e)
{
    if (e->tspeed < PLANE_SPEED_MIN) e->tspeed = PLANE_SPEED_MIN;
    if (e->tspeed > PLANE_SPEED_MAX) e->tspeed = PLANE_SPEED_MAX;
    if (e->speed < e->tspeed)
    {
        e->speed += (e->tspeed - e->speed) / 2 + 5;
        if (e->speed > PLANE_SPEED_MAX) e->speed = PLANE_SPEED_MAX;
    }
    else if (e->speed > e->tspeed)
    {
        e->speed -= (e->speed - e->tspeed) / 2 - 5;
        if (e->speed < PLANE_SPEED_MIN) e->speed = PLANE_SPEED_MIN;
    }
}

/* 0xd562 / 0xd530: a turn, one frame every 3 ticks; the heading flips as
 * the frame would become 14. Fighters follow a turning player. */
static void Turn(Plane* e, const PlanesPlayer* p)
{
    uint8_t deck = p->mode == PLANES_PLAYER_DECK;
    uint8_t fighter = (e->beh & 3) != 0;
    uint8_t flag = 0;
    int16_t t;
    if (p->mode == PLANES_PLAYER_FLYING && fighter) e->talt = p->alt;
    if (!p->turn && !deck && p->mode == PLANES_PLAYER_FLYING && e->frame >= 19 &&
        (e->rel == 1 || e->rel == 3) && fighter)
    {
        e->frame = 0; e->beh &= ~PLANE_TURNING;   /* cut short */
        return;
    }
    e->t10 = 0;
    t = e->sub--;
    if (t <= 0) { e->sub = 2; ++e->frame; }
    if (e->frame > 25) { e->frame = 0; e->beh &= ~PLANE_TURNING; return; }
    if (e->frame == 14) { e->facing = -e->facing; ++e->frame; return; }
    if (e->frame != 20 || !fighter || p->mode != PLANES_PLAYER_FLYING) return;
    if (e->rev >= 3) { e->rev = 0; e->t10 = 550; return; }
    switch (e->rel)
    {
    case 1:
        if (p->turn > 0 && p->turn < 6 && !e->t10) e->t18 = (int16_t)((int32_t)e->dist * 100 / e->speed);
        flag = 1;
        break;
    case 2:
        if (p->turn > 0 && p->turn < 6) flag = 1;
        break;
    case 3:
        flag = 1;
        break;
    case 4:
        if (!e->t10) e->t18 = (int16_t)((int32_t)e->dist * 100 / (e->speed + p->speed));
        flag = 1;
        break;
    }
    if (flag && !deck && !e->t10)
    {
        e->frame -= (e->frame - 13) * 2;   /* 20 -> 6 */
        ++e->rev;
    }
}

/* 0xd796: motion. */
static void Motion(Plane* e, const PlanesPlayer* p)
{
    int16_t d, q;
    uint8_t k;
    if (!(e->state & 0x14) &&
        (p->mode == PLANES_PLAYER_ENGINE_OUT || p->mode == PLANES_PLAYER_CRASHED || p->mode == 6))
        e->tspeed = 1700;
    /* x += trunc(turn factor x trunc(speed / 100) x facing). */
    q = (e->speed / 100) * e->facing;
    e->x += (int16_t)(q * (int16_t)s_TurnFactor[e->frame]) / 100;
    if (!(e->state & 0x14) && !(e->beh & PLANE_ARMED))
    {
        if (p->mode == PLANES_PLAYER_DECK) e->talt = 70;
        if (e->talt < 33) e->talt = 33;
    }
    d = e->talt - e->alt;
    if (d < 0) d = -d;
    if (d > 100 || d < 0) d = 100;
    k = (uint8_t)(d / 20);
    if (e->state & PLANE_DOWN)
    {
        if (e->alt > e->talt) { e->alt += e->vy / 100; e->vy -= 10; }
        else if (e->alt < e->talt) e->alt = e->talt;
    }
    if (e->alt > e->talt) e->alt -= s_AltStep[k] + Rand(2);
    else if (e->alt < e->talt) e->alt += s_AltStep[k] + Rand(2);
    if (!(e->state & 0x14) && e->t18)
    {
        if (--e->t18 <= 0) { e->beh |= PLANE_TURNING; e->t18 = 0; }
    }
    if ((e->beh & PLANE_TURNING) && e->state == PLANE_FLYING) Turn(e, p);
}

/* 0xdea4: the armed torpedo plane: cruise at 50 toward the carrier, down
 * to 20 within 1000 px of its near end, and the drop; turns back past it. */
static void TorpedoPlane(Plane* e, const PlanesPlayer* p)
{
    uint8_t approaching;
    if (e->rel == 3)
    {
        if (e->hit == 1)
        {
            e->hit = 0;
            if (!e->t18) e->t18 = Rand(6) + 8;
            e->t10 = 275;
        }
        if (e->dist > 150) e->dist = 240;
        if (e->dist < 150)
        {
            e->dist -= 150;
            if (e->alt == e->talt) e->talt = Rand(7) * 10 + 35;
        }
        e->tspeed = p->speed - e->dist;
    }
    else
    {
        if (e->facing == -1 && e->x < CARRIER_L - 500) e->beh |= PLANE_TURNING;
        else if (e->facing == 1 && e->x > CARRIER_R + 500) e->beh |= PLANE_TURNING;
    }
    if (e->facing == -1 && e->x > CARRIER_R && e->x - CARRIER_R < 1000) e->talt = 20;
    else if (e->facing == 1 && e->x < CARRIER_L && CARRIER_L - e->x < 1000) e->talt = 20;
    approaching = (e->facing == -1 && e->x > CARRIER_R) || (e->facing == 1 && e->x < CARRIER_L);
    if (approaching)
    {
        if (e->alt == 20 && e->frame == 0)
        {
            /* The drop (0xe08c): the caller launches the torpedo. */
            g_Planes.drop = 1;
            g_Planes.drop_x = e->x; g_Planes.drop_alt = e->alt;
            g_Planes.drop_speed = e->speed; g_Planes.drop_facing = e->facing;
            e->tspeed = PLANE_SPEED_MAX / 2;
            e->talt = 60;
            e->beh = PLANE_DROPPED;
            g_Planes.timer = PLANES_TIMER_DROP;
        }
    }
    else if (--e->t10 <= 0) { e->beh |= PLANE_TURNING; e->t10 = 0; }
}

/* 0xe17a: after the drop. Freed beyond 2600 px of the player (the only
 * distance despawn); turns when the player gets ahead of it; chased, it
 * picks altitudes 25..95 (inferred: the note gives the range only). */
static void Dropped(Plane* e)
{
    if (e->dist > 2600)
    {
        e->state = PLANE_FREE; e->beh = 0;
        --g_Planes.live;
        return;
    }
    if (e->rel == 1) e->beh |= PLANE_TURNING;
    else if (e->rel == 3)
    {
        if (e->hit == 1) { e->hit = 0; if (!e->t18) e->t18 = Rand(6) + 8; e->t10 = 275; }
        if (e->alt == e->talt) e->talt = Rand(8) * 10 + 25;
    }
}

/* 0xbc02: the torpedo-plane timer. */
static void Timer(const PlanesPlayer* p, uint8_t fire, uint8_t carrier)
{
    int16_t d = 0x7fff - p->x;
    if (d < 0) d = -d;
    if (fire)
    {
        if (g_Planes.timer && g_Planes.timer < PLANES_TIMER_FIRE) g_Planes.timer = PLANES_TIMER_FIRE;
        return;
    }
    if (!g_Planes.timer || !carrier) return;
    if (--g_Planes.timer) return;
    if (d <= 0x1a00) return;
    if (p->x < CARRIER_L || (p->x <= CARRIER_R && (Xorshift(&s_Random) & 0x8000u)))
        Planes_Spawn(PLANE_KIND_TORPEDO, p->x - PLANES_SPAWN_DISTANCE, 0, 1);
    else
        Planes_Spawn(PLANE_KIND_TORPEDO, p->x + PLANES_SPAWN_DISTANCE, 0, -1);
}

void Planes_Tick(const PlanesPlayer* player, uint8_t fire, uint8_t carrier) WINGS_BANKED
{
    uint8_t i;
    Plane* e;
    g_Planes.drop = 0;
    Timer(player, fire, carrier);
    if (!g_Planes.live) return;
    for (i = 0, e = g_Planes.plane; i < PLANES_MAX; ++i, ++e)
    {
        if (e->state == PLANE_FREE) continue;
        Relation(e, player);
        Rank();
        if (e->state == PLANE_FLYING)
        {
            if (e->beh & PLANE_ARMED) TorpedoPlane(e, player);
            else if (e->beh & PLANE_DROPPED) Dropped(e);
            if (e->state == PLANE_FREE) continue;
            Speed(e);
        }
        if (e->state != PLANE_WRECK) Motion(e, player);
        /* 0xd35a: the shape index. */
        {
            uint8_t idx = (uint8_t)e->frame;
            if ((e->beh & PLANE_ARMED) && !e->frame) idx = PLANE_SHAPE_TORPEDO;
            e->shape = e->facing == -1 ? idx : idx + PLANE_SHAPE_RIGHT;
        }
    }
}
