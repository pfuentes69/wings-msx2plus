#ifndef WINGS_FLIGHT_H
#define WINGS_FLIGHT_H
#include <stdint.h>

#define FLIGHT_UP 1
#define FLIGHT_RIGHT 2
#define FLIGHT_DOWN 4
#define FLIGHT_LEFT 8
#define FLIGHT_MAX_X (208u * 256u)
#define FLIGHT_MAX_Y (180u * 256u)

/* Positions are unsigned Q8 pixels. Velocities are signed Q8 pixels/tick.
 * One simulation tick is 1/150 second, independent of the video standard. */
typedef struct FlightState {
    uint16_t x, y;
    int16_t vx, vy;
    uint8_t frame; /* 0 climb, 1 level, 2 dive */
    uint8_t facing_left;
} FlightState;

void Flight_Reset(FlightState* state);
void Flight_Step(FlightState* state, uint8_t input);
#endif
