#include "engine.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_SCENE)

void Engine_Reset(EngineState* engine, SortieState* sortie) WINGS_BANKED
{
    sortie->fuel = ENGINE_FUEL_FULL;
    sortie->oil = ENGINE_OIL_FULL;
    engine->fuel_ticks = ENGINE_FUEL_TICKS;
    engine->leak_ticks = 1; /* the original's leak timer starts expired */
    engine->dry = engine->failed = 0;
    engine->oil_blink = engine->fuel_blink = 0;
    engine->oil_needle = Engine_OilFrame(sortie, 0);
    engine->fuel_needle = Engine_FuelFrame(sortie);
    engine->lamps = 0;
    if (!engine->random) engine->random = 0x5a;
}

void Engine_Damage(EngineState* engine, SortieState* sortie, uint8_t oil, uint8_t fuel) WINGS_BANKED
{
    sortie->oil = oil < sortie->oil ? sortie->oil - oil : 0;
    if (fuel > sortie->fuel) engine->dry = 1;
    sortie->fuel = fuel < sortie->fuel ? sortie->fuel - fuel : 0;
}

uint8_t Engine_OilFrame(const SortieState* sortie, uint8_t throttle) WINGS_BANKED
{
    uint8_t frame = sortie->oil > ENGINE_OIL_SEIZE ? (uint8_t)((sortie->oil - ENGINE_OIL_SEIZE) >> 1) : 0;
    if (throttle) frame += ENGINE_THROTTLE_FRAMES;
    return frame > ENGINE_NEEDLE_FULL ? ENGINE_NEEDLE_FULL : frame;
}

uint8_t Engine_FuelFrame(const SortieState* sortie) WINGS_BANKED
{
    uint8_t frame = sortie->fuel >> 3;
    return frame > ENGINE_NEEDLE_FULL ? ENGINE_NEEDLE_FULL : frame;
}

/* The original's blink: count down; lit while positive, then dark for two
 * ticks (0, then -1 reloads the counter). */
static uint8_t Blink(int8_t* counter, uint8_t reload)
{
    if (--*counter > 0) return 1;
    if (*counter) *counter = (int8_t)reload;
    return 0;
}

static uint8_t Approach(uint8_t shown, uint8_t target)
{
    return shown < target ? shown + 1 : shown > target ? shown - 1 : shown;
}

uint8_t Engine_Tick(EngineState* engine, SortieState* sortie, uint8_t flying, uint8_t throttle, uint8_t warnings) WINGS_BANKED
{
    uint8_t target, failed = 0;
    if (flying && !engine->failed)
    {
        if (sortie->oil != ENGINE_OIL_FULL && !--engine->leak_ticks)
        {
            engine->leak_ticks = ENGINE_LEAK_TICKS;
            if (sortie->oil) --sortie->oil;
        }
        if (!--engine->fuel_ticks)
        {
            engine->fuel_ticks = ENGINE_FUEL_TICKS;
            if (sortie->fuel) --sortie->fuel; else engine->dry = 1;
        }
        if (sortie->oil < ENGINE_OIL_SEIZE || engine->dry) engine->failed = failed = 1;
    }
    if (engine->failed) throttle = 0;
    /* Instruments: needles sweep one frame per tick toward their targets. */
    engine->random = (uint8_t)((engine->random << 1) | (((engine->random >> 7) ^ (engine->random >> 5) ^
                     (engine->random >> 4) ^ (engine->random >> 3)) & 1));
    engine->oil_needle = Approach(engine->oil_needle, Engine_OilFrame(sortie, throttle));
    target = Engine_FuelFrame(sortie);
    if (!target && warnings) target = engine->random & 1; /* an empty tank's needle twitches */
    engine->fuel_needle = Approach(engine->fuel_needle, target);
    engine->lamps = 0;
    if (warnings)
    {
        if (sortie->oil < ENGINE_OIL_WARN && Blink(&engine->oil_blink, ENGINE_OIL_BLINK))
            engine->lamps |= ENGINE_LAMP_OIL;
        if (sortie->fuel <= ENGINE_FUEL_WARN && Blink(&engine->fuel_blink, ENGINE_FUEL_BLINK))
            engine->lamps |= ENGINE_LAMP_FUEL;
    }
    return failed;
}
