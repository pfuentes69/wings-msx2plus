#include "landing.h"
#include "aircraft.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_SCENE)
#ifdef WINGS_P1_FLIGHT
#include "mission_heights.h"
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
#ifdef WINGS_MAP_RECORD   /* the runs stay in the map's bank: resident code reads them */
    return Mission_Height(world);
#else
    uint8_t low = 0, high = MISSION_HEIGHT_RUNS, middle;
    while (low < high)
    {
        middle = low + ((high - low) >> 1);
        if (world < s_MissionHeightEnd[middle]) high = middle;
        else low = middle + 1;
    }
    return low < MISSION_HEIGHT_RUNS ? s_MissionHeight[low] : 0;
#endif
}

uint8_t Landing_Contact(const FlightState* flight, uint16_t world, uint8_t engine_failed, uint8_t bottom, uint8_t height) WINGS_BANKED
{
    /* The plane's bottom above the sea, Q8 pixels. */
    int32_t base = (int32_t)FLIGHT_MAX_Y - (int32_t)flight->y - (int32_t)bottom * 256;
    if (FLIGHT_ON_DECK(flight)) return LANDING_NONE;
    if (world >= FLIGHT_DECK_LEFT && world <= FLIGHT_DECK_RIGHT)
    {
        if (base >= (int32_t)LANDING_DECK_HEIGHT * 256) return LANDING_NONE;
        /* Leaving over a deck end (a takeoff below flying speed sinks a
         * little): the MSX lets the plane clear the last 16 px. The
         * original's bow and stern geometry is not mapped. */
        if (flight->facing_left ? world < FLIGHT_DECK_LEFT + LANDING_EDGE : world > FLIGHT_DECK_RIGHT - LANDING_EDGE)
            return base < (int32_t)(LANDING_DECK_HEIGHT - LANDING_DEPTH) * 256 ? LANDING_CRASH : LANDING_NONE;
        if (base < (int32_t)(LANDING_DECK_HEIGHT - LANDING_DEPTH) * 256 ||
            world < FLIGHT_DECK_LEFT + LANDING_EDGE || world > FLIGHT_DECK_RIGHT - LANDING_EDGE ||
            engine_failed || flight->turn)
            return LANDING_CRASH;   /* hull, deck end, no power, or turning (0xba80) */
        /* 0xba80: holding the stall flare facing left lands. Any other deck
         * contact bounces: heading right, the hook cannot catch. */
        return flight->landing && flight->facing_left ? LANDING_LANDED : LANDING_BOUNCE;
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
    /* The original applies contact at the end of its tick, after the
     * move, so the rest of this tick's vertical motion is dropped. */
    flight->vy = 0;
    flight->yrem = 0;
    if (contact == LANDING_LANDED)
    {
        /* On deck at flying speed: the plane rolls on, and holding UP lets
         * the hook catch a cable (Flight_Tick). */
        flight->mode = FLIGHT_GROUND;
        flight->y = (FlightVertical)FLIGHT_DECK_Y * 256u;
    }
    else if (contact == LANDING_BOUNCE)
    {
        flight->climb = -flight->climb;
        flight->y -= (FlightVertical)LANDING_BOUNCE_LIFT * 256u;
    }
}
#endif
