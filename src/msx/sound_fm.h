#ifndef WINGS_MSX_SOUND_FM_H
#define WINGS_MSX_SOUND_FM_H
#include "core.h"
#include "banking.h"

/* MSX-MUSIC (YM2413) sound, when the machine has it (docs/sound-effects.md):
 * the engine on two FM channels, the guns and bursts on the rhythm section,
 * and FM layers for the one-shot effects. Without it the PSG plays
 * everything, as before. Segment 26; the driver runs from RAM. */
extern u8 g_SoundFM;   /* 1 once MSX-MUSIC was found and its driver loaded */
/* The driver, copied into RAM: Sound_Field calls it each field. */
#define FM_DRIVER_BYTES 300
extern u8 g_FMDriver[FM_DRIVER_BYTES];

/* Look for MSX-MUSIC (built in, or an FM-PAC, which it enables), set the
 * chip up and load the driver and effects into RAM. Boot only. */
void Sound_InitFM(void) WINGS_BANKED;
/* The chip set up for the effects again (after the music, msx/music.c):
 * the driver's state as at boot. The interrupt must not run the driver
 * meanwhile (g_Music held). */
void Sound_FMSetup(void) WINGS_BANKED;
/* The engine drone from the original's Paula period and volume (of 64),
 * once per presented frame. */
void Sound_FMEngine(u16 period, u8 volume) WINGS_BANKED;
/* The enemy planes' engine on channel 4, the same way. */
void Sound_FMDrone(u16 period, u8 volume) WINGS_BANKED;
#endif
