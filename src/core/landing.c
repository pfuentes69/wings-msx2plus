#include "landing.h"
#include "aircraft.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_SCENE)
#ifdef WINGS_P1_FLIGHT
#include "../generated/mission_heights.h"
#endif

#ifdef WINGS_P1_FLIGHT
static const uint8_t s_Bottom[11] = {2, 12, 10, 6, 4, 2, 5, 7, 9, 12, 14};
static const uint8_t s_GearBottom[11] = {5, 4, 3, 3, 3, 5, 3, 2, 1, 0, 0};

uint8_t Landing_Bottom(uint8_t pitch, uint8_t gear) WINGS_BANKED
{
    uint8_t pose = pitch < 10 ? pitch + 1 : 0;
    return s_Bottom[pose] + (gear ? s_GearBottom[pose] : 0);
}

uint8_t Landing_Height(uint16_t world) WINGS_BANKED
{
    uint8_t low = 0, high = MISSION_HEIGHT_RUNS, middle;
    while (low < high)
    {
        middle = low + ((high - low) >> 1);
        if (world < s_MissionHeightEnd[middle]) high = middle;
        else low = middle + 1;
    }
    return low < MISSION_HEIGHT_RUNS ? s_MissionHeight[low] : 0;
}

uint8_t Landing_Contact(const FlightState* flight, uint16_t world, uint8_t engine_failed, uint8_t bottom, uint8_t height) WINGS_BANKED
{
    /* The plane's bottom above the sea, Q8 pixels. */
    int32_t base = (int32_t)FLIGHT_MAX_Y - (int32_t)flight->y - (int32_t)bottom * 256;
    if (flight->mode == FLIGHT_GROUND) return LANDING_NONE;
    if (world >= FLIGHT_DECK_LEFT && world <= FLIGHT_DECK_RIGHT)
    {
        if (base >= (int32_t)LANDING_DECK_HEIGHT * 256) return LANDING_NONE;
        if (base < (int32_t)(LANDING_DECK_HEIGHT - LANDING_DEPTH) * 256 ||
            world < FLIGHT_DECK_LEFT + LANDING_EDGE || world > FLIGHT_DECK_RIGHT - LANDING_EDGE ||
            engine_failed)
            return LANDING_CRASH;   /* hull, deck end, or no power */
        return flight->mode == FLIGHT_STALL && flight->facing_left ? LANDING_LANDED : LANDING_BOUNCE;
    }
    /* Sea or scenery: below its static height, or the bottom at the sea. */
    return base < (int32_t)height * 256 || base <= 0 ? LANDING_CRASH : LANDING_NONE;
}

void Landing_Prepare(const FlightState* flight, uint16_t world, uint8_t* bottom, uint8_t* surface) WINGS_BANKED
{
    *bottom = Landing_Bottom(Aircraft_FlightPitch(flight), Flight_GearDown(flight, world));
    *surface = world >= FLIGHT_DECK_LEFT && world <= FLIGHT_DECK_RIGHT ? LANDING_DECK_HEIGHT : Landing_Height(world);
}

void Landing_Apply(FlightState* flight, uint8_t contact) WINGS_BANKED
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
