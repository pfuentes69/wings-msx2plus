#ifndef WINGS_MSX_MUSIC_H
#define WINGS_MSX_MUSIC_H
#include "core.h"
#include "banking.h"

/* The original's music (docs/music.md), on the front-end screens only, as
 * in the original: the title and credits (subsong 1), the story (2), rank
 * selection (4). Segment WINGS_SEGMENT_MUSIC with its data. */

/* 0 off (the effects' driver runs), 1 playing (the line interrupt maps the
 * music's segment and calls Music_Field instead), 2 held (the interrupt
 * does neither: the main program is setting the chips up). */
extern volatile u8 g_Music;

/* Boot: no song (RAM is not cleared). */
void Music_Init(void) WINGS_BANKED;
/* Once a presented frame: the song this screen wants (game phase and
 * cursor). A different one fades the old out first (about 2 s, as the
 * original); none stops the music and gives the chips back to the
 * effects. */
void Music_Update(u8 phase, u8 cursor) WINGS_BANKED;
/* One field of the player, from the line interrupt (msx/sound.c), with
 * the music's segment mapped in window 3. Not banked. */
void Music_Field(void);
#endif
