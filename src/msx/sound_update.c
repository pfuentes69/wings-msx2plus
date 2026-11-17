#include "sound_update.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_SOUND)
#include "sound.h"
#include "sound_fm.h"
#include "../core/carrier.h"
#include "../core/island.h"
#include "../core/ships.h"

/* What the PSG driver plays, from the game state, once per presented
 * frame (the original's sound update, 0x2132; docs/sound-effects.md). */
#ifdef WINGS_P1_FLIGHT
#define T 1
#define N(period) (2 | (period) << 2)
#define END {0, 0, 0, 0, 0, 0}
/* PSG tone periods: 111,861 / Hz. Durations at 60 fields a second, from
 * the samples at the original's periods (sounds/, docs/sound-effects.md). */
static const SoundStep s_Steps[] = {
    /* SOUND_SCREAM: 0.7 s, wavering 450..900 Hz */
    {6, 0x90, 4, T, 160, -6}, {6, 0xb0, 0, T, 124, 10}, {6, 0xb0, 0, T, 184, -8},
    {6, 0xb0, 0, T, 136, 12}, {8, 0xb0, -4, T, 208, -6}, {10, 0x90, -14, T, 160, 12}, END,
    /* SOUND_SCREECH: 0.67 s at ~1.7 kHz, fading */
    {5, 0xc0, -2, T | N(1), 66, 1}, {5, 0xb6, -2, T | N(1), 71, -1}, {10, 0xac, -3, T | N(1), 66, 1},
    {20, 0x8e, -7, T | N(1), 76, -1}, END,
    /* SOUND_CLANG: a struck metal ring, 0.72 s */
    {2, 0xf0, 0, T | N(1), 100, 0}, {41, 0xd0, -5, T, 104, 0}, END,
    /* SOUND_SPLASH: 0.67 s of hiss, quieter than a boom */
    {10, 0xa0, 0, N(6), 0, 0}, {12, 0xa0, 0, N(10), 0, 0}, {18, 0xa0, -9, N(14), 0, 0}, END,
    /* SOUND_BOOM: a thump, then 0.75 s of low rumble */
    {3, 0xf0, 0, T | N(31), 1800, 40}, {43, 0xf0, -6, N(31), 0, 0}, END};
typedef char SoundStepsFit[sizeof(s_Steps) <= sizeof(g_SoundSteps) ? 1 : -1];
/* With MSX-MUSIC (sound_fm.c) the FM plays the voices; the PSG keeps the
 * noise. Silent steps hold the effect's priority for its FM length. */
static const SoundStep s_StepsFM[] = {
    /* SOUND_SCREAM: the FM violin alone */
    {47, 0, 0, 0, 0, 0}, END,
    /* SOUND_SCREECH: the scrape under the FM squeal */
    {20, 0x90, -3, N(1), 0, 0}, {20, 0x60, -3, N(1), 0, 0}, END,
    /* SOUND_CLANG: the strike; the FM rings */
    {2, 0xd0, 0, T | N(1), 100, 0}, {41, 0, 0, 0, 0, 0}, END,
    /* SOUND_SPLASH and SOUND_BOOM: the hiss and the rumble under the drums */
    {10, 0xa0, 0, N(6), 0, 0}, {12, 0xa0, 0, N(10), 0, 0}, {18, 0xa0, -9, N(14), 0, 0}, END,
    {3, 0xf0, 0, T | N(31), 1800, 40}, {43, 0xf0, -6, N(31), 0, 0}, END};
typedef char SoundStepsFMFit[sizeof(s_StepsFM) <= sizeof(g_SoundSteps) ? 1 : -1];

static u16 s_Period;          /* the engine's Paula period (-$5bd0) */
static u8 s_Volume;           /* its volume of 64 (-$5bd2) */
static u8 s_Ticks, s_Stage, s_Mode;   /* s_Ticks: flight steps toward the next tick */

/* Into RAM, where the interrupt reads them (it cannot map this bank). */
void Sound_LoadEffects(void) WINGS_BANKED
{
    u8 i, id = SOUND_SCREAM, count;
    const SoundStep* steps;
    Sound_InitFM();
    steps = g_SoundFM ? s_StepsFM : s_Steps;
    count = g_SoundFM ? sizeof(s_StepsFM) / sizeof(SoundStep) : sizeof(s_Steps) / sizeof(SoundStep);
    g_SoundEffects[0] = 0;
    g_SoundEffects[id] = g_SoundSteps;
    for (i = 0; i < count; ++i)
    {
        g_SoundSteps[i] = steps[i];
        if (!steps[i].fields && ++id < SOUND_COUNT) g_SoundEffects[id] = g_SoundSteps + i + 1;
    }
    /* The engine starts idling, quiet (RAM is not cleared at boot). */
    s_Period = 808; s_Volume = s_Ticks = 0;
    s_Stage = CARRIER_DECK; s_Mode = FLIGHT_GROUND;
}


void Sound_Update(const FlightState* f, u16 world, u8 flags, u8 steps) WINGS_BANKED
{
    u8 i, target = 0, v;
    u16 base = 808, period;
    i16 dx;
    const IslandGun* g;
    g_SoundListener = world;
    if (!(flags & SOUND_PLAYING))
    {
        g_SoundEngineVolume = g_SoundGun = g_SoundGrind = 0;
        s_Volume = 0;
        Sound_FMEngine(s_Period, 0);
        return;
    }
    /* The engine (0xc0e2, 0xc144, 0xc528, 0xc566, 0xc74e): target volume
     * and base period by mode. */
    if (!(flags & SOUND_CRASHED))
    {
        if (f->mode == FLIGHT_DEAD) { target = 25; base = 960; }
        else if (f->throttle) { target = 64; base = 335; }
        else if (FLIGHT_ON_DECK(f)) { target = 40; base = 808; }
        else { target = 49; base = 385; }
    }
    /* 0x217c: the period follows base + climb / 128 + altitude / 16, at
     * most 10 down or 20 up a tick (12 flight steps); the volume 1 up or 2
     * down a tick. */
    period = base + (f->climb >> 7) + ((WINGS_FLIGHT_MAX_Y - (u16)(f->y >> 8)) >> 4);
    for (s_Ticks += steps; s_Ticks >= 12; s_Ticks -= 12)
    {
        if (s_Period > period) s_Period = s_Period - period > 10 ? s_Period - 10 : period;
        else if (s_Period < period) s_Period = period - s_Period > 20 ? s_Period + 20 : period;
        if (s_Volume < target) ++s_Volume;
        else if (s_Volume > target) s_Volume = s_Volume - target > 2 ? s_Volume - 2 : target;
    }
    /* The engine sample's waveform repeats every 71 samples: 49,956 / P Hz,
     * a PSG tone period of 2.24 P. */
    g_SoundEngineTone = (s_Period << 1) + (s_Period >> 2);
    g_SoundEngineVolume = g_SoundFM ? 0 : (u8)((s_Volume * 11u) >> 6);
    Sound_FMEngine(s_Period, s_Volume);
    /* Guns: the cannon (0x21c0, while firing), else the dugout guns in
     * range (their own channel in the original), louder nearer. */
    g_SoundGun = 0;
    if (g_Combat.flash) { g_SoundGun = 12; g_SoundGunRate = 6; }
    else
        for (i = 0, g = g_Island.gun; i < ISLAND_MAX_DUGOUTS; ++i, ++g)
        {
            if (g->frame == ISLAND_GUN_NONE) continue;
            dx = (i16)(world - g->x);
            if (dx < 0) dx = -dx;
            v = dx >= 512 ? 1 : 9 - (u8)(dx >> 6);
            if (v > g_SoundGun) { g_SoundGun = v; g_SoundGunRate = 10; }
        }
    /* Ship guns: "under fire" (0x38ea), louder by the nearest gun firing. */
    if (!g_Combat.flash && g_Ships.nearest < 512)
    {
        v = 9 - (u8)(g_Ships.nearest >> 6);
        if (v > g_SoundGun) { g_SoundGun = v; g_SoundGunRate = 10; }
    }
    /* The lift: its motor grinds while it moves (0x222a), and it clangs
     * at either stop (0x149e, 0x14ce). */
    g_SoundGrind = g_Carrier.stage == CARRIER_RAISING || g_Carrier.stage == CARRIER_LOWERING;
    if ((s_Stage == CARRIER_RAISING && g_Carrier.stage == CARRIER_DECK) ||
        (s_Stage == CARRIER_LOWERING && g_Carrier.stage == CARRIER_HOLD))
        Sound_Effect(SOUND_CLANG, world);
    s_Stage = g_Carrier.stage;
    /* The hook catching a cable (0xbb40). */
    if (f->mode == FLIGHT_ARREST && s_Mode != FLIGHT_ARREST) Sound_Effect(SOUND_SCREECH, world);
    s_Mode = f->mode;
}
#endif

#ifdef WINGS_P1_FLIGHT
/* Bombs that burst this weapon tick (0x0c90, 0x0c9a): a splash over the
 * sea, a boom on land or deck. Cannon strikes have no sound of their own:
 * the guns' rattle covers them. */
void Sound_Bursts(void) WINGS_BANKED
{
    const CombatProjectile* p = g_Combat.projectile + COMBAT_GUN_COUNT;
    u8 i;
    for (i = COMBAT_GUN_COUNT; i < g_Combat.count; ++i, ++p)
        if (p->kind >= COMBAT_IMPACT && p->life == 6)
            Sound_Effect(p->kind == COMBAT_SPLASH ? SOUND_SPLASH : SOUND_BOOM, (u16)Combat_WorldX(&g_Combat, p->x));
}
#endif
