#include "planes.h"
#include "ships.h"
#include "xorshift.h"
#include "mission_planes.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_FIGHTERS)

/* Enemy fighters (docs/enemy-planes.md, step 4), from the pseudo-code in
 * docs/research/amiga-enemy-planes.md: the AI (0xd9c6), the attack and its
 * fire (0xdccc, 0xde52), and the launches from the ships (0x1574). Split
 * from core/planes.c for room; they share its random source. */

#if PLANE_LISTS > PLANES_LISTS_MAX || PLANE_PARKED > PLANES_PARKED_MAX
#error The map has more plane lists or parked planes than PlanesState holds
#endif

extern uint16_t g_PlanesRandom;   /* core/planes.c */
uint8_t g_PlanesFlee;     /* -$3198: fleeing fighters this tick */
uint8_t g_PlanesParity;   /* -$3cb8: the tick parity */
static uint8_t Rand(uint8_t n)
{
    return (uint8_t)(Xorshift(&g_PlanesRandom) % n);
}

void Fighters_Reset(void) WINGS_BANKED
{
    uint8_t i;
    g_Planes.cooldown = 0;
    for (i = 0; i < PLANE_LISTS; ++i) g_Planes.left[i] = s_ListFirst[i + 1] - s_ListFirst[i];
    g_Planes.parked = 0;
    g_Planes.lists = PLANE_LISTS;
}

/* 0xd9c6: a fighter (behaviour 1, or 9 turning), by its relation to the
 * player. s_Flee counts the fleeing fighters this tick (-$3198). */
static int16_t Delay(int16_t dist, int16_t speed)
{
    /* muls.w #100 then ext.l: only the product's low word (wraps above 327). */
    return (int16_t)((int16_t)(dist * 100) / speed);
}
static void Fighter(Plane* e, const PlanesPlayer* p)
{
    uint8_t ptf = p->turn;
    switch (e->rel)
    {
    case 1:   /* on the player's tail */
        if (e->dist < 160)
        {
            if (ptf > 0 && ptf < 6 && p->mode != PLANES_PLAYER_DECK && !e->t18)
                e->t18 = (int16_t)((int32_t)e->dist * 100 / e->speed) + e->rank * 2;
            else if (!e->t18 && e->rank == 1) e->beh = (e->beh & PLANE_TURNING) | PLANE_ATTACK;
            else
            {
                e->firing = 0;
                e->talt = p->alt;
                e->tspeed = p->speed - e->rank * 70;
            }
        }
        else if (!e->frame)
        {
            e->tspeed = e->dist + p->speed;
            if (e->rank == 1) e->tspeed += 80; else e->tspeed -= e->rank * 80;
        }
        break;
    case 2:   /* opposite heading, right of the player */
        if (p->mode == PLANES_PLAYER_FLYING && ptf > 0 && ptf < 11) e->tspeed = PLANE_SPEED_MIN;
        else e->beh |= PLANE_TURNING;
        break;
    case 3:   /* the player on its tail */
        if (e->dist >= 1536) { e->beh |= PLANE_TURNING; break; }
        if (--e->t10 <= 0 || (ptf > 0 && ptf < 6) || p->mode == PLANES_PLAYER_DECK)
        {
            e->beh |= PLANE_TURNING; e->t10 = 0;
            break;
        }
        if (e->hit == 1)
        {
            e->hit = 0;
            if (!e->t18) e->t18 = Rand(6) + 8;
            e->t10 = 550;
            break;
        }
        e->tspeed = p->speed - e->dist / 4 + g_PlanesFlee++ * 70;
        if (e->alt == e->talt) e->talt = Rand(7) * 10 + 35;
        break;
    case 4:   /* opposite heading, left of the player */
        if (p->mode != PLANES_PLAYER_FLYING) break;
        e->tspeed = PLANE_SPEED_MIN;
        e->talt = e->alt >= p->alt ? p->alt + 32 : p->alt - 32;
        e->t18 = Delay(e->dist, e->speed + p->hstep);
        e->beh |= PLANE_TURNING;
        break;
    }
}

/* 0xdccc: the attack (behaviour 2, or 10 turning): 130 px behind at the
 * player's altitude; the nearest fighter behind, level, within 160 px
 * and 8 px of altitude fires (+12). On ticks of odd parity at exactly the
 * player's altitude the player's hit counter runs down: oil -8 and fuel
 * -0..31 each time it runs out (0xde52). */
static void Attack(Plane* e, const PlanesPlayer* p)
{
    int16_t da;
    if (e->rel != 1) { e->beh = PLANE_FIGHTER; return; }   /* +12 stays (a quirk) */
    if (p->turn || p->mode == PLANES_PLAYER_DECK)
    {
        e->beh = PLANE_FIGHTER | PLANE_TURNING;
        e->t18 = e->dist / (e->speed / 100);
    }
    else if (e->dist > 130) e->tspeed = p->speed + 50;
    else if (e->dist < 130) e->tspeed = p->speed - 50;
    e->talt = p->alt;
    da = p->alt - e->alt; if (da < 0) da = -da;
    if (p->mode == PLANES_PLAYER_FLYING && e->beh == PLANE_ATTACK && e->rank == 1 && da < 8 && !e->frame &&
        e->dist < 160 && p->facing == e->facing && (int16_t)((e->x - p->x) ^ p->facing) < 0)
    {
        e->firing = 1;
        if (e->alt == p->alt && g_PlanesParity && !--p->engine->hits)
        {
            Engine_Damage(p->engine, p->sortie, 8, Rand(32));
            p->engine->hits = Rand(5) + 6;
        }
    }
    else e->firing = 0;
}

/* 0x1574: a ship afloat launches its last parked plane as a fighter, at
 * most PLANES_LAUNCH_COOLDOWN ticks apart (shared), while the player is in
 * its window and fewer fighters fly than its list allows. The original's
 * Japanese carrier rolls its planes along the deck first (0x1510), and
 * airstrips (0x1622) roll theirs: neither is on a built map yet. */
void Fighters_Launch(int16_t px) WINGS_BANKED
{
    uint8_t i, n, ship;
    if (g_Planes.cooldown && --g_Planes.cooldown) goto parked;
    for (i = 0; i < PLANE_LISTS; ++i)
    {
        ship = s_ListShip[i];
        if (!g_Ships.hull[ship] || px < s_ListLo[i] || px > s_ListHi[i]) continue;
        if (g_Planes.fighters >= s_ListMax[i] || !g_Planes.left[i]) continue;
        n = s_ListFirst[i] + --g_Planes.left[i];
        Planes_Spawn(PLANE_KIND_FIGHTER, s_ParkedX[n], s_ParkedAlt[n], -1);
        g_Planes.cooldown = PLANES_LAUNCH_COOLDOWN;
    }
parked:
    /* The planes still on deck, sinking with their ship (0x391e). */
    g_Planes.parked = 0;
    g_Planes.lists = g_Planes.cooldown ? 1 : 0;
    for (i = 0; i < PLANE_LISTS; ++i)
    {
        if (g_Planes.left[i]) ++g_Planes.lists;
        for (n = s_ListFirst[i]; n < s_ListFirst[i] + g_Planes.left[i]; ++n)
        {
            uint8_t k = g_Planes.parked++;
            g_Planes.parked_x[k] = s_ParkedX[n];
            g_Planes.parked_alt[k] = s_ParkedAlt[n] - g_Ships.step[s_ListShip[i]];
            g_Planes.parked_left[k] = s_ParkedDir[n] < 0;
        }
    }
}

void Fighters_Behave(Plane* e, const PlanesPlayer* p) WINGS_BANKED
{
    if ((e->beh & ~PLANE_TURNING) == PLANE_FIGHTER) Fighter(e, p);
    else Attack(e, p);
}

int8_t g_CameraLead;
static uint8_t s_TailHold;
uint16_t Camera_Follow(uint16_t world, uint8_t flags, uint8_t ticks) WINGS_BANKED
{
    uint8_t left = flags & CAMERA_LEFT, i;
    int8_t target = left ? -CAMERA_LEAD : CAMERA_LEAD, step;
    const Plane* e;
    int16_t behind, px = (int16_t)world;
    if (flags & CAMERA_RESET) g_CameraLead = s_TailHold = 0;
    else if (flags & CAMERA_MOVE)
    {
        for (i = 0, e = g_Planes.plane; i < PLANES_MAX; ++i, ++e)
        {
            if (e->state != PLANE_FLYING || !(e->beh & (PLANE_FIGHTER | PLANE_ATTACK))) continue;
            behind = left ? e->x - px : px - e->x;
            if ((e->beh & 7) == PLANE_ATTACK ||
                ((e->facing < 0) == (left != 0) && behind >= 0 && behind < CAMERA_TAIL_RANGE))
                s_TailHold = CAMERA_TAIL_HOLD;
        }
        if (s_TailHold) { target = -target; s_TailHold = s_TailHold > ticks ? s_TailHold - ticks : 0; }
        step = (int8_t)(CAMERA_EASE * ticks);
        target -= g_CameraLead;
        if (target > step) target = step; else if (target < -step) target = -step;
        g_CameraLead += target;
    }
    /* The far view: an arithmetic shift (FAR_X in world_flight.c). */
    return (flags & CAMERA_FAR ? (uint16_t)((px >> 3) + (g_CameraLead >> 3)) : world + g_CameraLead) - 128;
}
