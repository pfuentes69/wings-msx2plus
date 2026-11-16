#include "sound.h"
#include "../core/flight.h"
#include "sound_fm.h"

/* The PSG driver (docs/sound-effects.md). Resident: it runs inside the
 * line interrupt, which never maps window 3, and Sound_Effect is called
 * from banked code. */
#ifdef WINGS_P1_FLIGHT

/* The effects' steps, copied into RAM from segment 22 at flight start
 * (Sound_LoadEffects): the interrupt cannot map a bank. */
SoundStep g_SoundSteps[SOUND_STEPS];
const SoundStep* g_SoundEffects[SOUND_COUNT];
#define s_Effects g_SoundEffects
static const u8 s_Priority[SOUND_COUNT] = {0, 1, 2, 2, 3, 4};

volatile u16 g_SoundEngineTone;
volatile u8 g_SoundEngineVolume, g_SoundGun, g_SoundGunRate, g_SoundGrind;
u16 g_SoundListener;
volatile u8 g_SoundRequest, g_SoundRequestAtten;   /* read by the FM driver too */
static const SoundStep* s_Step;
u8 g_SoundPlaying; static u8 s_Fields, s_Volume, s_Atten, s_Field, s_GunPhase;
static u16 s_Tone;
static u8 s_Regs[11];

void Sound_Reset(void)
{
    g_SoundFM = 0;   /* until Sound_InitFM has loaded the FM driver */
    g_SoundEngineVolume = g_SoundGun = g_SoundGrind = 0;
    g_SoundGunRate = 6;
    g_SoundRequest = g_SoundPlaying = 0;
}

void Sound_Effect(u8 id, u16 x)
{
    i16 d = (i16)(x - g_SoundListener);
    u16 distance = d < 0 ? (u16)-d : (u16)d;
    /* 0x2306: volume 64 - distance / 32 of 64; a PSG step per 128 px. */
    u8 atten = distance >= 15 * 128 ? 15 : (u8)(distance >> 7);
    if (s_Priority[id] < s_Priority[g_SoundPlaying] || s_Priority[id] < s_Priority[g_SoundRequest]) return;
    g_SoundRequestAtten = atten;
    g_SoundRequest = id;
}

/* In Z80: SDCC's C for this was 600 bytes, and resident space is short.
 * The statics are used by their labels. */
typedef char SoundStepLayout[sizeof(SoundStep) == 7 ? 1 : -1];

void Sound_Field(void) __naked
{
    __asm
        ; MSX-MUSIC, when found: its driver, copied into RAM (sound_fm.c)
        ld a, (_g_SoundFM)
        or a
        call nz, _g_FMDriver
        ld hl, #_s_Field
        inc (hl)
        ld c, (hl)              ; c: the field count
        ld de, #0x3f01          ; d: mixer (1 = off), e: noise period
        ; A: the engine, + 1/32 on odd fields (a slight throb)
        ld hl, (_g_SoundEngineTone)
        bit 0, c
        jr z, sound_engine$
        push hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld a, h
        pop hl
        add a, l
        ld l, a
        jr nc, sound_engine$
        inc h
    sound_engine$:
        ld (_s_Regs + 0), hl
        ld a, (_g_SoundEngineVolume)
        ld (_s_Regs + 8), a
        or a
        jr z, sound_b$
        res 0, d
    sound_b$:
        ; B: the lift grind, else the guns
        ld b, #0
        ld a, (_g_SoundGrind)
        or a
        jr z, sound_gun$
        ld b, #10
        ld a, c
        and #7
        cp #4
        jr c, sound_grind$
        ld b, #6
    sound_grind$:
        ld e, #20
        ld hl, #1200
        ld (_s_Regs + 2), hl
        ld a, d
        and #0xed               ; tone and noise B on
        ld d, a
        jr sound_b_done$
    sound_gun$:
        ld a, (_g_SoundGun)
        or a
        jr z, sound_b_done$
        ld l, a                 ; l: its volume
        ld a, (_g_SoundGunRate)
        ld h, a
        ld a, (_s_GunPhase)
        inc a
        cp h
        jr c, sound_phase$
        xor a
    sound_phase$:
        ld (_s_GunPhase), a
        ld b, l                 ; a burst: v, v - 3, v - 7, then quiet
        or a
        jr z, sound_gun_on$
        ld h, #3
        dec a
        jr z, sound_gun_less$
        ld h, #7
        dec a
        jr z, sound_gun_less$
        ld b, #0
        jr sound_gun_on$
    sound_gun_less$:
        ld a, l
        sub h
        jr nc, sound_gun_vol$
        xor a
    sound_gun_vol$:
        ld b, a
    sound_gun_on$:
        res 4, d
    sound_b_done$:
        ld a, b
        ld (_s_Regs + 9), a
        ; C: a new effect starts
        ld a, (_g_SoundRequest)
        or a
        jr z, sound_c$
        cp #SOUND_COUNT
        jr nc, sound_c$
        ld (_g_SoundPlaying), a
        add a, a
        ld l, a
        ld h, #0
        ld bc, #_g_SoundEffects
        add hl, bc
        ld a, (hl)
        inc hl
        ld h, (hl)
        ld l, a
        ld (_s_Step), hl
        ld a, (_g_SoundRequestAtten)
        ld (_s_Atten), a
        xor a
        ld (_g_SoundRequest), a
        call sound_load$
    sound_c$:
        ld b, #0
        ld a, (_g_SoundPlaying)
        or a
        jr z, sound_c_done$
        ld a, (_s_Volume)       ; volume: the step volume, less the distance
        rrca
        rrca
        rrca
        rrca
        and #15
        ld hl, #_s_Atten
        sub (hl)
        jr nc, sound_c_vol$
        xor a
    sound_c_vol$:
        ld b, a
        ld hl, (_s_Tone)
        ld (_s_Regs + 4), hl
        ld ix, (_s_Step)
        ld a, 3 (ix)            ; mix
        bit 0, a
        jr z, sound_c_tone$
        res 2, d
    sound_c_tone$:
        bit 1, a
        jr z, sound_c_noise$
        res 5, d
        rrca
        rrca
        and #31
        ld e, a
    sound_c_noise$:
        ld a, (_s_Volume)       ; volume += dvolume, within 0..255
        ld l, a
        ld h, 2 (ix)
        add a, h
        bit 7, h
        jr nz, sound_c_down$
        jr nc, sound_c_set$
        ld a, #255
        jr sound_c_set$
    sound_c_down$:
        jr c, sound_c_set$
        xor a
    sound_c_set$:
        ld (_s_Volume), a
        ld a, 6 (ix)            ; tone += dtone
        ld l, a
        add a, a
        sbc a, a
        ld h, a
        push bc
        ld bc, (_s_Tone)
        add hl, bc
        ld (_s_Tone), hl
        pop bc
        ld hl, #_s_Fields
        dec (hl)
        jr nz, sound_c_done$
        push de
        ld de, #7
        add ix, de
        ld (_s_Step), ix
        call sound_load$
        pop de
    sound_c_done$:
        ld a, b
        ld (_s_Regs + 10), a
        ld a, e
        ld (_s_Regs + 6), a
        ld a, d                 ; port A input (bit 6 = 0: joysticks), port B output (bit 7)
        or #0x80
        ld (_s_Regs + 7), a
        ld hl, #_s_Regs
        ld bc, #0x0b00
    sound_out$:
        ld a, c
        out (0xa0), a
        ld a, (hl)
        out (0xa1), a
        inc hl
        inc c
        djnz sound_out$
        ret
    sound_load$:                ; the step at s_Step: its fields, volume, tone
        ld hl, (_s_Step)
        ld a, (hl)
        ld (_s_Fields), a
        or a
        jr nz, sound_load_step$
        ld (_g_SoundPlaying), a      ; the end
        ret
    sound_load_step$:
        inc hl
        ld a, (hl)
        ld (_s_Volume), a
        inc hl
        inc hl
        inc hl
        ld a, (hl)
        inc hl
        ld h, (hl)
        ld l, a
        ld (_s_Tone), hl
        ret
    __endasm;
}

/* An MSX-MUSIC register write: A the register, E the value. The YM2413
 * needs 12 of its cycles (T-states at 3.58 MHz) after the address, which
 * this gives, and 84 after the data, which the caller must leave before its
 * next write (tests/test_sound_fm_z80.py checks the FM driver's). Preserves
 * everything but A. */
void Sound_OPLLWrite(void) __naked
{
    __asm
        out (0x7c), a
        ld a, e
        out (0x7d), a
        ret
    __endasm;
}
#endif
