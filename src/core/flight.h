#ifndef WINGS_FLIGHT_H
#define WINGS_FLIGHT_H
#include <stdint.h>
#ifndef WINGS_WORLD_WIDTH
#define WINGS_WORLD_WIDTH 4096u
#endif
#ifndef WINGS_WORLD_START
#define WINGS_WORLD_START 104u
#endif

#if defined(MISSION_TERRAIN) && !defined(WINGS_DEBUG_CONTROLS)
#define WINGS_P1_FLIGHT 1
#endif

/* Carrier geometry. Deck bounds follow the fcar/mcar/rcar drawing extents
 * (the original's landing range is the carrier map extents x 4, 16 px inward
 * at each end); the deck row rests a plane on its wheels at deck height. */
#define FLIGHT_DECK_LEFT 6593u
#define FLIGHT_DECK_RIGHT 7361u
#define FLIGHT_DECK_EDGE 16u
#define FLIGHT_DECK_Y 1160u
/* The original's carrier position (-$5c6c): the elevator, where a new plane
 * starts. Gear comes down within FLIGHT_GEAR_RANGE of it, and the four
 * arresting cables lie at +70, +126, +182, +238 (0xb92e). */
#define FLIGHT_CARRIER_X 7032u
#define FLIGHT_GEAR_RANGE 1280u
#define FLIGHT_CABLE_FIRST 70u
#define FLIGHT_CABLE_SPACING 56u
#define FLIGHT_CABLE_REACH 8u
#define FLIGHT_HOOK 24u
/* The original runs its logic once per 4 PAL VBlanks (12.5 Hz): one tick is
 * 12 steps of the port's 150 Hz simulation clock. */
#define FLIGHT_TICK_STEPS 12u
/* World x is a 16-bit ring read as signed: the map is 0..WINGS_WORLD_WIDTH-1
 * and open sea continues FLIGHT_SEA_LIMIT px beyond either end, as in the
 * original, which never limits the plane's x. The limit keeps every signed
 * world and camera value within int16. */
#define FLIGHT_SEA_LIMIT 16000

/* Modes (the original's player mode in brackets). */
#define FLIGHT_GROUND 0   /* on deck: taxi, takeoff roll [1] */
#define FLIGHT_AIRBORNE 1 /* [0] */
#define FLIGHT_ARREST 2   /* caught by a cable, braking to a stop [7] */
#define FLIGHT_DEAD 3     /* engine failed: falling, no control [4] */
#define FLIGHT_ON_DECK(f) ((f)->mode == FLIGHT_GROUND || (f)->mode == FLIGHT_ARREST)

#define FLIGHT_UP 1
#define FLIGHT_RIGHT 2
#define FLIGHT_DOWN 4
#define FLIGHT_LEFT 8
#define FLIGHT_MAX_X (208u * 256u)
#ifndef WINGS_FLIGHT_MAX_Y
#define WINGS_FLIGHT_MAX_Y 180u
#endif
#ifndef WINGS_FLIGHT_START_Y
#define WINGS_FLIGHT_START_Y 88u
#endif
#define FLIGHT_MAX_Y (WINGS_FLIGHT_MAX_Y * 256UL)
#if WINGS_FLIGHT_MAX_Y > 255
typedef uint32_t FlightVertical;
#else
typedef uint16_t FlightVertical;
#endif

/* Positions are unsigned Q8 pixels. Velocities are signed Q8 pixels/step.
 * One simulation step is 1/150 second, independent of the video standard. */
typedef struct FlightState {
    uint16_t x;
    FlightVertical y;
    int16_t vx, vy;
    uint8_t frame; /* legacy: 0 climb, 1 level, 2 dive. P1: pitch pose 0..9 (4 level) */
    uint8_t facing_left;
#ifdef WINGS_P1_FLIGHT
    /* The original's flight variables (docs/research/amiga-fuel-oil.md),
     * in its units: speed 0..1400 (100 = 1 px per tick), angles in
     * hundredths of a degree. */
    uint8_t mode;
    uint8_t turn;       /* turn frame: 0..25 in the air, 0..6 on deck (-$5bf0) */
    uint8_t turn_clock; /* ticks to the next air-turn frame (-$555e) */
    uint8_t step;       /* simulation step within the original tick */
    uint8_t landing;    /* UP alone facing left: the stall flare (-$5554) */
    uint8_t fast_roll;  /* on deck above speed 600 without UP: tail up (-$5562) */
    uint8_t throttle;   /* pushing the way the plane flies (-$3216) */
    int8_t xrem, yrem;  /* steps of this tick that move one extra Q8 unit */
    int16_t speed;      /* -$5bea */
    int16_t climb;      /* commanded climb angle (-$5bfc) */
    int16_t path;       /* flight path angle, lags the climb (-$555c) */
    int16_t cancel;     /* small-climb correction (-$5bf6) */
    int16_t boost;      /* acceleration counter (-$3214) */
#endif
} FlightState;

#ifdef WINGS_P1_FLIGHT
/* Gear: always on deck; in the air within FLIGHT_GEAR_RANGE of the carrier,
 * in either direction; up after an engine failure (0xb45a). */
uint8_t Flight_GearDown(const FlightState* state, uint16_t world);
/* The cable (0..3) holding the plane during the arrest (the original's
 * -$42c4); drawn as the stretched rope. Its x is FLIGHT_CABLE_X(cable). */
extern uint8_t g_FlightCable;
#define FLIGHT_CABLE_X(cable) (FLIGHT_CARRIER_X + FLIGHT_CABLE_FIRST + (cable) * FLIGHT_CABLE_SPACING)
#endif

void Flight_Reset(FlightState* state);
void Flight_Step(FlightState* state, uint8_t input);
/* World variant keeps x in unsigned Q8 over the configured bounded world. */
void Flight_StepWorld(FlightState* state, uint32_t* x, uint8_t input);
/* Same physics and persistent facing; update derived pitch only when sampled. */
void Flight_StepWorldSample(FlightState* state, uint32_t* x, uint8_t input, uint8_t sample_pose);
#endif
