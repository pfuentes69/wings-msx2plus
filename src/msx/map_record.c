/* The loaded map (docs/map-records.md): its record, copied into RAM from
 * its ROM bank by Map_Load; the surface and height runs stay in that bank
 * and are read here, window 3 mapped for the moment. Resident: banked code
 * calls in, and window 3 comes back to the caller's segment before return
 * (the shadow first, as in mission_streamer.c's Decode). */
#include "map_record.h"
#include "mission_surfaces.h"
#include "../core/mission.h"

MapRecord g_Map;
uint8_t g_MapNumber;
/* Mission_Query's last run found: the plane (or camera) stays in one most
 * frames. */
static uint16_t s_Start, s_End, s_Word;
/* The same for Mission_Height (the landing check asks every step) and
 * Mission_Surface (its run index: a sunk ship's bit is tested each time). */
static uint16_t s_HeightStart, s_HeightEnd;
static uint8_t s_Height;
static uint16_t s_ClassStart, s_ClassEnd;
static uint8_t s_Class;
static uint8_t s_Bank;   /* the loaded record's */
extern uint8_t g_Bank3Segment;   /* crt0's shadow of the window-3 register */

/* Window 3 = segment, sdcccall(1): A. LD (nn),A, the form loaders patch
 * (docs/diag-rom.md). */
static void SetBank3(uint8_t segment) __naked
{
    (void)segment;
    __asm
        ld      (0x7800), a
        ret
    __endasm;
}

static uint8_t Enter(void)
{
    uint8_t segment = g_Bank3Segment;
    g_Bank3Segment = s_Bank;
    SetBank3(s_Bank);
    return segment;
}

static void Leave(uint8_t segment)
{
    g_Bank3Segment = segment;
    SetBank3(segment);
}

/* The record's RAM part (window 3 at A000h) into g_Map. */
static void CopyRecord(void) __naked
{
    __asm
        ld      hl, #0xA000
        ld      de, #_g_Map
        ld      bc, #MAP_RECORD_BYTES
        ldir
        ret
    __endasm;
}

void Map_Load(uint8_t n)
{
    uint8_t segment;
    g_MapNumber = n;
    s_Bank = g_MapRecordBank[n];
    segment = Enter();
    CopyRecord();
    Leave(segment);
    s_Start = s_End = s_Word = 0;   /* RAM is not cleared at boot */
    s_HeightStart = s_HeightEnd = s_ClassStart = s_ClassEnd = 0;
}

uint16_t Map_Word(uint16_t at)
{
    uint8_t segment = Enter();
    uint16_t word = *(const uint16_t*)at;
    Leave(segment);
    return word;
}

uint8_t Map_Byte(uint16_t at)
{
    uint8_t segment = Enter();
    uint8_t byte = *(const uint8_t*)at;
    Leave(segment);
    return byte;
}

/* Class-only lookup over the original surface intervals; a ship gone under
 * (its g_ShipsGone bit) leaves sea. */
uint8_t Mission_Surface(uint16_t x)
{
    uint8_t i;
    if (x < s_ClassStart || x >= s_ClassEnd)
    {
        for (i = 0; i < g_Map.class_count && x >= g_Map.class_end[i]; ++i) {}
        if (i == g_Map.class_count) return MISSION_SEA;   /* past the map */
        s_ClassStart = i ? g_Map.class_end[i - 1] : 0;
        s_ClassEnd = g_Map.class_end[i];
        s_Class = i;
    }
    return g_Map.class_ship[s_Class] & g_ShipsGone ? MISSION_SEA : g_Map.class_surface[s_Class];
}

/* Exact source strip query (core/mission.h), over the runs in ROM. */
uint16_t Mission_Query(int16_t x)
{
    const MissionSurfaceRun* runs = (const MissionSurfaceRun*)g_Map.runs_at;
    uint8_t low = 0, high = g_Map.surface_runs, middle, segment;
    if (x < 0 || (uint16_t)x >= g_Map.width) return 0;
    if ((uint16_t)x >= s_Start && (uint16_t)x < s_End) return s_Word;
    segment = Enter();
    while (low < high)
    {
        middle = low + ((high - low) >> 1);
        if ((uint16_t)x < runs[middle].end) high = middle;
        else low = middle + 1;
    }
    s_Start = low ? runs[low - 1].end : 0;
    s_End = runs[low].end;
    s_Word = runs[low].word;
    Leave(segment);
    return s_Word;
}

/* Static scenery height above the sea (Amiga 0x5710, core/landing.c): the
 * ends (u16) then the heights (u8), in ROM. */
uint8_t Mission_Height(uint16_t world)
{
    const uint16_t* ends = (const uint16_t*)g_Map.heights_at;
    uint8_t low = 0, high = g_Map.height_runs, middle, segment, height = 0;
    if (world >= s_HeightStart && world < s_HeightEnd) return s_Height;
    segment = Enter();
    while (low < high)
    {
        middle = low + ((high - low) >> 1);
        if (world < ends[middle]) high = middle;
        else low = middle + 1;
    }
    if (low < g_Map.height_runs)
    {
        height = ((const uint8_t*)(ends + g_Map.height_runs))[low];
        s_HeightStart = low ? ends[low - 1] : 0;
        s_HeightEnd = ends[low];
        s_Height = height;
    }
    Leave(segment);
    return height;
}
