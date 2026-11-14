#include "flight_model.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_FLIGHT)

/* The original flight model, one call per original 12.5 Hz tick. Recovered
 * from the Amiga executable; addresses and variables are documented in
 * docs/research/amiga-fuel-oil.md ("Flight model"). The original computes
 * motion in Motorola fast floating point; here the same tables are scaled
 * integers (sin x 10000, turn factor x 100), so results can differ by one
 * pixel only where the exact value lands on a whole pixel. */
#ifdef WINGS_P1_FLIGHT

#define ACCEL 600            /* -$50e8 */
#define CLIMB_MAX 3000
#define CLIMB_MIN (-4500)
#define TURN_DIVE_MIN (-2250)
#define FLARE_CLIMB 600      /* the stall: UP alone, facing left */
#define FLARE_PATH (-800)
#define SPEED_MIN 1000
#define SPEED_MAX 1400
#define BOOST_MAX 8
#define BOOST_MIN 4
#define CEILING 1100         /* altitude */
#define DECK_ROLL_FAST 600
#define DECK_BRAKE 8
#define ARREST_BRAKE 110

/* sin(degree) x 10000, 0..90 (-$548a). Entries 1..4 are all sin 4 degrees. */
static const uint16_t s_Sin[91] = {
    0, 698, 698, 698, 698, 872, 1045, 1219, 1392, 1564, 1736, 1908, 2079, 2250, 2419,
    2588, 2756, 2924, 3090, 3256, 3420, 3584, 3746, 3907, 4067, 4226, 4384, 4540, 4695,
    4848, 5000, 5150, 5299, 5446, 5592, 5736, 5878, 6018, 6157, 6293, 6428, 6561, 6691,
    6820, 6947, 7071, 7193, 7314, 7431, 7547, 7660, 7771, 7880, 7986, 8090, 8191, 8290,
    8387, 8480, 8572, 8660, 8746, 8830, 8910, 8988, 9063, 9136, 9205, 9272, 9336, 9397,
    9455, 9511, 9563, 9613, 9659, 9703, 9744, 9782, 9816, 9848, 9877, 9903, 9926, 9945,
    9962, 9976, 9986, 9994, 9998, 10000};
/* Horizontal speed factor x 100 by turn frame (-$54f2). */
static const uint8_t s_TurnFactor[26] = {
    100, 98, 95, 91, 86, 81, 75, 70, 60, 50, 40, 30, 23, 20, 0, 5, 25, 45, 60, 70, 75,
    81, 86, 91, 95, 98};
/* Pose 1..10 by (climb + 5000) / 500 (-$5526); pose 5 is level. */
static const uint8_t s_Pose[18] = {10, 10, 9, 9, 8, 8, 7, 7, 6, 5, 5, 4, 4, 3, 3, 2, 2, 1};

/* 0xab80: a turn advances one frame every 2 ticks. The heading flips at
 * frame 14 and the turn ends after 25. Past frame 19, unless the new heading
 * is held, the frame mirrors (26 - frame) and the turn unwinds. (The original
 * also pauses turns while a particular weapon object is in flight, 0xaa6e;
 * not reproduced.) */
static void TurnAdvance(FlightState* f, uint8_t forward)
{
    if (--f->turn_clock) return;
    f->turn_clock = 2;
    if (++f->turn > 25) { f->turn = 0; return; }
    if (f->turn > 19 && !forward) f->turn = 26 - f->turn;
    if (f->turn == 14) f->facing_left ^= 1;
}

/* Early in a turn (frame 6 or less) the turn unwinds a frame per tick. */
static void TurnContinue(FlightState* f, uint8_t forward)
{
    if (!f->turn) return;
    if (f->turn > 6) TurnAdvance(f, forward);
    else --f->turn;
}

/* Without vertical input a climb flattens; while turning the nose drops.
 * Climbs of up to 5 degrees are cancelled out of the flight path at once. */
static void Relax(FlightState* f, uint8_t turning)
{
    if (turning)
    {
        f->climb -= ACCEL / 4;
        if (f->climb < TURN_DIVE_MIN) f->climb = TURN_DIVE_MIN;
        if (f->climb > 0 && f->climb <= 500) f->cancel = -f->climb;
    }
    else if (f->climb > 0)
    {
        f->climb -= ACCEL;
        if (f->climb < 0) f->climb = 0;
        if (f->climb <= 500) f->cancel = -f->climb;
    }
}

static void Dive(FlightState* f, int16_t amount)
{
    f->climb -= amount;
    if (f->climb < CLIMB_MIN) f->climb = CLIMB_MIN;
}

/* 0xbff4: controls in the air. */
static void AirControls(FlightState* f, uint8_t input)
{
    uint8_t horizontal = input & (FLIGHT_LEFT | FLIGHT_RIGHT);
    /* LEFT wins when both are held, as in the original. */
    uint8_t forward = horizontal && (uint8_t)!!(input & FLIGHT_LEFT) == f->facing_left;
    f->landing = 0;
    f->cancel = 0;
    if (!(input & (FLIGHT_LEFT | FLIGHT_RIGHT | FLIGHT_UP | FLIGHT_DOWN)))
    {
        uint8_t turning = f->turn != 0;
        TurnContinue(f, 0);
        Relax(f, turning);
        if (--f->boost < BOOST_MIN) f->boost = BOOST_MIN;
        if (f->speed > SPEED_MIN)
        {
            f->speed -= f->boost;
            if (f->speed < SPEED_MIN) f->speed = SPEED_MIN;
        }
        f->throttle = 0;
        return;
    }
    if (horizontal)
    {
        if (forward)
        {
            f->throttle = 1;
            TurnContinue(f, 1);
            if (++f->boost > BOOST_MAX) f->boost = BOOST_MAX;
            f->speed += f->boost;
            if (f->speed > SPEED_MAX) f->speed = SPEED_MAX;
        }
        else TurnAdvance(f, 0);   /* pushing the other way turns */
        if (input & FLIGHT_DOWN) Dive(f, f->turn ? ACCEL / 2 : ACCEL);
        else if (input & FLIGHT_UP)
        {
            f->climb += f->speed > SPEED_MIN ? ACCEL : f->facing_left ? ACCEL / 8 : ACCEL / 4;
            if (f->climb > CLIMB_MAX) f->climb = CLIMB_MAX;
        }
        else Relax(f, f->turn != 0);
        return;
    }
    /* Vertical input alone: no power change. */
    f->throttle = 0;
    if (input & FLIGHT_DOWN)
    {
        f->throttle = 1;
        Dive(f, 2 * ACCEL);
    }
    else if (f->facing_left)
    {
        /* The stall flare: the nose settles at +6 degrees while the plane
         * sinks (see Integrate); the landing flag allows a deck landing. */
        if (f->climb < FLARE_CLIMB)
        {
            f->climb += ACCEL;
            if (f->climb > FLARE_CLIMB) f->climb = FLARE_CLIMB;
        }
        else
        {
            f->climb -= ACCEL;
            if (f->climb < FLARE_CLIMB) f->climb = FLARE_CLIMB;
        }
        f->landing = 1;
    }
    else
    {
        /* Facing right, UP alone noses down, settling near -12 degrees. */
        f->climb -= ACCEL;
        if (f->climb < -ACCEL) f->climb -= (f->climb + ACCEL) / 2;
        f->cancel = 0;
    }
    TurnContinue(f, 0);
}

/* Spread one tick's whole-pixel motion over the next FLIGHT_TICK_STEPS
 * steps, stopping FLIGHT_SEA_LIMIT px out over the open sea. */
static void SetMotion(FlightState* f, uint16_t world, int16_t dx, int16_t dy)
{
    int16_t q, at = (int16_t)world;
    if (dx < 0 && at + dx < -FLIGHT_SEA_LIMIT) dx = -FLIGHT_SEA_LIMIT - at;
    if (dx > 0 && at + dx > (int16_t)WINGS_WORLD_WIDTH + FLIGHT_SEA_LIMIT) dx = (int16_t)WINGS_WORLD_WIDTH + FLIGHT_SEA_LIMIT - at;
    q = dx * 256;
    f->vx = q / (int16_t)FLIGHT_TICK_STEPS;
    f->xrem = (int8_t)(q - f->vx * (int16_t)FLIGHT_TICK_STEPS);
    q = dy * 256;
    f->vy = q / (int16_t)FLIGHT_TICK_STEPS;
    f->yrem = (int8_t)(q - f->vy * (int16_t)FLIGHT_TICK_STEPS);
}

/* Unsigned 16 x 16 -> 32 bit multiply. SDCC's general 32-bit multiply and
 * divide cost milliseconds per call on the Z80; the tick needs neither. */
#ifdef __SDCC
static uint32_t Mul16(uint16_t a, uint16_t b) __naked
{
    (void)a; (void)b;
    __asm
        ld      b, h                    ; BC = a, DE = b
        ld      c, l
        ld      hl, #0
        ld      a, #16
    00001$:
        add     hl, hl                  ; DEHL <<= 1, adding BC per bit of DE
        rl      e
        rl      d
        jr      nc, 00002$
        add     hl, bc
        jr      nc, 00002$
        inc     de
    00002$:
        dec     a
        jr      nz, 00001$
        ex      de, hl                  ; return HL:DE = high:low
        ret
    __endasm;
}
#else
static uint32_t Mul16(uint16_t a, uint16_t b) { return (uint32_t)a * b; }
#endif

/* floor(value / unit), for quotients of at most a few dozen. */
static int16_t Quotient(uint32_t value, uint32_t unit)
{
    int16_t q = 0;
    while (value >= unit) { value -= unit; ++q; }
    return q;
}

/* 0xbdfa: the flight path follows the climb; motion from speed and path. */
static void Integrate(FlightState* f, uint8_t input, uint16_t world)
{
    int16_t angle, hstep, vstep, altitude;
    uint8_t degree, down;
    uint32_t product;
    if (f->landing && f->climb == FLARE_CLIMB) f->path += (FLARE_PATH - f->path) / 4;
    else f->path += (f->climb - f->path) / 4;
    angle = f->path + f->cancel;
    if (angle < 0) angle = -angle;
    degree = (uint8_t)(angle / 100);
    down = f->path < 0 || f->cancel < 0;
    if (degree == 90) f->boost += down ? 1 : -1;
    if (!f->facing_left && f->speed < SPEED_MIN) f->boost -= f->boost / 10;
    /* hstep = (speed x turn x cos + 50) / 100, exactly in the table units:
     * (speed x turn100 x cos10000 + 5e7) / 1e8. */
    product = Mul16((uint16_t)f->speed, s_TurnFactor[f->turn]);
    product = Mul16((uint16_t)product, s_Sin[(9000 - angle) / 100]) +
              ((uint32_t)((uint16_t)(product >> 16) * s_Sin[(9000 - angle) / 100]) << 16);
    hstep = Quotient(product + 50000000UL, 100000000UL);
    /* vstep = speed x sin / 100, truncated toward zero. */
    vstep = Quotient(Mul16((uint16_t)f->speed, s_Sin[degree]), 1000000UL);
    if (down) vstep = -vstep;
    if (f->speed < SPEED_MIN)
    {
        /* Below flying speed (just off the deck): the nose drops unless UP
         * is held, and the plane sinks. */
        if (!(input & FLIGHT_UP)) Dive(f, ACCEL / 2);
        vstep -= (SPEED_MIN - f->speed) / 100;
    }
    altitude = (int16_t)WINGS_FLIGHT_MAX_Y - (int16_t)(f->y >> 8);
    if (altitude + vstep > CEILING)
    {
        vstep = CEILING - altitude;
        f->climb = -f->climb;
    }
    if (altitude + vstep < 0) vstep = -altitude;   /* contact crashes first */
    SetMotion(f, world, f->facing_left ? -hstep : hstep, -vstep);
}

/* 0xc4e8: controls on deck. */
static void DeckControls(FlightState* f, uint8_t input)
{
    uint8_t horizontal = input & (FLIGHT_LEFT | FLIGHT_RIGHT);
    if (horizontal && (uint8_t)!!(input & FLIGHT_LEFT) == f->facing_left)
    {
        f->throttle = 1;
        if (!f->turn) { if (++f->boost > BOOST_MAX) f->boost = BOOST_MAX; }
        else --f->turn;
        f->speed += f->boost;
    }
    else
    {
        f->throttle = 0;
        f->boost = 0;
        /* Pushing the other way at rest turns the plane round on deck. */
        if (horizontal && !f->speed && ++f->turn > 6)
        {
            f->facing_left ^= 1;
            f->turn = 5;
        }
        f->speed -= DECK_BRAKE;
    }
    f->fast_roll = f->speed > DECK_ROLL_FAST && !(input & FLIGHT_UP);
    if (f->speed < 0) f->speed = 0;
    if (f->speed > SPEED_MAX) f->speed = SPEED_MAX;
}

void Flight_Tick(FlightState* f, uint16_t world, uint8_t input) WINGS_BANKED
{
    if ((input & (FLIGHT_UP | FLIGHT_DOWN)) == (FLIGHT_UP | FLIGHT_DOWN)) input &= ~FLIGHT_UP; /* DOWN wins */
    if (f->mode == FLIGHT_AIRBORNE)
    {
        uint8_t index;
        AirControls(f, input);
        Integrate(f, input, world);
        index = (uint8_t)((f->climb + 5000) / 500);
        f->frame = f->turn ? 4 : s_Pose[index > 17 ? 17 : index] - 1;
        return;
    }
    f->landing = 0;
    f->frame = 4;
    if (f->mode == FLIGHT_ARREST)
    {
        /* 0xc882: the cable stops the plane, then it is back on deck. */
        f->climb = f->cancel = 0;
        f->speed -= ARREST_BRAKE;
        if (f->speed < 0) { f->speed = 0; f->mode = FLIGHT_GROUND; }
        f->fast_roll = 0;
    }
    else DeckControls(f, input);
    {
        /* 0xbdba: roll; 0xc5f4: past either end of the deck the plane flies
         * (or falls); 0xb92e: with UP held above speed 600, the hook catches
         * a cable when it passes within 8 px of one. */
        int16_t step = (f->speed + 50) / 100;
        uint16_t next = f->facing_left ? world - step : world + step;
        SetMotion(f, world, f->facing_left ? -step : step, 0);
        if (f->mode != FLIGHT_GROUND) return;
        if (next < FLIGHT_DECK_LEFT + FLIGHT_DECK_EDGE || next > FLIGHT_DECK_RIGHT - FLIGHT_DECK_EDGE)
            f->mode = FLIGHT_AIRBORNE;
        else if (f->speed >= DECK_ROLL_FAST && !f->fast_roll)
        {
            uint16_t hook = f->facing_left ? next + FLIGHT_HOOK : next - FLIGHT_HOOK;
            uint16_t cable = FLIGHT_CARRIER_X + FLIGHT_CABLE_FIRST;
            uint8_t i;
            for (i = 0; i < 4; ++i, cable += FLIGHT_CABLE_SPACING)
                if (hook + FLIGHT_CABLE_REACH >= cable && hook <= cable + FLIGHT_CABLE_REACH)
                {
                    f->mode = FLIGHT_ARREST;
                    break;
                }
        }
    }
}
#endif
