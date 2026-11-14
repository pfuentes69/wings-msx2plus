#include "smoke.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_EFFECTS)

#ifdef WINGS_P1_FLIGHT
SmokePuff g_Smoke[SMOKE_COUNT];
static uint8_t s_Phase;
static uint16_t s_Random = 0xACE1u;

/* Puff probability for damage 1..19 (= 128 - oil), 16 bits per pair of
 * damage levels (DATA -$5a34, bit n of byte n / 8): 3/16 rising to 12/16.
 * Above 19 every chance puffs. */
static const uint8_t s_Chance[20] = {
    0x80, 0xc0, 0xc0, 0xc0, 0xc0, 0xe0, 0xe0, 0xe0, 0xe0, 0xf0,
    0xf0, 0xf0, 0xf4, 0xf8, 0xf8, 0xf8, 0xf8, 0xfc, 0xfc, 0xfc};
/* Smoke x offset by turn frame 9..17 (DATA -$640e, low nibble). */
static const uint8_t s_TurnOffset[9] = {3, 7, 11, 12, 11, 7, 3, 12, 15};

static uint8_t Random(void)
{
    /* 16-bit xorshift (7, 9, 8); the high byte is well mixed. */
    s_Random ^= s_Random << 7;
    s_Random ^= s_Random >> 9;
    s_Random ^= s_Random << 8;
    return (uint8_t)(s_Random >> 8);
}

void Smoke_Reset(void) WINGS_BANKED
{
    uint8_t i;
    for (i = 0; i < SMOKE_COUNT; ++i) g_Smoke[i].stage = 0;
    s_Phase = 0;
}

static void Puff(SmokePuff* p, uint16_t x, uint16_t y)
{
    p->x = x; p->y = y;
    p->xf = p->yf = 0;
    p->vx = Random(); p->vy = Random();
    p->stage = SMOKE_STAGES;
    p->life = SMOKE_STAGE_TICKS - 1;
}

/* 0x54e0 / 0x5460: a puff 10 px ahead of the plane's origin and 13 px above
 * it (at least 16 px above the sea), drifting 1-2 px right and up a tick. */
static void Spawn(const FlightState* f, uint16_t world)
{
    SmokePuff* p = g_Smoke;
    uint8_t i, t = f->turn;
    int16_t dx = f->facing_left ? -10 : 10, altitude;
    for (i = 0; i < SMOKE_COUNT && p->stage; ++i, ++p) {}
    if (i == SMOKE_COUNT) return;   /* pool full: no puff (as the original) */
    if (t > 8 && t < 18)
    {
        int8_t o = (int8_t)s_TurnOffset[t - 9];
        if (f->facing_left ? o <= 11 : o < 11) o = -o;
        dx += o;
    }
    altitude = (int16_t)WINGS_FLIGHT_MAX_Y - (int16_t)(f->y >> 8) + 13;
    if (altitude < 16) altitude = 16;
    Puff(p, world + dx, (uint16_t)((int16_t)WINGS_FLIGHT_MAX_Y - altitude));
}

void Smoke_Emit(uint16_t x, uint16_t y) WINGS_BANKED
{
    SmokePuff* p = g_Smoke;
    uint8_t i;
    for (i = 0; i < SMOKE_COUNT && p->stage; ++i, ++p) {}
    if (i < SMOKE_COUNT) Puff(p, x, y);
}

void Smoke_Tick(const FlightState* flight, uint16_t world, uint8_t oil, uint8_t emit) WINGS_BANKED
{
    SmokePuff* p = g_Smoke;
    uint8_t i, damage;
    for (i = 0; i < SMOKE_COUNT; ++i, ++p)
    {
        uint16_t xf, yf;
        if (!p->stage) continue;
        xf = p->xf + p->vx; p->xf = (uint8_t)xf; p->x += 1 + (xf >> 8);
        yf = p->yf + p->vy; p->yf = (uint8_t)yf; p->y -= 1 + (yf >> 8);
        if (p->life) --p->life;
        else { p->life = SMOKE_STAGE_TICKS - 1; --p->stage; }
    }
    /* 0x1bfc: the original checks every other tick; with its 40-entry
     * effect pool against the port's 8 puffs, the MSX checks every 4th. */
    if (!emit || (++s_Phase & 3)) return;
    damage = oil < 128 ? 128 - oil : 0;
    if (!damage) return;
    if (damage <= 19)
    {
        uint8_t bit = ((damage << 3) & 0xf0) + (Random() & 15);
        if (!(s_Chance[bit >> 3] & (1 << (bit & 7)))) return;
    }
    Spawn(flight, world);
}
#endif
