#ifndef WINGS_MSX_SOUND_UPDATE_H
#define WINGS_MSX_SOUND_UPDATE_H
#include "core.h"
#include "banking.h"
#include "../core/flight.h"
#include "../core/combat.h"
#include "../core/carrier.h"

#define SOUND_PLAYING 1   /* in a sortie: otherwise everything is silent */
#define SOUND_CRASHED 2   /* the plane is wrecked: no engine */
extern CombatState g_Combat;     /* world_flight.c */
extern CarrierState g_Carrier;
/* Set the PSG driver's channels from the game state: the engine, the
 * guns, the lift; once per presented frame, steps flight steps after the
 * last. Segment 22. */
void Sound_Update(const FlightState* f, u16 world, u8 flags, u8 steps) WINGS_BANKED;
/* Copy the effects into RAM for the driver (flight start). */
void Sound_LoadEffects(void) WINGS_BANKED;
/* After a weapon tick with new impacts: the bombs that burst. */
void Sound_Bursts(void) WINGS_BANKED;
#endif
