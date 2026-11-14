#ifndef WINGS_LANDING_H
#define WINGS_LANDING_H
#include <stdint.h>
#include "flight.h"

/* Contact with the carrier, the sea or the ground, after the Amiga rules in
 * docs/research/amiga-fuel-oil.md (0xba80/0xb8c4): touching the deck from
 * above while stalling facing left lands; other deck contact bounces; any
 * other contact crashes. Resting exactly at deck height is not contact. */
#define LANDING_NONE 0
#define LANDING_LANDED 1
#define LANDING_BOUNCE 2
#define LANDING_CRASH 3
#define LANDING_EDGE 16u      /* landing range excludes 16 px at each deck end */
#define LANDING_DEPTH 4u      /* at most 4 px into the deck */
#define LANDING_BOUNCE_LIFT 6u

#ifdef WINGS_P1_FLIGHT
uint8_t Landing_Contact(const FlightState* flight, uint16_t world, uint8_t engine_failed);
void Landing_Apply(FlightState* flight, uint8_t contact);
#endif
#endif
