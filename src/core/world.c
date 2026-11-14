#include "world.h"

void World_Reset(WorldState* state)
{
    Flight_Reset(&state->flight);
    state->x = (uint32_t)WINGS_WORLD_START * 256;
#ifdef WINGS_P1_FLIGHT
    state->camera = (uint16_t)(WINGS_WORLD_START - 128); /* centred: open sea beyond the map */
#else
    state->camera = WINGS_WORLD_START < 128 ? 0 :
        WINGS_WORLD_START > WINGS_WORLD_WIDTH - 128 ? WINGS_WORLD_WIDTH - 256 : WINGS_WORLD_START - 128;
#endif
    state->flight.x = (WINGS_WORLD_START - state->camera) * 256u;
}

void World_StepSample(WorldState* state, uint8_t input, uint8_t sample_view)
{
    uint16_t pixel;
    Flight_StepWorldSample(&state->flight, &state->x, input, sample_view);
    if (!sample_view) return;
    pixel = state->x >> 8;
#ifdef WINGS_P1_FLIGHT
    state->camera = pixel - 128;
#else
    state->camera = pixel < 128 ? 0 : pixel > WINGS_WORLD_WIDTH - 128 ? WINGS_WORLD_WIDTH - 256 : pixel - 128;
#endif
    state->flight.x = (pixel - state->camera) << 8;
}

void World_Step(WorldState* state, uint8_t input)
{
    World_StepSample(state, input, 1);
}
