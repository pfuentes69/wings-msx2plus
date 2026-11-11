#ifndef WINGS_FLIGHT_H
#define WINGS_FLIGHT_H
#include <stdint.h>
#ifndef WINGS_WORLD_WIDTH
#define WINGS_WORLD_WIDTH 4096u
#endif
#ifndef WINGS_WORLD_START
#define WINGS_WORLD_START 104u
#endif

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
} FlightState;

void Flight_Reset(FlightState* state);
void Flight_Step(FlightState* state, uint8_t input);
/* World variant keeps x in unsigned Q8 over the configured bounded world. */
void Flight_StepWorld(FlightState* state, uint32_t* x, uint8_t input);
/* Same physics and persistent facing; update derived pitch only when sampled. */
void Flight_StepWorldSample(FlightState* state, uint32_t* x, uint8_t input, uint8_t sample_pose);
#endif
