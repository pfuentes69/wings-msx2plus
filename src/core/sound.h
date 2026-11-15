#ifndef WINGS_CORE_SOUND_H
#define WINGS_CORE_SOUND_H
#include <stdint.h>

/* The original's one-shot sound effects (docs/sound-effects.md): on the
 * MSX resynthesized as PSG effects on one channel, the higher priority
 * winning. */
#define SOUND_NONE 0
#define SOUND_SCREAM 1    /* a soldier hit (0x23ac) */
#define SOUND_SCREECH 2   /* the hook catching a cable, a bounce on deck (0x2380) */
#define SOUND_CLANG 3     /* the lift reaching its stop (0x2354) */
#define SOUND_SPLASH 4    /* a bomb or the plane into the sea (0x233e) */
#define SOUND_BOOM 5      /* a bomb burst on land or deck, a crash (0x2324) */
#define SOUND_COUNT 6

/* Play effect id heard from world x: quieter with the distance from the
 * plane (0x2306). Resident: callable from any segment. Tests stub it. */
void Sound_Effect(uint8_t id, uint16_t x);
#endif
