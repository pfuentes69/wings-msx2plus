#ifndef WINGS_LANDING_H
#define WINGS_LANDING_H
#include <stdint.h>
#include "flight.h"
#include "../msx/banking.h"

/* Contact with the carrier, the sea or the ground, after the Amiga rules in
 * docs/research/amiga-fuel-oil.md (0xba80/0xb8c4/0x5710): touching the deck
 * from above in the stall flare (Up alone) facing left, not turning, lands;
 * other deck contact bounces;
 * the sea, scenery at its static height, deck ends and the hull crash.
 * Resting exactly at deck height is not contact. */
#define LANDING_NONE 0
#define LANDING_LANDED 1
#define LANDING_BOUNCE 2
#define LANDING_CRASH 3
#define LANDING_EDGE 16u      /* landing range excludes 16 px at each deck end */
#define LANDING_DEPTH 4u      /* at most 4 px into the deck */
#define LANDING_BOUNCE_LIFT 6u
/* Altitude is 1200 - y pixels (sea level 0). Contact compares the plane's
 * bottom, altitude - bottom offset, with the surface: Amiga 0xb8c4. The deck
 * stands 33 px up, so a resting plane (pose 0 with gear: 2 + 5 px) has its
 * origin at the port's deck row 1160. */
#define LANDING_DECK_HEIGHT 33u
/* Highest surface plus the deepest bottom: no contact is possible above. */
#define LANDING_CHECK_Y (FLIGHT_MAX_Y - 56u * 256u)

#ifdef WINGS_P1_FLIGHT
/* Bottom offset in pixels for a pitch pose 0..9 (original poses 1..10), with
 * the extra gear-down depth (Amiga 0xaaea tables at -$5552 / -$553c). */
/* Banked (segment 16); called only below LANDING_CHECK_Y. */
uint8_t Landing_Bottom(uint8_t pitch, uint8_t gear) WINGS_BANKED;
/* Static scenery height at world x (0 for sea, beach and the carrier). */
uint8_t Landing_Height(uint16_t world) WINGS_BANKED;
uint8_t Landing_Contact(const FlightState* flight, uint16_t world, uint8_t engine_failed, uint8_t bottom, uint8_t height) WINGS_BANKED;
void Landing_Apply(FlightState* flight, uint8_t contact) WINGS_BANKED;
/* Once per presented frame: the plane's bottom offset and the surface height
 * under it (the deck over the carrier). The per-step gate in the main loop
 * compares against these and calls Landing_Contact only on a hit. */
void Landing_Prepare(const FlightState* flight, uint16_t world, uint8_t* bottom, uint8_t* surface) WINGS_BANKED;
#endif
#endif
