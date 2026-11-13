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

/* P1 values are tuning data, not recovered Amiga physics. Deck bounds follow
 * fcar/mcar/rcar drawing extents; Y rests the level crop above viewport row 129.
 * Reset X is a provisional parking point, not a recovered elevator location. */
#define FLIGHT_DECK_LEFT 6593u
#define FLIGHT_DECK_RIGHT 7361u
#define FLIGHT_TAXI_MIN_X (FLIGHT_DECK_LEFT + 24u)
#define FLIGHT_TAXI_MAX_X (FLIGHT_DECK_RIGHT - 25u)
#define FLIGHT_TAXI_STEP_TICKS 24u
#define FLIGHT_TAXI_TURN_TICKS (10u * FLIGHT_TAXI_STEP_TICKS)
#define FLIGHT_DECK_Y 1160u
#define FLIGHT_TAKEOFF_SPEED 154
/* 154 speed steps * 5 ticks / 150 Hz = 5.13 seconds from rest. */
#define FLIGHT_GROUND_ACCEL_TICKS 5u
#define FLIGHT_LAUNCH_ZONE (FLIGHT_DECK_LEFT + 64u)
#define FLIGHT_GROUND 0
#define FLIGHT_AIRBORNE 1
#define FLIGHT_STALL 2
#define FLIGHT_STALL_DIVE 3 /* Latched nose-down dive; cleared by Up or horizontal input. */
#define FLIGHT_TURN_TICKS 110u

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

/* Positions are unsigned Q8 pixels. Velocities are signed Q8 pixels/tick.
 * One simulation tick is 1/150 second, independent of the video standard. */
typedef struct FlightState {
    uint16_t x;
    FlightVertical y;
    int16_t vx, vy;
    uint8_t frame; /* 0 climb, 1 level, 2 dive */
    uint8_t facing_left;
#ifdef WINGS_P1_FLIGHT
    uint8_t mode, turn_ticks, target_left, ground_tick;
#endif
} FlightState;

#ifdef WINGS_P1_FLIGHT
/* Gear is automatic: ground support or a low, inbound carrier approach.
 * This is presentation eligibility, not hook capture or landing collision. */
uint8_t Flight_GearDown(const FlightState* state, uint16_t world);
#endif

void Flight_Reset(FlightState* state);
void Flight_Step(FlightState* state, uint8_t input);
/* World variant keeps x in unsigned Q8 over the configured bounded world. */
void Flight_StepWorld(FlightState* state, uint32_t* x, uint8_t input);
/* Same physics and persistent facing; update derived pitch only when sampled. */
void Flight_StepWorldSample(FlightState* state, uint32_t* x, uint8_t input, uint8_t sample_pose);
#endif
