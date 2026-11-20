#include "music.h"
#include "vdp.h"
#include "sound_fm.h"
#include "../core/game.h"
#include "../generated/music_data.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_MUSIC)

/* The music player (docs/music.md). The tracks (tools/convert_music.py)
 * tick at the original's rate, a fraction of a tick a field. With
 * MSX-MUSIC each track has its FM channel (0..3) and the drums the rhythm
 * section; with the PSG alone the song's instruments name a channel, and a
 * drum hit takes its channel over while it sounds. */

volatile u8 g_Music;

#define NO_SONG 255
#define FADE_FIELDS 8         /* a 3 dB step every 8 fields: about 2 s to silence */
#define DRUM_ATT 2            /* the rhythm section's level */

typedef struct Track {
    const u8* start;
    const u8* ptr;
    u16 wait, gate;
    const MusicInstrument* inst;
    u8 att, key;              /* key: register 0x20's value while it sounds */
} Track;
static Track s_Track[4];
static const MusicInstrument* s_Instruments;
static u8 s_Song, s_Rate, s_Fade, s_FadeTimer, s_Fading;
static u16 s_Acc;
/* PSG: per channel the melodic tone and volume, and a drum hit's state. */
static u16 s_Tone[3], s_DrumTone[3];
static u8 s_Volume[3], s_DrumKind[3], s_DrumVolume[3];

/* An OPLL write (sdcccall(1): A register, L value) with the chip's waits:
 * 12 of its cycles after the address, 84 after the data. */
static void FM(u8 reg, u8 value) __naked
{
    (void)reg; (void)value;
    __asm
        out (0x7c), a
        ld a, l
        nop
        out (0x7d), a
        ld a, #6
    fm_wait$:
        dec a
        jr nz, fm_wait$
        ret
    __endasm;
}

static void PSG(u8 reg, u8 value) __naked
{
    (void)reg; (void)value;
    __asm
        out (0xa0), a
        ld a, l
        out (0xa1), a
        ret
    __endasm;
}

static u8 Att(u8 a)
{
    a += s_Fade;
    return a > 15 ? 15 : a;
}

static u16 Number(Track* k)
{
    u8 b = *k->ptr++;
    u16 v;
    if (b) return b;
    v = k->ptr[0] | (u16)k->ptr[1] << 8;
    k->ptr += 2;
    return v;
}

static u8 Note(u8 note, i8 shift)
{
    i16 n = (i16)note + shift - MUSIC_MIDI_LOW;
    if (n < 0) n = 0;
    if (n > MUSIC_MIDI_HIGH - MUSIC_MIDI_LOW) n = MUSIC_MIDI_HIGH - MUSIC_MIDI_LOW;
    return (u8)n;
}

static void On(u8 t, u8 note)
{
    Track* k = &s_Track[t];
    const MusicInstrument* i = k->inst;
    u16 v;
    u8 c;
    if (g_SoundFM)
    {
        if (i->kind) { FM(0x0E, 0x20); FM(0x0E, 0x20 | i->fm); return; }
        v = g_MusicFM[Note(note, i->fm_shift)];
        FM(0x20 + t, 0);
        FM(0x10 + t, (u8)v);
        FM(0x30 + t, i->fm << 4 | Att(k->att));
        k->key = 0x10 | (u8)(v >> 8);   /* block << 1 | fnum bit 8 */
        FM(0x20 + t, k->key);
        return;
    }
    c = i->psg;
    if (c > 2) return;
    if (i->kind)
    {
        s_DrumKind[c] = i->psg_arg;
        s_DrumVolume[c] = 15 - k->att;
        s_DrumTone[c] = 0x200;
        return;
    }
    s_Tone[c] = g_MusicPSG[Note(note, (i8)i->psg_arg)];
    s_Volume[c] = 15 - k->att;
}

static void Off(u8 t)
{
    Track* k = &s_Track[t];
    const MusicInstrument* i = k->inst;
    if (i->kind) return;
    if (g_SoundFM) { FM(0x20 + t, k->key & 0x0F); k->key = 0; return; }
    if (i->psg <= 2) s_Volume[i->psg] = 0;
}

/* A track's commands up to its next note or rest. */
static void Read(u8 t)
{
    Track* k = &s_Track[t];
    u8 c;
    for (;;)
    {
        c = *k->ptr++;
        if (c == 0xFF) { k->ptr = k->start; continue; }
        if (c >= 0xA0) { k->wait = Number(k); return; }
        if (c >= 0x90) { k->att = c & 15; continue; }
        if (c >= 0x80) { k->inst = s_Instruments + (c & 15); continue; }
        k->gate = Number(k);
        k->wait = Number(k);
        On(t, c);
        return;
    }
}

static void Tick(void)
{
    u8 t;
    Track* k = s_Track;
    for (t = 0; t < 4; ++t, ++k)
    {
        if (k->gate && !--k->gate) Off(t);
        if (--k->wait) continue;
        Read(t);
    }
}

/* The fade's step reached the sounding notes. */
static void Volumes(void)
{
    u8 t, a = Att(DRUM_ATT);
    Track* k = s_Track;
    if (!g_SoundFM) return;   /* the PSG's volumes are faded as they are written */
    for (t = 0; t < 4; ++t, ++k)
        if (k->key) FM(0x30 + t, k->inst->fm << 4 | Att(k->att));
    FM(0x36, a);
    FM(0x37, a << 4 | a);
    FM(0x38, a << 4 | a);
}

/* The PSG's registers for this field: each channel its drum hit, else its
 * note; a hit's tone falls (kick) or its noise rings (snare, metal). */
static void PSGField(void)
{
    u8 c, mixer = 0xBF, noise = 7, v;
    u16 tone;
    for (c = 0; c < 3; ++c)
    {
        tone = s_Tone[c];
        v = s_Volume[c];
        if (s_DrumVolume[c])
        {
            v = s_DrumVolume[c];
            if (s_DrumKind[c] == 0)
            {
                tone = s_DrumTone[c]; s_DrumTone[c] += 0x100;
                mixer &= ~(1 << c);
                s_DrumVolume[c] = v > 2 ? v - 2 : 0;
            }
            else
            {
                noise = s_DrumKind[c] == 1 ? 7 : 1;
                mixer &= ~(8 << c);
                s_DrumVolume[c] = v > 2 ? v - (s_DrumKind[c] == 1 ? 2 : 1) : 0;
            }
        }
        else if (v) mixer &= ~(1 << c);
        PSG(c * 2, (u8)tone);
        PSG(c * 2 + 1, (u8)(tone >> 8));
        PSG(8 + c, v > s_Fade ? v - s_Fade : 0);
    }
    PSG(6, noise);
    PSG(7, mixer);   /* bit 7 port B output, bit 6 port A input (the joysticks) */
}

void Music_Field(void)
{
    if (s_Fading)
    {
        if (s_Fading == 2) return;   /* silent: the main program stops it */
        if (!--s_FadeTimer)
        {
            s_FadeTimer = FADE_FIELDS;
            if (s_Fade < 15) { ++s_Fade; Volumes(); }
            else s_Fading = 2;
        }
    }
    s_Acc += s_Rate;
    if (s_Acc >= 256) { s_Acc -= 256; Tick(); }
    if (!g_SoundFM) PSGField();
}

void Music_Init(void) WINGS_BANKED
{
    g_Music = 0;
    s_Song = NO_SONG;
    s_Fading = 0;
}

static void Start(u8 song)
{
    const MusicSong* s = &g_MusicSongs[song];
    u8 t;
    for (t = 0; t < 4; ++t)
    {
        s_Track[t].start = s_Track[t].ptr = s->track[t];
        s_Track[t].wait = 1; s_Track[t].gate = 0;
        s_Track[t].inst = s->instrument; s_Track[t].att = 0; s_Track[t].key = 0;
    }
    for (t = 0; t < 3; ++t) s_Tone[t] = s_Volume[t] = s_DrumVolume[t] = 0;
    s_Instruments = s->instrument;
    s_Rate = (g_VDP_REGSAV[9] & 2) ? s->rate_pal : s->rate_ntsc;
    s_Acc = 0; s_Fade = 0; s_Fading = 0;
    if (g_SoundFM)
    {
        /* The PSG quiet (the interrupt reads the joysticks through it:
         * not between an address and its data); rhythm mode, the drums at
         * the usual pitches and level. */
        __asm di __endasm;
        PSG(8, 0); PSG(9, 0); PSG(10, 0);
        __asm ei __endasm;
        for (t = 0; t < 9; ++t) FM(0x20 + t, 0);
        FM(0x0E, 0x20);
        FM(0x16, 0x20); FM(0x26, 0x05);
        FM(0x17, 0x50); FM(0x27, 0x05);
        FM(0x18, 0xC0); FM(0x28, 0x01);
        Volumes();
    }
    s_Song = song;
    g_Music = 1;
}

static void Stop(void)
{
    g_Music = 2;
    if (g_SoundFM) Sound_FMSetup();   /* the effects' instruments and drums */
    s_Song = NO_SONG;
    s_Fading = 0;
    g_Music = 0;   /* the effects' driver writes every PSG register again */
}

void Music_Update(u8 phase, u8 cursor) WINGS_BANKED
{
    u8 want = phase == GAME_INTRO ? (cursor < GAME_INTRO_STORY ? MUSIC_SUBSONG_1 : MUSIC_SUBSONG_2) :
              phase == GAME_RANK ? MUSIC_SUBSONG_4 : NO_SONG;
    if (want == s_Song) return;
    if (s_Song != NO_SONG)
    {
        /* The old song fades out first (0x2470); in play there is no music
         * at all (a quick start cuts the fade). */
        if (!s_Fading) { s_FadeTimer = FADE_FIELDS; s_Fading = 1; }
        if (s_Fading != 2 && phase != GAME_PLAY) return;
        Stop();
    }
    if (want != NO_SONG)
    {
        g_Music = 2;
        Start(want);
    }
}
