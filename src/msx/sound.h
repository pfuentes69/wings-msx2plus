#ifndef WINGS_MSX_SOUND_H
#define WINGS_MSX_SOUND_H
#include "core.h"
#include "../core/sound.h"

/* The PSG sound driver (docs/sound-effects.md), resident. Sound_Field runs
 * once per video field at the end of the dashboard line interrupt (the
 * budget of docs/sound-budget.md) and writes PSG registers 0..10:
 *  A: the engine drone, g_SoundEngineTone / g_SoundEngineVolume;
 *  B: the lift's grind (g_SoundGrind), else gunfire (g_SoundGun volume,
 *     one burst every g_SoundGunRate fields);
 *  C: the one-shot effects (Sound_Effect).
 * The game sets these once per presented frame (Sound_Update). */
/* An effect is a list of steps; each holds its tone and volume for
 * `fields` fields, sliding them by dtone / dvolume a field. Volume is 4.4
 * fixed point. mix: bit 0 tone, bit 1 noise, bits 2..6 the noise period.
 * A step of 0 fields ends it. */
typedef struct SoundStep {
    u8 fields, volume;
    i8 dvolume;
    u8 mix;
    u16 tone;
    i8 dtone;
} SoundStep;
#define SOUND_STEPS 24
extern SoundStep g_SoundSteps[SOUND_STEPS];
extern const SoundStep* g_SoundEffects[SOUND_COUNT];
extern volatile u16 g_SoundEngineTone;
extern volatile u8 g_SoundEngineVolume, g_SoundGun, g_SoundGunRate, g_SoundGrind;
extern u16 g_SoundListener;   /* the plane's world x */
extern u8 g_SoundPlaying;     /* the effect on channel C, SOUND_NONE when quiet */
extern volatile u8 g_SoundRequest, g_SoundRequestAtten;   /* the effect to start next field */
void Sound_Field(void);
/* One MSX-MUSIC register write (A register, E value), with the chip's waits;
 * for the FM driver (sound_fm.c). */
void Sound_OPLLWrite(void);
/* Silence everything and turn the FM driver off until Sound_InitFM (boot:
 * before any line interrupt runs the driver). */
void Sound_Reset(void);
#endif
