#include "sound_fm.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_SOUND)
#include "sound.h"
#include "../core/flight.h"
#include "../generated/fm_pitch.h"

/* MSX-MUSIC (docs/sound-effects.md). The YM2413 runs in rhythm mode:
 *  channels 0, 1: the engine, the custom instrument, 3% apart so the two
 *                 beat like a radial engine;
 *  channels 2, 3: the melodic effects (clang, screech, scream);
 *  channels 4, 5: free (music, later);
 *  rhythm:        snare and hi-hat for the guns; bass drum, tom and cymbal
 *                 for bursts and splashes.
 * The PSG keeps the lift's grind and layers noise under the bursts.
 *
 * The driver runs in the line interrupt, which never maps window 3, so it
 * is copied into RAM with its scripts. It uses relative jumps only; its
 * absolute references are RAM and the resident Sound_OPLLWrite. */
#ifdef WINGS_P1_FLIGHT

u8 g_SoundFM;
u8 g_FMDriver[FM_DRIVER_BYTES];
#define FM_SCRIPT_BYTES 400
static u8 s_ScriptData[FM_SCRIPT_BYTES];
u8* g_FMScripts[SOUND_COUNT];
/* The engine's registers as (register, value, last written): the driver
 * writes a value when it changed. Sound_FMEngine sets the values. */
u8 g_FMEngine[18];
static volatile u8 s_FMEngineDirty;   /* values changed since the driver looked */
static u16 s_FMPeriod;
static u8* s_FMScript;
static u8 s_FMWait, s_FMAtten, s_FMGunPhase, s_FMKeys;
/* Writes left this field: 4 (~270 T-states each) keep the sound under its
 * 3,000 T-states with the PSG's ~1,000-1,400 (docs/sound-budget.md). The
 * engine takes at most 2, a gun hit 3; what does not fit waits a field. */
static u8 s_FMBudget;

__sfr __at 0x7C s_OPLLIndex;
__sfr __at 0x7D s_OPLLData;

/* A script is (register, value) pairs. Volume registers (0x30..0x38) lose
 * a step per 128 px of distance, like the PSG effects. */
#define W(r, v) (r), (v)
#define WAIT(n) 0xFF, (n)          /* go on n fields later */
#define END 0xFE, 0
#define FL(f) ((f) & 255)
#define FH(f, b) (0x10 | (b) << 1 | (f) >> 8)     /* key on, block b */
#define FOFF(f, b) ((b) << 1 | (f) >> 8)          /* key off: the release */
#define NOTE(ch, f, b) W(0x10 + (ch), FL(f)), W(0x20 + (ch), FH(f, b))
/* Frequency: f = fnum x 49,716 / 2^(19 - block) Hz. Rhythm keys (0x0E):
 * 0x20 rhythm mode, 0x10 bass drum, 8 snare, 4 tom, 2 cymbal, 1 hi-hat;
 * a drum sounds when its bit goes from 0 to 1. */

/* A soldier hit: a violin wavering 600..900 Hz, then falling to 400 Hz
 * (the PSG version's contour, 0x23ac), at full volume: its slow bow
 * attack makes it quieter than the other effects. */
static const u8 s_Scream[] = {
    W(0x23, 0), W(0x33, 0x10), NOTE(3, 230, 5), WAIT(2),
    NOTE(3, 252, 5), WAIT(2), NOTE(3, 275, 5), WAIT(2), NOTE(3, 297, 5), WAIT(2),
    NOTE(3, 265, 5), WAIT(2), NOTE(3, 232, 5), WAIT(2), NOTE(3, 200, 5), WAIT(2),
    NOTE(3, 224, 5), WAIT(2), NOTE(3, 247, 5), WAIT(2), NOTE(3, 271, 5), WAIT(2),
    NOTE(3, 240, 5), WAIT(2), NOTE(3, 208, 5), WAIT(2), NOTE(3, 177, 5), WAIT(2),
    NOTE(3, 203, 5), WAIT(2), NOTE(3, 230, 5), W(0x33, 0x12), WAIT(3),
    NOTE(3, 205, 5), W(0x33, 0x14), WAIT(3), NOTE(3, 180, 5), W(0x33, 0x17), WAIT(3),
    NOTE(3, 156, 5), W(0x33, 0x1A), WAIT(3), NOTE(3, 132, 5), W(0x33, 0x1D), WAIT(3),
    W(0x23, FOFF(132, 5)), END};
/* The hook catching a cable, a bounce: an oboe squealing ~1.7 kHz,
 * wobbling and fading over 0.67 s; the PSG adds the scrape's noise. */
static const u8 s_Screech[] = {
    W(0x22, 0), W(0x32, 0x62), NOTE(2, 280, 6), WAIT(3),
    NOTE(2, 287, 6), WAIT(3), NOTE(2, 274, 6), W(0x32, 0x63), WAIT(3),
    NOTE(2, 286, 6), WAIT(3), NOTE(2, 276, 6), W(0x32, 0x65), WAIT(4),
    NOTE(2, 284, 6), W(0x32, 0x67), WAIT(5), NOTE(2, 278, 6), W(0x32, 0x69), WAIT(6),
    W(0x32, 0x6C), WAIT(6), W(0x22, FOFF(278, 6)), END};
/* The lift at its stop: two vibraphone notes 1.07 and 1.58 kHz apart from
 * any harmonic ratio, struck with the cymbal; they ring for 0.7 s. */
static const u8 s_Clang[] = {
    W(0x22, 0), W(0x23, 0), W(0x32, 0xC1), W(0x33, 0xC4), WAIT(1),
    W(0x12, FL(353)), W(0x13, FL(260)), W(0x22, FH(353, 5)), W(0x23, FH(260, 6)), WAIT(1),
    W(0x38, 0xF2), W(0x0E, 0x20), W(0x0E, 0x22), WAIT(40),
    W(0x22, FOFF(353, 5)), W(0x23, FOFF(260, 6)), END};
/* Into the sea: the cymbal's crash and the hi-hat's spray, twice, over the
 * PSG's hiss. */
static const u8 s_Splash[] = {
    W(0x38, 0xF0), W(0x37, 0x1F), W(0x0E, 0x20), W(0x0E, 0x23), WAIT(12),
    W(0x37, 0x4F), W(0x0E, 0x20), W(0x0E, 0x21), WAIT(12), W(0x0E, 0x20), END};
/* A burst: bass drum (tuned down at init), tom and cymbal, then a second
 * thump, over the PSG's low rumble. */
static const u8 s_Boom[] = {
    W(0x36, 0x00), W(0x38, 0x01), W(0x0E, 0x20), W(0x0E, 0x36), WAIT(6),
    W(0x36, 0x03), W(0x0E, 0x20), W(0x0E, 0x30), WAIT(10), W(0x0E, 0x20), END};

static const u8* const s_Sources[SOUND_COUNT] = {0, s_Scream, s_Screech, s_Clang, s_Splash, s_Boom};
static const u16 s_Sizes[SOUND_COUNT] = {0, sizeof(s_Scream), sizeof(s_Screech), sizeof(s_Clang), sizeof(s_Splash), sizeof(s_Boom)};
typedef char FMScriptsFit[sizeof(s_Scream) + sizeof(s_Screech) + sizeof(s_Clang) + sizeof(s_Splash) + sizeof(s_Boom) <= FM_SCRIPT_BYTES ? 1 : -1];

/* The engine: a sustained buzz. The modulator is half-wave rectified with
 * full feedback (a rasp rich in harmonics); the carrier's amplitude
 * modulation adds the 3.7 Hz throb. Registers 0..7 of the custom
 * instrument. */
static const u8 s_EnginePatch[8] = {0x21, 0xA1, 0x0C, 0x0F, 0xF0, 0xF0, 0x0F, 0x0F};

/* The driver (in RAM): the engine's changed registers, a gun hit when due,
 * then the current script's writes up to its next wait, within the field's
 * write budget. */
void FM_Driver(void) __naked
{
    __asm
        ld a, #4
        ld (_s_FMBudget), a
        ld a, (_s_FMEngineDirty)
        or a
        jr z, fmd_guns$
        xor a
        ld (_s_FMEngineDirty), a
        ld hl, #_g_FMEngine
        ld b, #6
    fmd_engine$:
        ld c, (hl)
        inc hl
        ld e, (hl)
        inc hl
        ld a, (hl)
        cp e
        jr z, fmd_same$
        ld a, (_s_FMBudget)
        cp #2
        jr nz, fmd_engine_write$
        ld (_s_FMEngineDirty), a    ; 2 written: the rest next field
        jr fmd_guns$
    fmd_engine_write$:
        dec a
        ld (_s_FMBudget), a
        ld (hl), e
        ld a, c
        call _Sound_OPLLWrite
    fmd_same$:
        inc hl
        djnz fmd_engine$
    fmd_guns$:
        ; guns: snare and hi-hat, one hit every g_SoundGunRate fields
        ld a, (_g_SoundGun)
        or a
        jr z, fmd_request$
        ld c, a                 ; c: the PSG volume, 1..15
        ld hl, #_s_FMGunPhase
        inc (hl)
        ld a, (_g_SoundGunRate)
        cp (hl)
        jr z, fmd_hit$
        jr nc, fmd_request$
    fmd_hit$:
        ld a, (_s_FMBudget)
        cp #3
        jr c, fmd_request$      ; no room: the hit waits a field
        sub #3
        ld (_s_FMBudget), a
        ld (hl), #0
        ld a, #15
        sub c
        ld e, a                 ; snare attenuation
        add a, #2               ; the hi-hat 2 steps quieter
        cp #16
        jr c, fmd_hh$
        ld a, #15
    fmd_hh$:
        rlca
        rlca
        rlca
        rlca
        or e
        ld e, a
        ld a, #0x37
        call _Sound_OPLLWrite
        ld a, (_s_FMKeys)
        and #0x36               ; snare and hi-hat off, the rest kept
        ld e, a
        ex (sp), hl             ; (38 T-states: the chip's 84 between writes)
        ex (sp), hl
        ld a, #0x0e
        call _Sound_OPLLWrite
        ld a, e
        or #0x09
        ld e, a
        ld (_s_FMKeys), a
        ex (sp), hl
        ex (sp), hl
        ld a, #0x0e
        call _Sound_OPLLWrite
    fmd_request$:
        ; a new effect (Sound_Effect) replaces the script
        ld a, (_g_SoundRequest)
        or a
        jr z, fmd_script$
        add a, a
        ld l, a
        ld h, #0
        ld bc, #_g_FMScripts
        add hl, bc
        ld a, (hl)
        inc hl
        ld h, (hl)
        ld l, a
        ld (_s_FMScript), hl
        ld a, (_g_SoundRequestAtten)
        ld (_s_FMAtten), a
        xor a
        ld (_s_FMWait), a
    fmd_script$:
        ld hl, (_s_FMScript)
        ld a, h
        or l
        ret z
        ld a, (_s_FMWait)
        or a
        jr z, fmd_step$
        dec a
        ld (_s_FMWait), a
        ret
    fmd_step$:
        ld a, (_s_FMBudget)
        or a
        jr z, fmd_pause$        ; the rest of this step next field
        ld a, (hl)
        inc hl
        ld e, (hl)
        inc hl
        cp #0xfe
        jr z, fmd_end$
        jr nc, fmd_wait$
        ld c, a                 ; c: the register, e: its value
        and #0xf0
        cp #0x30
        jr nz, fmd_write$
        ld a, (_s_FMAtten)      ; a volume: quieter with the distance
        ld b, a
        ld a, e
        and #15
        add a, b
        cp #16
        jr c, fmd_low$
        ld a, #15
    fmd_low$:
        ld d, a
        ld a, e
        and #0xf0
        ld e, a
        ld a, c
        cp #0x37                ; 0x37, 0x38 hold two drum volumes
        jr c, fmd_merge$
        ld a, e
        rrca
        rrca
        rrca
        rrca
        add a, b
        cp #16
        jr c, fmd_high$
        ld a, #15
    fmd_high$:
        rlca
        rlca
        rlca
        rlca
        ld e, a
    fmd_merge$:
        ld a, e
        or d
        ld e, a
    fmd_write$:
        ld a, c
        cp #0x0e
        jr nz, fmd_out$
        ld a, e
        ld (_s_FMKeys), a
        ld a, c
    fmd_out$:
        call _Sound_OPLLWrite
        ld a, (_s_FMBudget)
        dec a
        ld (_s_FMBudget), a
        jr fmd_step$
    fmd_pause$:
        ld (_s_FMScript), hl
        ret
    fmd_wait$:
        ld (_s_FMScript), hl
        ld a, e
        dec a
        ld (_s_FMWait), a
        ret
    fmd_end$:
        ld hl, #0
        ld (_s_FMScript), hl
        ret
    _FM_DriverEnd::
    __endasm;
}
extern void FM_DriverEnd(void);

/* A register write from C, with the chip's waits (boot only). */
static void Write(u8 reg, u8 value)
{
    s_OPLLIndex = reg;
    s_OPLLData = value;
    __asm
        push bc
        ld b, #8
    fmw_wait$:
        djnz fmw_wait$
        pop bc
    __endasm;
}

static void Copy(u8* to, const u8* from, u16 count)
{
    while (count--) *to++ = *from++;
}

/* The BIOS's RDSLT (000Ch): a byte of another slot's memory. It returns
 * with interrupts off. Called from window 3: it switches page 1 only. */
static u8 ReadSlot(u8 slot, u16 address) __naked
{
    (void)slot; (void)address;
    __asm
        ex de, hl               ; sdcccall(1): A slot, DE address
        call 0x000c
        ei
        ret
    __endasm;
}

/* An FM-PAC's ports open with bit 0 of 7FF6h (RDSLT, then WRSLT 0014h). */
static void EnableFMPAC(u8 slot) __naked
{
    (void)slot;
    __asm
        push af
        ld hl, #0x7ff6
        call 0x000c
        or #1
        ld e, a
        pop af
        ld hl, #0x7ff6
        call 0x0014
        ei
        ret
    __endasm;
}

static u8 Match(u8 slot, u16 address, const c8* text, u8 count)
{
    do { if (ReadSlot(slot, address++) != (u8)*text++) return 0; } while (--count);
    return 1;
}

/* Every slot and subslot: "APRLOPLL" at 4018h is a built-in MSX-MUSIC,
 * "OPLL" at 401Ch alone an FM-PAC, whose ports open with bit 0 of 7FF6h. */
static u8 Detect(void)
{
    u8 primary, secondary, expanded, slot;
    for (primary = 0; primary < 4; ++primary)
    {
        expanded = *(volatile u8*)(0xFCC1 + primary) & 0x80;
        for (secondary = 0; secondary < (expanded ? 4 : 1); ++secondary)
        {
            slot = primary | (expanded ? 0x80 | secondary << 2 : 0);
            if (Match(slot, 0x4018, "APRLOPLL", 8)) return 1;
            if (Match(slot, 0x401C, "OPLL", 4))
            {
                EnableFMPAC(slot);
                return 1;
            }
        }
    }
    return 0;
}

void Sound_InitFM(void) WINGS_BANKED
{
    u8 i, *data = s_ScriptData;
    u16 size = (u16)FM_DriverEnd - (u16)FM_Driver;
    g_SoundFM = 0;
    if (size > FM_DRIVER_BYTES || !Detect()) return;
    /* Silence, the engine's instrument, the drums' pitches (the bass drum
     * an octave below the BIOS's, for bursts), rhythm mode. */
    for (i = 0; i < 9; ++i) { Write(0x20 + i, 0); Write(0x10 + i, 0); Write(0x30 + i, 0x0F); }
    Write(0x37, 0xFF); Write(0x38, 0xFF);
    for (i = 0; i < 8; ++i) Write(i, s_EnginePatch[i]);
    Write(0x16, 0x60); Write(0x26, 0x03);
    Write(0x17, 0x50); Write(0x27, 0x05);
    Write(0x18, 0xC0); Write(0x28, 0x01);
    Write(0x0E, 0x20);
    for (i = 0; i < 6; ++i)
    {
        g_FMEngine[i * 3] = (i & 1 ? 0x20 : 0x10) + (i >> 1);   /* 0x10 0x20 0x11 0x21 */
        g_FMEngine[i * 3 + 1] = 0;
        g_FMEngine[i * 3 + 2] = 0xFF;
    }
    g_FMEngine[12] = 0x30; g_FMEngine[15] = 0x31;
    g_FMEngine[13] = g_FMEngine[16] = 0x0F;   /* the custom instrument, silent */
    g_FMScripts[0] = 0;
    for (i = 1; i < SOUND_COUNT; ++i)
    {
        g_FMScripts[i] = data;
        Copy(data, s_Sources[i], s_Sizes[i]);
        data += s_Sizes[i];
    }
    Copy(g_FMDriver, (const u8*)FM_Driver, size);
    s_FMScript = 0; s_FMWait = s_FMGunPhase = 0; s_FMKeys = 0x20;
    s_FMEngineDirty = 1; s_FMPeriod = 0;
    g_SoundFM = 1;   /* last: the interrupt starts calling the driver */
}

void Sound_FMEngine(u16 period, u8 volume) WINGS_BANKED
{
    u16 fnum, half, detuned;
    u8 att;
    if (!g_SoundFM) return;
    if (period != s_FMPeriod)
    {
        /* The PSG version's pitch, 49,956 / P Hz, in block 2: fnum =
         * 131,700 / P, from a table (tools/convert_fm_pitch.py). */
        s_FMPeriod = period;
        half = period >> 1;
        if (half < FM_PITCH_FIRST) half = FM_PITCH_FIRST;
        if (half > FM_PITCH_FIRST + FM_PITCH_COUNT - 1) half = FM_PITCH_FIRST + FM_PITCH_COUNT - 1;
        fnum = s_FMPitch[half - FM_PITCH_FIRST];
        detuned = fnum + (fnum >> 5);
        if (detuned > 511) detuned = 511;
        g_FMEngine[1] = (u8)fnum; g_FMEngine[4] = (g_FMEngine[4] & 0x10) | 0x04 | (u8)(fnum >> 8);
        g_FMEngine[7] = (u8)detuned; g_FMEngine[10] = (g_FMEngine[10] & 0x10) | 0x04 | (u8)(detuned >> 8);
        s_FMEngineDirty = 1;
    }
    /* Volume of 64, 3 dB a step: full throttle (64) at attenuation 3,
     * flying (49) 6, on deck (40) 9, a failed engine (25) 12. */
    att = volume ? 3 + (u8)((u8)(64 - volume) >> 2) : 15;
    if (att > 15) att = 15;
    if (att != g_FMEngine[13])
    {
        g_FMEngine[13] = att;
        g_FMEngine[16] = att > 13 ? 15 : att + 2;
        /* Keyed off when silent: attenuation 15 is -45 dB, not silence. */
        if (att == 15) { g_FMEngine[4] &= ~0x10; g_FMEngine[10] &= ~0x10; }
        else { g_FMEngine[4] |= 0x10; g_FMEngine[10] |= 0x10; }
        s_FMEngineDirty = 1;
    }
}
#endif
