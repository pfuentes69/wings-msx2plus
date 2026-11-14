#include "landing.h"

#ifdef WINGS_P1_FLIGHT
uint8_t Landing_Contact(const FlightState* flight, uint16_t world, uint8_t engine_failed)
{
    if (flight->mode == FLIGHT_GROUND) return LANDING_NONE;
    if (world >= FLIGHT_DECK_LEFT && world <= FLIGHT_DECK_RIGHT)
    {
        if (flight->y <= (FlightVertical)FLIGHT_DECK_Y * 256u) return LANDING_NONE;
        if (flight->y > (FlightVertical)(FLIGHT_DECK_Y + LANDING_DEPTH) * 256u ||
            world < FLIGHT_DECK_LEFT + LANDING_EDGE || world > FLIGHT_DECK_RIGHT - LANDING_EDGE ||
            engine_failed)
            return LANDING_CRASH;   /* hull, deck end, or no power */
        return flight->mode == FLIGHT_STALL && flight->facing_left ? LANDING_LANDED : LANDING_BOUNCE;
    }
    /* Sea or island: flat at sea level until per-object heights are mapped. */
    return flight->y >= FLIGHT_MAX_Y ? LANDING_CRASH : LANDING_NONE;
}

void Landing_Apply(FlightState* flight, uint8_t contact)
{
    if (contact == LANDING_LANDED)
    {
        /* Caught: on the deck facing left. The ground model brakes the plane
         * to a stop (provisional arrest; no cable geometry in the original). */
        flight->mode = FLIGHT_GROUND;
        flight->y = (FlightVertical)FLIGHT_DECK_Y * 256u;
        flight->vy = 0;
        flight->facing_left = flight->target_left = 1;
        flight->turn_ticks = flight->ground_tick = 0;
    }
    else if (contact == LANDING_BOUNCE)
    {
        flight->vy = (int16_t)-flight->vy;
        flight->y -= (FlightVertical)LANDING_BOUNCE_LIFT * 256u;
    }
}
#endif
