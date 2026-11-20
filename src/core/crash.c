#include "crash.h"
#include "combat.h"
#include "flight_model.h"
#include "landing.h"
#include "mission.h"
#include "ships.h"
#include "island.h"
#include "smoke.h"
#include "game.h"
#include "xorshift.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_GAME)

/* The original's crash routine and the modes after it, one call per
 * original tick (docs/research/amiga-player-crash.md). Altitudes are the
 * original's: px above the sea; the deck stands at 33. */
#ifdef WINGS_P1_FLIGHT
extern CombatState g_Combat;   /* world_flight.c */
extern GameState g_Game;
extern uint8_t g_LastContact;
extern uint8_t g_ShipHeave;    /* msx/ship.c: the enemy ships' bob */
CrashState g_Crash;
static uint16_t s_Random = 0xB5C3u;

#define SEA 0
#define DECK 1
#define LAND 2
#define CLIMB_FALL (-3100)     /* the falling nose settles at -31 degrees */
#define CLIMB_SINK (-4500)
#define FALL_MAX (-10)         /* terminal vertical step, px per tick */
#define LEVEL_BOTTOM 2         /* the level pose without wheels */

static uint8_t Random(void)
{
    Xorshift(&s_Random);
    return (uint8_t)(s_Random >> 8);
}

static int16_t Altitude(const FlightState* f)
{
    return (int16_t)WINGS_FLIGHT_MAX_Y - (int16_t)(f->y >> 8);
}

/* 0xafba: the sea (or beyond the map), a ship or the carrier, or land. */
static uint8_t Outcome(int16_t x)
{
    uint8_t s = Mission_Surface((uint16_t)x);
    return s == MISSION_SEA ? SEA : s == MISSION_CARRIER ? DECK : LAND;
}

/* 0x5710 over a hull: the carrier's deck, or an enemy ship's less its bob. */
static int16_t Deck(int16_t x)
{
    uint8_t ship = Ships_Find((uint16_t)x);
    if (ship == SHIP_NONE || ship == SHIP_CARRIER) return LANDING_DECK_HEIGHT;
    return (int16_t)Ships_Deck(ship) - (int16_t)(g_ShipHeave + 2);
}

/* 0x0820: a burst on the column under x, its art on the surface h px up:
 * the explosion with a boom, or (sea) the water burst, silent. It hurts
 * nothing. No free slot: none, as the original. */
static void Explode(int16_t x, int16_t h, uint8_t sea)
{
    CombatProjectile* p = g_Combat.projectile + COMBAT_GUN_COUNT;
    uint8_t i;
    for (i = COMBAT_GUN_COUNT; i < COMBAT_COUNT && p->kind; ++i, ++p) {}
    if (i == COMBAT_COUNT) return;
    if (i >= g_Combat.count) g_Combat.count = i + 1;
    p->x = (uint16_t)(x & ~7) * 4u;
    p->y = (uint16_t)((int16_t)WINGS_FLIGHT_MAX_Y - h) * 4u;
    p->vx = COMBAT_CRASH_BURST; p->vy = 0; p->life = 6;
    p->kind = sea ? COMBAT_SPLASH : COMBAT_IMPACT;
    if (g_Combat.impacts != 65535u) ++g_Combat.impacts;
}

/* 0x46c6 / 0x46dc: a rocket-type impact on the column under x. On land a
 * white flash, or red when it wrecked a hut or emptied a dugout; on a ship
 * the first live gun within 16 px (Ships_Rocket). */
static void Impact(int16_t x)
{
    uint8_t color;
    if (Outcome(x) == LAND)
    {
        uint16_t points = Island_Bombed((uint16_t)x);
        g_Game.progress.score += points;
        color = points ? COMBAT_SKY_RED : COMBAT_SKY_WHITE;
    }
    else color = Ships_Rocket((uint16_t)x, &g_Game.progress.score);
    if (color) { g_Combat.sky_flash = 5; g_Combat.sky_color = color; }
}

void Crash_Contact(FlightState* f, uint16_t world) WINGS_BANKED
{
    int16_t x = (int16_t)world, alt = Altitude(f);
    uint8_t out = Outcome(x);
    if (out == LAND || (out == DECK && alt >= 20))
    {
        Explode(x + (f->facing_left ? -16 : 16), alt, 0);
        Impact(x);
    }
    /* 0xc6a0's entry: the last horizontal step becomes the speed. The rest
     * of this tick moves on level; the next tick is the crash routine's. */
    Flight_EngineOut(f);
    f->vy = 0; f->yrem = 0;
}

/* 0xafba's turn step: an unfinished turn moves 2 frames a tick, back to 0
 * below frame 14, on to the end (the heading flips at 14) from it. */
static void Turn(FlightState* f)
{
    if (!f->turn) return;
    if (f->turn < 14) f->turn = f->turn > 2 ? f->turn - 2 : 0;
    else
    {
        if (f->turn == 14) f->facing_left ^= 1;
        f->turn += 2;
        if (f->turn > 25) f->turn = 0;
    }
}

/* 0xafba, mode 4: fall, slide on the surface, then sink or burn. */
static int16_t Dead(FlightState* f, int16_t x, int16_t alt)
{
    int8_t dir = f->facing_left ? -1 : 1;
    int16_t step = f->speed / 100, floor, dx = 0;
    uint8_t out = Outcome(x), bottom = Landing_Bottom(f->frame, 0), on = 0, fall = 0;
    floor = bottom;
    if (out == DECK) floor += Deck(x);
    if (alt <= floor)
    {
        if (out == DECK && Outcome(x - 40 * dir) == SEA)
        {
            /* The hull side, its first 40 px from the sea: thrown back with
             * a red flash and a burst; the plane falls into the sea. (The
             * original moves back 4 px more to the right either way.) */
            dx = -dir * (step + 4);
            f->speed = 0; step = 0;
            g_Combat.sky_flash = 7; g_Combat.sky_color = COMBAT_SKY_RED;
            Explode(x, alt, 0);
            floor = bottom;
        }
        else if (out != LAND || !f->turn)
        {
            /* On the surface: level, no wheels. */
            f->climb = f->path = 0;
            alt = floor = (out == DECK ? Deck(x) : 0) + LEVEL_BOTTOM;
            on = 1;
            if (out == SEA) Ships_AddSplash(x + 8 * dir);
            else if (out == LAND) Explode(x, 1, 0);
        }
    }
    Turn(f);
    if (on && f->turn) dx += dir * step;   /* the turn finishes first */
    else if (on)
    {
        /* The slide: speed falls 85 a tick. On land each tick strikes the
         * column (huts, guns, dugouts) and kills soldiers within 8 px. The
         * original's stray burst at 0xb304 is left out. */
        dx += dir * step;
        f->speed -= 85;
        if (f->speed < 100) f->speed = 0;
        if (out == SEA) Ships_AddSplash(x + dx + 8 * dir);
        else if (out == LAND) { Impact(x + dx); Island_Kill(x + dx, 8); }
    }
    else
    {
        f->climb -= 600;
        if (f->climb < CLIMB_FALL) f->climb = CLIMB_FALL;
        fall = 1;
    }
    if (fall)
    {
        if (--f->path < FALL_MAX) f->path = FALL_MAX;
        alt += f->path;
        /* The original stops the fall only at the ground (altitude 0) and
         * lets the next tick lift the plane onto a deck; here it stops on
         * the deck. Over the sea the burst is the water's (the original
         * draws its land explosion there too). */
        if (alt <= floor)
        {
            alt = floor;
            if (out != DECK) Explode(x, alt - 1, out == SEA);
        }
        dx += dir * step;
    }
    g_Crash.dx = dx;
    if (!f->speed && !f->turn && alt <= floor)
    {
        /* 0xb3e6: sea, or a deck below 20 (the Japanese carrier riding
         * low): sinking; else the wreck. The oil gauge falls to 0. */
        out = Outcome(x + dx);
        f->mode = out == SEA || (out == DECK && alt < 20) ? FLIGHT_SINKING : FLIGHT_WRECK;
        g_Game.sortie.oil = 0;
        g_Crash.clock = g_Crash.next = g_Crash.sink = g_Crash.depth = 0;
        g_LastContact = LANDING_CRASH;
    }
    return alt;
}

void Crash_Tick(FlightState* f, uint16_t world) WINGS_BANKED
{
    int16_t x = (int16_t)world, start = Altitude(f), alt = start;
    uint8_t sea = f->mode == FLIGHT_SINKING;
    g_Crash.dx = 0;
    if (f->mode == FLIGHT_DEAD) alt = Dead(f, x, alt);
    else
    {
        if (sea)
        {
            /* 0xc78c: a pixel down every 3 ticks, the nose going down. */
            if (++g_Crash.sink > 2) { g_Crash.sink = 0; ++g_Crash.depth; }
            f->climb -= 250;
            if (f->climb < CLIMB_SINK) f->climb = CLIMB_SINK;
        }
        else
        {
            /* 0xc7c6: riding the deck's bob; a fire puff every 4 ticks
             * that burns out into smoke drifting downwind. */
            alt = (Outcome(x) == DECK ? Deck(x) : 0) + LEVEL_BOTTOM;
            if (!(++g_Crash.puff & 3))
            {
                int16_t h = alt + 17;
                if (h < 16) h = 16;
                Smoke_Puff((uint16_t)(x + (f->facing_left ? -8 : 8) + (Random() & 7)),
                           (uint16_t)((int16_t)WINGS_FLIGHT_MAX_Y - h), SMOKE_STAGE_FIRE);
            }
        }
        /* 0xaed8: for 6 s, a burst every 1, 4, 8 or 12 ticks within 8 px
         * of the plane: water bursts, or explosions with a boom. */
        if (g_Crash.clock < CRASH_BURST_TICKS && g_Crash.clock >= g_Crash.next)
        {
            g_Crash.next = g_Crash.clock + (Random() & 12);
            Explode(x + (int16_t)(Random() & 15) - 8, sea ? 0 : alt - LEVEL_BOTTOM, sea);
        }
        if (g_Crash.clock != 255) ++g_Crash.clock;
    }
    g_Crash.dy = start - alt;
}
#endif
