#include "bios.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "keyboard.h"
#include "core/world.h"
#include "core/aircraft.h"
#ifdef WINGS_P1_FLIGHT
#include "core/carrier.h"
#include "msx/rope.h"
#include "msx/smoke_draw.h"
#include "core/smoke.h"
#include "core/island.h"
#include "core/ships.h"
#include "core/planes.h"
#include "core/rockets.h"
#include "core/flight_model.h"
#include "core/crash.h"
#include "msx/elevator.h"
CarrierState g_Carrier;
volatile u8 g_DisplayElevator;
#endif
#include "msx/terrain_patch.h"
#include "generated/hellcat_frames.h"
#ifndef WINGS_PRESENT_TICKS
#define WINGS_PRESENT_TICKS 2
#endif
#include "msx/terrain_renderer.h"
#include "mission_tiles.h"
#include "core/mission.h"
#include "msx/dashboard.h"
#include "msx/cockpit.h"
#include "msx/ship.h"
#include "msx/weapons.h"
#include "core/combat.h"
#include "core/engine.h"
#include "msx/step_batch.h"
#include "core/landing.h"
#include "core/game.h"
#include "msx/input_sampler.h"
#include "msx/menu.h"
#include "msx/screens.h"
GameState g_Game;
u8 g_GameView[8], g_TopPalette[32], g_BottomPalette[32];
static u8 s_NextGameView[8];
static u16 s_LastControl;
static u8 s_UiDirty;
CombatState g_Combat;
#ifdef WINGS_P1_FLIGHT
EngineState g_Engine;
u8 g_LastContact;                /* latest LANDING_* contact, for verification */
u8 s_ContactBottom, s_ContactSurface; /* per-frame contact gate (Landing_Prepare; msx/step_batch.c) */
#endif
/* The wreck's frame drawn instead of the plane (255 = none); the frame shown
 * on the published page, and the frame loaded into the host atlas slot. */
static u8 s_CrashFrame = 255, s_RenderCrash = 255, s_CrashLoaded = 255;
volatile u8 g_DisplayCrash = 255;
#ifdef WINGS_P1_FLIGHT
/* Landing gear: the overlay sprite drawn (255 none) and its slide 0..5
 * (5 = down), as the original animates it toward the gear state (0x0550). */
static u8 s_Wheel = 255, s_GearPos = 5, s_RenderWheel = 255, s_RenderGear = 5;
/* The arresting rope (src/msx/rope.c): the cable drawn, 255 none. */
volatile u8 g_DisplayRope = 255;
volatile u32 g_DisplayScore;
/* Smoke_Restore repainted the elevator's columns this frame. A static: a
 * local held across Render's column loops makes SDCC spill throughout. */
static u8 s_Smoked;
static u8 s_GunsDrawn;           /* dugout guns shown this original tick */
static u8 s_ShipGuns;            /* ship barrels and splashes shown this frame */
static u8 s_SoldiersMoving;      /* island soldiers walking or dying */
static u16 s_Impacts;            /* g_Combat.impacts already seen */
static u8 s_RenderRope = 255;
volatile u8 g_DisplayWheel = 255, g_DisplayGear = 5;
#endif
#ifdef WINGS_P1_FLIGHT
u8 s_EngineSteps;         /* simulation steps into the current original tick (msx/step_batch.c reads it) */
#endif
/* Oil needle, fuel needle and lamps drawn on the rendered/published page.
 * A new plane reads oil frame 16 and fuel frame 22 (amiga-fuel-oil.md). */
static u8 s_RenderGauges[3] = {16, 22, 0};
volatile u8 g_DisplayGauges[3] = {16, 22, 0};
#include "rom_mapper.h"
#include "msx/scenery_load.h"
#include "msx/message.h"
#include "msx/sound.h"
#include "msx/sound_update.h"
#include "msx/vdp_ring.h"

volatile u8 g_ScrollFine, g_ScrollCoarse, g_VerticalOffset, g_LineSplit;
/* Close-view pan (docs/altitude-view.md): above altitude 131 the original
 * scrolls the scene down with the plane. Whole tile rows are drawn lower in
 * software (g_PanRows); the last 0..7 px are a hardware scroll from line s =
 * heave + fine down, the top lines keeping the heave-only offset (sky).
 * g_FirstSplit/g_FirstState: the first line interrupt and the HBlank state
 * the VBlank ISR arms (2: top split pending). */
volatile u8 g_PlayOffset, g_FirstSplit, g_FirstState;
/* The play area's horizontal scroll, set again at the top split (the
 * message band above it has its own; msx/message.h). */
volatile u8 g_PlayFine, g_PlayCoarse;
volatile u8 g_DisplayFine;   /* the published page's fine pan (verification) */
static u8 s_ViewKey, s_RenderFine;   /* view: 8 distant, else pan rows / 8 */
static int8_t s_PanStep;              /* tile rows the page moves this render */
static u8 s_Repainted;                /* scenery under the elevator was repainted */
static u8 s_GuardTop[2];              /* first VRAM row of each page's guard line */
static u8 s_RenderHeave;
/* Far view x: an arithmetic shift, so the sea left of the map (negative x)
 * stays continuous with the map. */
#define FAR_X(world) ((u16)((int16_t)(world) >> 3))
#ifdef WINGS_P1_FLIGHT
static u8 s_CarrierView; /* the near view shows the carrier */
static u8 s_Tight;       /* the last frame took within a VBlank of the base deadline */
#endif
volatile u8 g_DashboardSplit;
volatile u16 g_DisplaySurfaceWord;
volatile u8 g_DisplayScale, g_DisplayWave, g_DisplayPilot, g_ViewChange;
volatile u8 g_DisplayHeave, g_DisplayShipFrame;
static u8 s_PageScale[2], s_Wave = 11, s_RenderPilot;
u8 s_AnimTick;   /* steps into the original tick (msx/step_batch.c reads it) */
static u16 s_RenderSurface;
#include "input.h"

volatile u8 g_VBlankTicks, g_Ready, g_Rendering, g_FramePublished;
volatile u8 g_DisplayPage, g_SelectedFrame, g_DisplayX, g_Turning;
volatile u16 g_DisplayY;
volatile u8 g_HoldFlight, g_RenderPage;
volatile u16 g_DisplayCamera, g_DisplayWorld, g_MissedFrames;
/* Close-view pan steps that ran past the frame deadline: counted apart
 * from g_MissedFrames, like view changes (docs/altitude-view.md). */
volatile u16 g_PanOverruns;
/* Not static: the openMSX scenarios read the flight state (tools/p0_smoke.tcl). */
WorldState s_World;
static AircraftState s_Aircraft;
static u16 s_Camera[2], s_OldX[2];
static u8 s_OldY[2], s_OldWidth[2], s_OldHeight[2], s_Valid[2];
static u8 s_Keyboard;
static u8 s_Joystick;

/* Reserved once-per-frame CPU budget for the future PSG music + effects
 * driver (docs/sound-budget.md). It runs at the end of the dashboard line
 * interrupt (line ~174, active display), never inside the VBlank window that
 * page publication needs. Until the driver exists, a calibrated busy loop
 * consumes the budget so every frame-deadline check already includes it.
 * 30 T-states per iteration including MSX M1 wait states; the -30 covers
 * entry, setup and return (measured on openMSX). 0 disables it. */
#ifndef WINGS_SOUND_TSTATES
#define WINGS_SOUND_TSTATES 3000
#endif
#ifdef WINGS_P1_FLIGHT
/* The PSG driver (msx/sound.c) in the sound budget. */
#define WINGS_LINE_ISR_TAIL jp _Sound_Field
#elif WINGS_SOUND_TSTATES
#define WINGS_LINE_ISR_TAIL jp _SoundBudget
static void SoundBudget(void) __naked
{
    __asm
        ld de, #(WINGS_SOUND_TSTATES - 30) / 30
    sound_budget_loop$:
        dec de
        ld a, d
        or e
        jr nz, sound_budget_loop$
        ret
    __endasm;
}
#else
#define WINGS_LINE_ISR_TAIL ret
#endif

void VDP_InterruptHandler(void)
{
    // The CRT saves all registers; direct writes leave interrupts disabled.
    __asm
        ld a, (_g_FirstState)
        ld (_g_DashboardSplit), a
        ld a, #1
        out (0x99), a
        ld a, #0x90
        out (0x99), a
        ld hl, #_g_TopPalette+2
        ld c, #0x9a
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        ld a, (_g_ScrollFine)
        out (0x99), a
        ld a, #0x9b
        out (0x99), a
        ld a, (_g_ScrollCoarse)
        out (0x99), a
        ld a, #0x9a
        out (0x99), a
        ld a, (_g_VerticalOffset)
        out (0x99), a
        ld a, #0x97
        out (0x99), a
        ld a, (_g_FirstSplit)
        out (0x99), a
        ld a, #0x93
        out (0x99), a
    __endasm;
    ++g_VBlankTicks;
    Input_Sample();
}
// Early scroll restoration compensates carrier heave. Palette switching
// stages ocean-unused colors early, then finishes before the icons at 183.
void VDP_HBlankHandler(void) __naked
{
    __asm
        ld a, (_g_DashboardSplit)
        cp #2
        jp z, pan_split$
        or a
        jp nz, dashboard_low_palette$
        // Requested on line 170: back to the dashboard's scroll. Lines
        // 170..175 read dark pixels under either scroll (the guard line
        // drawn at VRAM 170 - scroll .. 171, then the dashboard's solid top
        // rows 172..175), so a late interrupt changes nothing on screen.
        // R19 before R23: the VDP fires on line R19 - R23, and the old R19
        // with the new R23 could name the next line (see pan_split$).
        ld a, #1
        ld (_g_DashboardSplit), a
        // Leave time to return from this ISR before requesting the next.
        ld a, #174
        out (0x99), a
        ld a, #0x93
        out (0x99), a
        xor a
        out (0x99), a
        ld a, #0x97
        out (0x99), a
        xor a
        out (0x99), a
        ld a, #0x9b
        out (0x99), a
        xor a
        out (0x99), a
        ld a, #0x9a
        out (0x99), a
        // Stage the upper dashboard colors on the dark lines, leaving a
        // short final transfer before the icons at 183.
        ld a, #6
        out (0x99), a
        ld a, #0x90
        out (0x99), a
        ld hl, #_g_BottomPalette+12
        ld c, #0x9a
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        ret
    pan_split$:
        // Top lines done: scroll the play area by heave + fine pan, and
        // request the dashboard split (counted in the new scroll).
        // R19 first: the VDP fires on line R19 - R23. Writing R23 first left
        // the old R19 (this split) with the new scroll for a few
        // instructions, naming a line just ahead; with a small pan the
        // interrupt fired there, and once this one returned the dashboard
        // branch ran at the top of the screen, with its scroll and palette
        // (the plane in other colours during the pan, 2026-11-17).
        xor a
        ld (_g_DashboardSplit), a
        ld a, (_g_LineSplit)
        out (0x99), a
        ld a, #0x93
        out (0x99), a
        ld a, (_g_PlayOffset)
        out (0x99), a
        ld a, #0x97
        out (0x99), a
        ld a, (_g_PlayFine)
        out (0x99), a
        ld a, #0x9b
        out (0x99), a
        ld a, (_g_PlayCoarse)
        out (0x99), a
        ld a, #0x9a
        out (0x99), a
        ret
    dashboard_low_palette$:
        ld a, #1
        out (0x99), a
        ld a, #0x90
        out (0x99), a
        ld hl, #_g_BottomPalette+2
        ld c, #0x9a
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        outi
        WINGS_LINE_ISR_TAIL
    __endasm;
}
/* The scrolls and line splits for the page being published. */
#ifdef WINGS_P1_FLIGHT
static u8 s_Band[2];   /* per page: the message band's height, 0 without */
#endif
/* The published band and its text pixel at the right edge (verification). */
volatile u8 g_DisplayBand;
volatile u16 g_DisplayTicker;
#ifdef WINGS_P1_FLIGHT
/* A rocket impact's background flash (0x031a): of its 5 published frames
 * the odd counts show white or red in colour 0, the sky (the dashboard does
 * not use it; the line interrupts never write it). Set in VBlank, so the
 * change and the new page come together. */
static u8 s_SkyShown;
static void SkyFlash(void)
{
    u8 show = 0;
    if (g_Combat.sky_flash)
    {
        if (g_Combat.sky_flash & 1) show = g_Combat.sky_color;
        --g_Combat.sky_flash;
    }
    if (show == s_SkyShown) return;
    s_SkyShown = show;
    VDP_SetPaletteEntry(0, show == COMBAT_SKY_RED ? 0x0070 : show ? 0x0777 :
        g_TerrainPalette[0] | ((u16)g_TerrainPalette[1] << 8));
}
#endif

static void PublishScroll(u8 page, u16 camera)
{
    u8 scroll = s_RenderHeave + s_RenderFine;
    g_PlayFine = (-camera) & 7;
    g_PlayCoarse = ((camera & 255) + 7) >> 3;
    g_PlayOffset = 0 - scroll;
    g_LineSplit = 170 - scroll;   /* line 170 in the play scroll */
#ifdef WINGS_P1_FLIGHT
    if (s_Band[page])
    {
        /* The message band: VRAM rows 0.. unscrolled, the text pixel
         * g_MessageScroll at its right edge; the split is requested 2 lines
         * early (MESSAGE_BAND leaves sky there). */
        g_VerticalOffset = 0;
        g_FirstSplit = s_Band[page] - 2;
        g_FirstState = 2;
        camera = g_MessageScroll[page] + 1;
        g_DisplayTicker = g_MessageScroll[page];
    }
    else
#else
    (void)page;
#endif
    {
        g_VerticalOffset = 0 - s_RenderHeave;
        /* R19 counts scrolled lines: line s with the top region's -heave.
         * The split is requested up to 2 lines early: those lines then show
         * VRAM rows 254..255 (kept sky) under the play scroll, and an
         * interrupt up to 2 lines late shows rows fine - 2 .. fine - 1 (sky:
         * g_TopClip), so a late interrupt changes nothing on screen.
         * Measured lateness is 0-2 lines on nearly every field, rarely 3-4. */
        g_FirstSplit = (int8_t)s_RenderFine > 0 ? s_RenderFine - (s_RenderFine < 2 ? s_RenderFine : 2) : g_LineSplit;
        g_FirstState = (int8_t)s_RenderFine > 0 ? 2 : 0;
    }
    g_ScrollFine = (-camera) & 7;
    g_ScrollCoarse = ((camera & 255) + 7) >> 3;
    g_DashboardSplit = g_FirstState;
    g_DisplayFine = s_RenderFine;
#ifdef WINGS_P1_FLIGHT
    g_DisplayBand = s_Band[page];
#endif
    VDP_SetVerticalOffset(g_VerticalOffset);
    VDP_SetHBlankLine(g_FirstSplit);
    VDP_SetHorizontalOffset(camera & 255);
}
static void WaitVBlank(void)
{
    u8 tick = g_VBlankTicks;
    do { __asm halt __endasm; } while (g_VBlankTicks == tick);
}

static void DrawColumn(u16 world, u8 page)
{
    Terrain_DrawColumn(world, page);
}

/* A close-view pan step of s_PanStep tile rows: move the page's scenery
 * with a VDP block move instead of rebuilding it (a rebuild took 250+ ms),
 * shift the tile cache to match, and redraw what the move exposed. */
/* The first VRAM row with scenery on a page drawn at pan pan_rows: the
 * visible 256-px blocks' tops (converter), lowered by the pan, and never
 * below the wave strip (row 160). */
static u8 SceneryTop(u16 camera, u8 pan_rows)
{
    int16_t left = (int16_t)(camera + 8) >> 8, right = (int16_t)(camera + 255) >> 8;
    u8 top = 160, block;
    if (left >= 0 && left < TERRAIN_BLOCKS && (block = g_TerrainBlockTop[left] + pan_rows) < top) top = block;
    if (right >= 0 && right < TERRAIN_BLOCKS && (block = g_TerrainBlockTop[right] + pan_rows) < top) top = block;
    return top;
}

static void PanStep(u8 page, u16 camera)
{
    u16 base = (u16)page * 256;
    u8 rows, top = SceneryTop(camera, g_PanRows), old = g_PanRows;
    g_PanRows = s_ViewKey << 3;
    if (s_PanStep > 0)
    {
        /* Rows top..171-rows move down; above them the view is sky. */
        rows = (u8)s_PanStep << 3;
        if (top + rows < 172)
            VDP_CommandYMMM(base + 171 - rows, 0, base + 171, 172 - rows - top, 0x08); /* bottom up */
        VDP_CommandHMMV(0, base + top, 256, top + rows < 172 ? rows : 172 - top, 0);
        /* Waves drawn at no pan moved into the bottom tile row. */
        if (!old) Terrain_RepaintBand(page, camera, 18 - s_ViewKey, 18 - s_ViewKey, 0, 172);
    }
    else
    {
        /* Rows top..171 move up; the cache (map rows) already knows what
         * comes up from below: repaint it, the last row moved only half in. */
        rows = (u8)(-s_PanStep) << 3;
        VDP_CommandYMMM(base + top, 0, base + top - rows, 172 - top, 0);
        Terrain_RepaintBand(page, camera, TERRAIN_MAP_ROWS - 1 + s_PanStep - s_ViewKey, TERRAIN_MAP_ROWS - 1 - s_ViewKey, 0, 172);
    }
    s_PageScale[page] = s_ViewKey;
    /* The old guard line moved with the page. */
    s_GuardTop[page] = s_PanStep > 0 ? (s_GuardTop[page] + rows > 172 ? 172 : s_GuardTop[page] + rows)
                                     : s_GuardTop[page] - rows;
}

/* The guard line moves with the scroll. When it shrinks, repaint the rows
 * it leaves from the tile cache (map rows at the page's pan). */
static void RepairGuard(u8 page, u16 camera)
{
    u8 top = 170 - (u8)(s_RenderHeave + (int8_t)s_RenderFine), old = s_GuardTop[page];
    s_GuardTop[page] = top;
    if (old >= top) return;
    if (!g_PanRows && !s_PanStep)
    {
        /* Waves drawn last frame here: rows 166..171 are redrawn opaque and
         * 161..162 restored from their backup; rows 163..165 are water only
         * away from the island's beach (x 16..3972, a-scene.json bands). */
        if (old < 163) old = 163;
        if (top > 166) top = 166;
        if (old >= top || (int16_t)(camera + 255) < 16 || (int16_t)(camera + 8) >= 3973) return;
    }
    /* Only the rows the guard leaves (old .. top - 1), not whole tile rows:
     * over the carrier a full band was a long VDP wait. */
    Terrain_RepaintBand(page, camera, (old - 24 - g_PanRows) >> 3, (top - 25 - g_PanRows) >> 3, old, top);
    s_Repainted = 1;
}

/* Every column a page shows from this camera (unchanged ones cost a check). */
static void DrawView(u16 camera, u8 page)
{
    u8 count = 33;
    camera &= 65528u;
    do { DrawColumn(camera, page); camera += 8; } while (--count);
}



// Save/restore the clean, byte-aligned footprint, splitting at the page seam.
// Backups live at x=0,y=212 in each page, never displayed.
static void Background(u8 page, u8 save)
{
    u16 ring = s_OldX[page];
    u16 base = (u16)page * 256;
    u8 offset = 0, width = s_OldWidth[page], part;
    if (!save)
    {
        /* Restore: a ring copy from the backup (Z80, msx/vdp_ring.c). */
        VDP_RING_SET(0, base + 212, base + s_OldY[page], s_OldHeight[page], VDP_CMD_HMMM);
        Vdp_RingCopy((u8)ring, width);
        return;
    }
    while (width)
    {
        part = width;
        if ((u16)(ring & 255) + part > 256) part = 256 - (ring & 255);
        VDP_CommandHMMM(ring & 255, base + s_OldY[page],
                        offset, base + 212, part, s_OldHeight[page]);
        offset += part;
        width -= part;
        ring = (ring + part) & 255;
    }
}

/* The aircraft pixel data's ROM banks (tools/convert_hellcat.py AIRCRAFT_BANKS). */
static const u8 s_AircraftBank[7] = {8, 9, 10, 14, 4, 5, 6};
void Atlas_LoadShape(const AircraftShape* shape)
{
    const u8* source;
    u16 offset = (u16)shape->data;
    // Atlas rows 0..511 are the lower 64 KiB (pages 0/1), 512..1023 the upper.
    u16 address = (shape->atlas_y & 511) * 128 + shape->atlas_x / 2;
    u8 high = shape->atlas_y >= 512;
    u8 scratch[32];
    u8 row;
    for (row = 0; row < shape->height; ++row)
    {
        Scenery_Read(s_AircraftBank[offset >> 13], offset & 8191, scratch, shape->width / 2);
        offset += shape->width / 2;
        source = scratch;
        VDP_WriteVRAM(source, address, high, shape->width / 2);
        address += 128;
    }
}

static u8 s_GroundShape, s_FlashSlot[2];
static void LoadCaches(void)
{
    u8 i;
    s_GroundShape=s_FlashSlot[0]=s_FlashSlot[1]=255;
    for (i=0; i<AIRCRAFT_STATIC_SHAPES; ++i) Atlas_LoadShape(&g_AircraftShapes[i]);
#ifdef WINGS_P1_FLIGHT
    for (i=0; i<WHEEL_PIECE_COUNT; ++i) Atlas_LoadShape(&g_WheelPieces[i]);
    Smoke_LoadPieces();
#endif
}

/* The original cannon overlay matching the drawn pitch pose. There is no
 * source art for distant, ground or turning poses, so none is drawn there. */
static const AircraftShape* GunFlash(u8 frame)
{
    u8 i, slot, index = 255;
    if (!g_Combat.flash || g_TerrainFar) return 0;
#ifdef WINGS_P1_FLIGHT
    if (FLIGHT_ON_DECK(&s_World.flight)) return 0;
#endif
    for (i = 0; i < 10; ++i)
    {
        if (g_PitchRight[i] == frame) index = i;
        else if (g_PitchLeft[i] == frame) index = 10 + i;
    }
    if (index == 255) return 0;
    // Alternate fa/fb on presented frames. The captured state then records
    // the variant drawn on this page. Each variant streams into its own
    // small VRAM slot when the pose changes.
    g_Combat.flash ^= 3;
    slot = g_Combat.flash - 1;
    index += slot * 20;
    if (s_FlashSlot[slot] != index)
    {
        Atlas_LoadShape(&g_GunFlash[index]);
        s_FlashSlot[slot] = index;
    }
    return &g_GunFlash[index];
}

/* Transparent copy of an atlas shape at world X dx / screen row dy,
 * clipped to the camera and the playfield rows above limit. */
static void CopyShape(u8 page, const AircraftShape* shape, int16_t dx, int16_t dy, u16 camera, int16_t limit)
{
    int16_t left = dx < (int16_t)camera ? (int16_t)camera : dx, right = dx + shape->width;
    int16_t top = dy < (int16_t)g_TopClip ? (int16_t)g_TopClip : dy, bottom = dy + shape->height;
    if (right > (int16_t)(camera + 256)) right = camera + 256;
    if (bottom > limit) bottom = limit;
    if (right <= left || bottom <= top) return;
    VDP_RING_SET((u8)(shape->atlas_x + left - dx), shape->atlas_y + top - dy,
                 (u16)page * 256 + top, bottom - top, VDP_CMD_LMMM + VDP_OP_TIMP);
    Vdp_RingCopy((u8)left, right - left);
}

#ifdef WINGS_P1_FLIGHT
static u8 SmokeActive(void)
{
    u8 i;
    for (i = 0; i < SMOKE_COUNT; ++i) if (g_Smoke[i].stage) return 1;
    return 0;
}
/* The plane's origin row on screen, set by DrawAircraft. A static keeps the
 * call below from holding DrawAircraft's locals live (SDCC then spills
 * through the whole function: ~900 bytes). */
static int16_t s_OriginRow;
/* The arresting rope while the cable holds the plane (src/msx/rope.c). */
static void DrawArrest(u8 page, u16 world, u16 camera, int16_t limit)
{
    s_RenderRope = 255;
    if (s_World.flight.mode != FLIGHT_ARREST || g_TerrainFar || s_CrashFrame != 255) return;
    s_RenderRope = g_FlightCable;
    Rope_Draw(page, (int16_t)FLIGHT_CABLE_X(g_FlightCable),
              s_World.flight.facing_left ? (int16_t)world + 16 : (int16_t)world - 16,
              s_OriginRow, camera, limit);
}
#endif

static void DrawAircraft(u8 page, u8 frame, u16 world, u16 y, u16 camera)
{
    const AircraftShape* shape = &g_AircraftShapes[frame];
    const AircraftShape* flash;
    int16_t dx, dy, fx = 0, fy = 0, left, top, right, bottom, limit = 172;
#ifdef WINGS_P1_FLIGHT
    int16_t wy = 0, wx;
    u8 wheel = 255, first = 0, last = 0, i;
#endif
    s_RenderCrash = s_CrashFrame;
    if (s_CrashFrame != 255)
    {
        /* The crash art streams into the host shape's atlas slot (restored
         * when the next plane launches) and replaces the plane. */
        shape = &g_CrashShapes[s_CrashFrame];
        if (s_CrashLoaded != s_CrashFrame) { Atlas_LoadShape(shape); s_CrashLoaded = s_CrashFrame; }
        flash = 0;
    }
    else
    {
    if (frame >= AIRCRAFT_STATIC_SHAPES && s_GroundShape != frame)
    {
        Atlas_LoadShape(shape);
        s_GroundShape=frame;
    }
    flash = GunFlash(frame);
    }
    if (g_TerrainFar && s_CrashFrame == 255) { shape = Dashboard_FarShape(frame); world = FAR_X(world); }
    dx = (int16_t)world + shape->dx - (g_TerrainFar ? 0 : 25);
    dy = (g_TerrainFar ? 161 - ((WINGS_FLIGHT_MAX_Y - y) >> 3) :
          WINGS_FLIGHT_MAX_Y - y > 131 ? 14 : 145 - (WINGS_FLIGHT_MAX_Y - y)) + shape->dy;
#ifdef WINGS_P1_FLIGHT
    if (FLIGHT_ON_DECK(&s_World.flight) && s_CrashFrame == 255)
    {
        /* The slow deck poses carry their own wheels: rest them on the deck.
         * Rolling fast or held by a cable, the level pose stands at deck
         * height (y 1160) on the wheel overlay. */
        dy = (s_World.flight.mode == FLIGHT_GROUND && !s_World.flight.fast_roll ?
              129 - shape->height : 145 - (int16_t)(WINGS_FLIGHT_MAX_Y - FLIGHT_DECK_Y) + shape->dy) + g_Carrier.depth;
    }
    else
#endif
    dy -= s_RenderHeave + (int8_t)s_RenderFine;
#ifdef WINGS_P1_FLIGHT
    if (g_Carrier.stage != CARRIER_DECK) limit = CARRIER_WELL_BOTTOM;
    /* Sinking (mode 6): drawn lower each 3 ticks; the opaque waves (from
     * the strip's third row) cover it, as the original draws them after it. */
    if (s_World.flight.mode == FLIGHT_SINKING) { dy += g_Crash.depth; limit = 163 - s_RenderHeave; }
#endif
    left = dx; right = dx + shape->width;
    top = dy; bottom = dy + shape->height;
#ifdef WINGS_P1_FLIGHT
    s_OriginRow = dy - shape->dy + 16;
#endif
#ifdef WINGS_P1_FLIGHT
    if (!g_TerrainFar && s_CrashFrame == 255) wheel = s_Wheel;
    s_RenderWheel = wheel; s_RenderGear = s_GearPos;
    if (wheel != 255)
    {
        /* Pieces share the plane's drawing origin, (5 - gear) px higher
         * while the gear is going up or down. */
        first = g_WheelFirst[wheel]; last = g_WheelFirst[wheel + 1];
        wy = dy - shape->dy + s_GearPos - 5;
        for (i = first; i < last; ++i)
        {
            wx = (int16_t)world + g_WheelPieces[i].dx - 25;
            if (wx < left) left = wx;
            if (wx + g_WheelPieces[i].width > right) right = wx + g_WheelPieces[i].width;
            if (wy + g_WheelPieces[i].dy < top) top = wy + g_WheelPieces[i].dy;
            if (wy + g_WheelPieces[i].dy + g_WheelPieces[i].height > bottom) bottom = wy + g_WheelPieces[i].dy + g_WheelPieces[i].height;
        }
    }
#endif
    if (flash)
    {
        // Both shapes use the original drawing origins around one object point.
        fx = (int16_t)world + flash->dx - 25;
        fy = dy - shape->dy + flash->dy;
        if (fx < left) left = fx;
        if (fx + flash->width > right) right = fx + flash->width;
        if (fy < top) top = fy;
        if (fy + flash->height > bottom) bottom = fy + flash->height;
    }
    if (left < (int16_t)camera) left = camera;
    if (right > (int16_t)(camera + 256)) right = camera + 256;
    if (top < (int16_t)g_TopClip) top = g_TopClip;
    if (bottom > limit) bottom = limit;
    s_Valid[page] = 0;
    if (right <= left || bottom <= top) return;
    s_OldX[page] = (left & 254);
    s_OldY[page] = top;
    s_OldWidth[page] = ((right + 1) & ~1) - (left & ~1);
    s_OldHeight[page] = bottom - top;
    Background(page, 1);
    s_Valid[page] = 1;
#ifdef WINGS_P1_FLIGHT
    /* Behind the plane, as in the original. */
    for (i = first; i < last; ++i)
        CopyShape(page, &g_WheelPieces[i], (int16_t)world + g_WheelPieces[i].dx - 25, wy + g_WheelPieces[i].dy, camera, limit);
#endif
    CopyShape(page, shape, dx, dy, camera, limit);
    if (flash) CopyShape(page, flash, fx, fy, camera, limit);
#ifdef WINGS_P1_FLIGHT
    DrawArrest(page, world, camera, limit);
#endif
}

u8 g_TopClip;
static void Render(u8 page, u16 camera, u16 world, u16 y, u8 frame)
{
    u16 previous, next;
    g_RenderPage = page;
    g_TopClip = !g_TerrainFar && (int8_t)s_RenderFine > 0 ? s_RenderFine : 0;
#ifdef WINGS_P1_FLIGHT
    /* The message band shows VRAM rows 0 .. band + 1 (a late split) at its
     * own scroll: no overlays there. */
    { u8 scroll = s_RenderHeave + s_RenderFine;
      s_Band[page] = g_MessageActive ? MESSAGE_BAND((int8_t)scroll > 0 ? scroll : 0) : 0;
      if (s_Band[page]) g_TopClip = s_Band[page] + 2; }
#endif
    g_ViewChange = s_PageScale[page] != s_ViewKey;
    s_PanStep = 0;
    if (g_ViewChange && s_PageScale[page] < 8 && s_ViewKey < 8)
    {
        /* Close view to close view: a pan step of up to 3 tile rows moves
         * the page instead of rebuilding it. */
        int8_t step = (int8_t)s_ViewKey - (int8_t)s_PageScale[page];
        if (step >= -3 && step <= 3) { s_PanStep = step; g_ViewChange = 0; }
    }
    /* Restores see the page as drawn (its old pan); PanStep moves it on. */
    g_PanRows = !g_ViewChange && s_PageScale[page] < 8 ? s_PageScale[page] << 3 : (s_ViewKey == 8 ? 0 : s_ViewKey << 3);
    g_Rendering = 1;
    if (g_ViewChange)
    {
        s_Valid[page] = 0;
        VDP_CommandHMMV(0, (u16)page * 256, 256, 172, 0);
        Terrain_InitPage(page);
        DrawView(camera, page);
        s_Camera[page] = camera;
        s_PageScale[page] = s_ViewKey;
        s_GuardTop[page] = 172;
    }
    Weapons_Restore(page, g_ViewChange);
#ifdef WINGS_P1_FLIGHT
    Rope_Restore(page, g_ViewChange);
#endif
    if (s_Valid[page]) Background(page, 0);
    Dashboard_RestoreWaves(page, g_ViewChange);
#ifdef WINGS_P1_FLIGHT
    /* Erase this page's old smoke before the new columns: the tile cache does
     * not know about it, so scrolled-in columns must see the clean sky. */
    s_Smoked = Smoke_Restore(page, g_ViewChange, camera);
#endif
    s_Repainted = 0;
    if (s_PanStep) { PanStep(page, camera); s_Repainted = 1; }
    g_PanRows = s_ViewKey == 8 ? 0 : s_ViewKey << 3;
    /* Before the scrolled-in columns compare against the cache. */
    RepairGuard(page, camera);
    /* Signed differences: the camera may cross 0 into the open sea. */
    if ((int16_t)(camera - s_Camera[page]) > 0)
    {
        previous = (s_Camera[page] + 255) & 65528u;
        next = (camera + 255) & 65528u;
        while ((int16_t)(next - previous) > 0)
        {
            previous += 8;
            DrawColumn(previous, page);
        }
    }
    else
    {
        previous = (s_Camera[page] + 8) & 65528u;
        next = (camera + 8) & 65528u;
        while ((int16_t)(previous - next) > 0)
        {
            previous -= 8;
            DrawColumn(previous, page);
        }
    }
    s_Camera[page] = camera;
#ifdef WINGS_P1_FLIGHT
    /* A wrecked hut changed map columns: redraw what this page shows (the
     * renderer skips columns whose runs did not change). */
    if (g_TerrainDirty & (page + 1))
    {
        g_TerrainDirty &= ~(page + 1);
        DrawView(camera, page);
    }
#endif
    /* The elevator is redrawn only when something repainted under it. */
    if (!g_TerrainFar)
    {
#ifdef WINGS_P1_FLIGHT
        Elevator_Draw(page,camera,g_Carrier.depth,g_ViewChange || s_Smoked || s_Repainted);
#endif
        Ship_Draw(page, camera);
#ifdef WINGS_P1_FLIGHT
        Ship_DrawCrew(page, camera, g_ViewChange);
#endif
        Dashboard_Waves(page, camera, s_Wave, s_RenderHeave);
    }
#ifdef WINGS_P1_FLIGHT
    /* Engine smoke, behind the plane. The near view pins a high plane to the
     * top rows; the smoke follows it down by the same amount. */
    Smoke_Draw(page, camera, g_TerrainFar,
               !g_TerrainFar && WINGS_FLIGHT_MAX_Y - y > 131 ? (int16_t)(WINGS_FLIGHT_MAX_Y - y) - 131 : 0,
               (int8_t)(s_RenderHeave + (int8_t)s_RenderFine), g_Carrier.stage != CARRIER_DECK ? CARRIER_WELL_BOTTOM : 172);
#endif
    DrawAircraft(page, frame, world, y, camera);
    Weapons_Draw(page, camera, g_TerrainFar, s_RenderHeave, &g_Combat);
    Dashboard_Status(page, g_Game.sortie.weapon, g_Game.sortie.stock, g_Game.progress.lives);
    Dashboard_Kills(page, g_Game.progress.kills > 99 ? 99 : (u8)g_Game.progress.kills);
    Dashboard_Score(page, g_Game.progress.score);
#ifdef WINGS_P1_FLIGHT
    s_RenderGauges[0] = g_Engine.oil_needle; s_RenderGauges[1] = g_Engine.fuel_needle;
    s_RenderGauges[2] = g_Engine.lamps;
#endif
    /* Dial redraws wait out fast frames over the carrier (the heaviest
     * render): needles move one step per tick, so a short delay is not seen. */
    Dashboard_Gauges(page, s_RenderGauges,
#ifdef WINGS_P1_FLIGHT
                     s_CarrierView && s_World.flight.speed >= 1000
#else
                     0
#endif
                     ); /* now holds what this page shows */
    /* The guard line: VRAM 170 - scroll .. 171, dark under either scroll
     * around the dashboard split (see VDP_HBlankHandler). */
    VDP_CommandHMMV(0, (u16)page * 256 + s_GuardTop[page], 256, 172 - s_GuardTop[page], 0x11);
    {
        s_RenderPilot = Cockpit_Draw(page, world, y, s_Aircraft.facing_left);
    }
    // Query the strip while the final miniature command is still executing.
    s_RenderSurface = Mission_Query(world);
    // Finish the hidden page before it can be published.
    VDP_CommandWait();
#ifdef WINGS_P1_FLIGHT
    /* After the commands: a rebuild clears the band's rows. */
    if (g_MessageActive) Message_Draw(page, g_ViewChange);
#endif
    g_Rendering = 0;
}

static u8 ReadDirection(void)
{
    u8 input = 0;
    s_Joystick = Joystick_Read(JOY_PORT_1);
    if (IS_JOY_PRESSED(s_Joystick, JOY_INPUT_DIR_UP)) input |= FLIGHT_UP;
    if (IS_JOY_PRESSED(s_Joystick, JOY_INPUT_DIR_RIGHT)) input |= FLIGHT_RIGHT;
    if (IS_JOY_PRESSED(s_Joystick, JOY_INPUT_DIR_DOWN)) input |= FLIGHT_DOWN;
    if (IS_JOY_PRESSED(s_Joystick, JOY_INPUT_DIR_LEFT)) input |= FLIGHT_LEFT;
    s_Keyboard = Keyboard_Read(8);
    if (!(s_Keyboard & 32)) input |= FLIGHT_UP;
    if (!(s_Keyboard & 128)) input |= FLIGHT_RIGHT;
    if (!(s_Keyboard & 64)) input |= FLIGHT_DOWN;
    if (!(s_Keyboard & 16)) input |= FLIGHT_LEFT;
    return input;
}

static u16 s_Latest;
static void ConsumeActions(void)
{
    __asm di __endasm;
    Controls_Block(&g_Controls);s_Latest=g_Controls.latest;
    __asm ei __endasm;
    s_LastControl=s_Latest;
    g_Combat.primary_pending=g_Combat.secondary_pending=0;
}
/* A fresh plane on deck: new sortie, or the next plane after a crash. */
static void NewPlane(void)
{
    World_Reset(&s_World); Aircraft_Reset(&s_Aircraft); Combat_Reset(&g_Combat);
#ifdef WINGS_P1_FLIGHT
    Carrier_Reset(&g_Carrier);
    Aircraft_SyncFlight(&s_Aircraft,&s_World.flight,s_World.x>>8);
    Engine_Reset(&g_Engine,&g_Game.sortie);
    s_EngineSteps=0;
    s_GearPos=5; s_Wheel=255;
    Smoke_Reset(); Smoke_ClearPages();
    Planes_NewPlane();
#endif
    s_CrashFrame=255;
    if (s_CrashLoaded!=255) { Atlas_LoadShape(&g_AircraftShapes[CRASH_HOST_SHAPE]); s_CrashLoaded=255; }
    s_PageScale[0]=s_PageScale[1]=255;
}

#ifdef WINGS_P1_FLIGHT
/* The crashed plane is lost: the next one waits in the hold, where the
 * service arms it (the weapon is the player's choice again) and the lift
 * brings it up, as after a landing (0xd2); the island and the ships keep
 * their damage. No plane left: the game ends. */
/* The US carrier took its 4th torpedo (docs/enemy-planes.md): the game
 * ends at the next new plane (0x35fe). Its sinking is not drawn. */
static u8 CarrierLost(void)
{
    if (g_Ships.hull[SHIP_MAX]) return 0;
    g_Game.phase=GAME_OVER; g_Game.cursor=g_Game.notice=0;
    return 1;
}
static void LosePlane(void)
{
    if (Game_LosePlane(&g_Game) && !CarrierLost()) { NewPlane(); g_Carrier.stage=CARRIER_HOLD; }
    s_UiDirty=1;
}

/* A flying plane's contact this step: a landing, a bounce or a crash. Out
 * of the step loop: inline there, SDCC spilled its arithmetic to the stack
 * (some hundreds of T-states a step). Contact needs the plane near the
 * surface: the cheap gate on the frame's cached bottom and surface skips
 * the exact (banked) check on nearly every step. */
static void StepContact(void)
{
    int16_t base;
    u8 contact;
    if (s_World.flight.mode!=FLIGHT_AIRBORNE) return;
    base=(int16_t)WINGS_FLIGHT_MAX_Y-(int16_t)(s_World.flight.y>>8)-s_ContactBottom;
    if (base>=(int16_t)s_ContactSurface+1 && base>0) return;
    contact=Landing_Contact(&s_World.flight,s_World.x>>8,g_Engine.failed,
        s_ContactBottom,Landing_Height(s_World.x>>8));
    if (!contact) return;
    g_LastContact=contact;
    if (contact==LANDING_CRASH) { Crash_Contact(&s_World.flight,s_World.x>>8); return; }
    if (contact==LANDING_BOUNCE) Sound_Effect(SOUND_SCREECH,s_World.x>>8);   /* 0xbb7e */
    Landing_Apply(&s_World.flight,contact);
}
#endif

#ifdef WINGS_P1_FLIGHT
/* Directions pressed since the last frame. A tap that starts and ends
 * between two frames still drives the flight model for this frame's ticks:
 * one tick of DOWN alone, for instance, starts a dive that then holds. */
static u8 s_Tapped;
/* The mission's last island fell: advanced once (0x5694), its promotion
 * plane joins at the hold (0x0122). */
static u8 s_MissionAdvanced, s_Promotion;
u8 g_BriefIslands, g_BriefShips;
/* The weapon panel (msx/screens.c): drawn; the view rendered behind it this
 * frame (its scroll is published); the last phase. */
static u8 s_Panel, s_PanelRendered, s_LastPhase;
/* The briefing's palette is up; a page's dashboard rows were drawn over (a
 * full-screen menu: restored before the page is drawn on again). */
static u8 s_BriefColours, s_DashGone[2], s_RankShown, s_PaletteShown;
/* The intro's screen shown: 0 none, else its colours (SCREENS_TITLE, SCREENS_INTRO). */
static u8 s_IntroShown;
#ifdef WINGS_HIGH_SCORES
static u8 s_Typing;   /* the name entry has scanned the keyboard once */
#endif
/* A new mission (game start or the next one): the island restored, no
 * ticker, nothing advanced yet. */
static void StartMission(void)
{
    Island_Reset();
    Ships_Reset();
    Planes_Reset();
    g_MessageActive = g_MessageWait = 0;
    s_MissionAdvanced = s_Promotion = 0;
}
#endif
static u8 ReadActions(void)
{
    u8 reset_weapons=0, result, action, old_phase, old_cursor, old_notice, old_invert;
    u16 pressed;
    ControlEvent event;
#ifdef WINGS_P1_FLIGHT
    if (g_Game.phase==GAME_PLAY && g_Carrier.stage==CARRIER_HOLD)
    {
        /* Back in the hold with the mission done: the next mission's
         * briefing instead of the service (0x0122). */
        if (g_Island.complete) Game_NextMission(&g_Game,s_Promotion);
        else if (!CarrierLost()) Game_OpenService(&g_Game);
        Engine_Reset(&g_Engine,&g_Game.sortie);
        s_UiDirty=1;ConsumeActions();return 0;
    }
#endif
    for (;;)
    {
        __asm di __endasm;
        result=Controls_Pop(&g_Controls,&event);
        s_Latest=g_Controls.latest;
        __asm ei __endasm;
        if (result==2) { s_LastControl=s_Latest; break; }
        if (!result) break;
        pressed=event.state & ~s_LastControl; s_LastControl=event.state;
        old_phase=g_Game.phase; old_cursor=g_Game.cursor;
        old_notice=g_Game.notice; old_invert=g_Game.invert;
#ifdef WINGS_P1_FLIGHT
        /* A fire button on the elevator lowers it, unless Ctrl-R comes with
         * it: that restarts from anywhere (manual). */
        if (g_Game.phase==GAME_PLAY && (pressed & (ACTION_PRIMARY|ACTION_SECONDARY)) &&
            !(pressed & ACTION_RESTART) && Carrier_Request(&g_Carrier,&s_World.flight,s_World.x>>8))
        {
            Combat_Reset(&g_Combat);action=GAME_CONTEXT_CHANGED;
        }
        else
#endif
        action=Game_HandleAction(&g_Game,pressed);
        g_InputInvert=g_Game.invert;
        if (old_phase!=g_Game.phase || old_cursor!=g_Game.cursor || old_notice!=g_Game.notice || old_invert!=g_Game.invert) s_UiDirty=1;
        if (action & GAME_RESTARTED)
        {
            Combat_Reset(&g_Combat);
#ifdef WINGS_P1_FLIGHT
            Island_Reset();
            Ships_Reset();
            Planes_NewGame();
#endif
        }
        if (action & GAME_START_SORTIE)
        {
#ifdef WINGS_P1_FLIGHT
            StartMission();
#endif
            NewPlane(); reset_weapons=1;
        }
#ifdef WINGS_P1_FLIGHT
        if (action & GAME_LEAVE_SERVICE) {Carrier_Raise(&g_Carrier);Combat_Reset(&g_Combat);reset_weapons=1;}
#endif
        if (action & GAME_CONTEXT_CHANGED)
        {
            ConsumeActions();break;
        }
        if (g_Game.phase==GAME_PLAY
#ifdef WINGS_P1_FLIGHT
            && g_Carrier.stage==CARRIER_DECK
#endif
            )
        {
            if (pressed & ACTION_SECONDARY) g_Combat.secondary_pending=1;
            if (pressed & ACTION_PRIMARY) g_Combat.primary_pending=1;
#ifdef WINGS_P1_FLIGHT
            s_Tapped|=(u8)(pressed & (ACTION_UP|ACTION_RIGHT|ACTION_DOWN|ACTION_LEFT));
#endif
#ifdef WINGS_DEBUG_CONTROLS
            if (pressed & ACTION_DEBUG_RESET)
            {
                Combat_Reset(&g_Combat); Game_SetLoadout(&g_Game,g_Game.sortie.weapon);
                Flight_Reset(&s_World.flight); Aircraft_Reset(&s_Aircraft); reset_weapons=1;
            }
            if ((pressed & ACTION_DEBUG_TURN) && !s_World.flight.vx && !s_World.flight.vy)
                Aircraft_RequestTurn(&s_Aircraft);
#endif
        }
    }
    return reset_weapons;
}

void main(void)
{
    u16 camera, world, y;
    u16 surface;
    u8 weapons, reset_weapons, i;
    u8 page, frame, steps, step, input, tick, turn, held = 0;
    u8 base_steps, present_ticks, core_phase = 0;
#ifdef WINGS_P1_FLIGHT
    /* RAM is not cleared at boot: before any line interrupt runs the driver. */
    Sound_Reset();
    Sound_LoadEffects();
    s_SkyShown = 0;
#endif
    g_Ready = g_Rendering = g_FramePublished = g_HoldFlight = 0;
    g_MissedFrames = g_PanOverruns = 0;
    g_InputEnabled=0; g_InputInvert=g_InputOverflow=0;
    Controls_Reset(&g_Controls); s_LastControl=0; s_UiDirty=1;
    Game_Reset(&g_Game);
#ifdef WINGS_P1_FLIGHT
    /* RAM is not cleared at boot: no front-end screen is up yet. */
    s_Panel=s_PanelRendered=s_LastPhase=s_BriefColours=s_RankShown=s_IntroShown=s_DashGone[0]=s_DashGone[1]=0;
    s_PaletteShown=SCREENS_PLAY;
    /* At boot the intro (docs/intro.md), then rank selection. */
    Game_Intro(&g_Game);
#endif
#ifdef WINGS_HIGH_SCORES
    Game_ClearScores();
#endif
    Dashboard_LoadTables();
#ifdef WINGS_DEBUG_CONTROLS
    g_Game.phase=GAME_PLAY;
#endif
    for (i=0; i<32; ++i) g_TopPalette[i]=g_TerrainPalette[i];
    Dashboard_CopyPalette(g_BottomPalette);
    Combat_Reset(&g_Combat);
    Weapons_Init();
    g_TerrainFar = g_ViewChange = s_PageScale[0] = s_PageScale[1] = 0;
    g_VerticalOffset = s_RenderHeave = 0; g_LineSplit = 170;
    g_PlayOffset = g_FirstState = s_RenderFine = s_ViewKey = g_PanRows = 0; g_FirstSplit = 170;
#ifdef WINGS_P1_FLIGHT
    g_MessageActive = g_MessageWait = s_Band[0] = s_Band[1] = 0;
#endif
    s_GuardTop[0] = s_GuardTop[1] = 172;
    g_DisplayPage = 0;
    s_Valid[0] = s_Valid[1] = 0;
    World_Reset(&s_World);
#ifdef WINGS_P1_FLIGHT
    Carrier_Reset(&g_Carrier);
    /* The boot render reads the instruments before any sortie starts. */
    Engine_Reset(&g_Engine,&g_Game.sortie);
    s_EngineSteps=0;
    /* RAM is not cleared at boot: the smoke state must be. */
    Smoke_Reset(); Smoke_ClearPages();
#endif
    camera = s_World.camera;
    world = s_World.x >> 8;
    s_Camera[0] = s_Camera[1] = camera;
    Aircraft_Reset(&s_Aircraft);
#ifdef WINGS_P1_FLIGHT
    Aircraft_SyncFlight(&s_Aircraft,&s_World.flight,s_World.x>>8);
#endif
    VDP_SetMode(VDP_MODE_SCREEN5);
    VDP_EnableDisplay(FALSE);
    /* Border uses index 1 (dark navy, identical in playfield and dashboard
       palettes); TP=1 keeps index-0 sky pixels from showing the border. */
    VDP_EnableTransparency(FALSE);
    VDP_SetColor(1);
    VDP_SetPalette(g_TerrainPalette);
    /* VDP_SetPalette enables interrupts before its 32 data bytes. A line
     * interrupt in between rewrites colours 1..15 and leaves the palette
     * pointer wrapped to 0, so the rest of this write lands on colour 0
     * (the sky), which the ISR never rewrites. Set colour 0 atomically. */
    VDP_SetPaletteEntry(0, g_TerrainPalette[0] | ((u16)g_TerrainPalette[1] << 8));
    VDP_FillVRAM(0, 0, 0, 0);
    VDP_FillVRAM(0, 0, 1, 0);
    LoadCaches();
    Dashboard_Load();
    Ship_Load();
#ifdef WINGS_P1_FLIGHT
    Elevator_Load();
#endif
    Terrain_Load();
#ifdef WINGS_P1_FLIGHT
    Planes_NewGame();
    StartMission(); g_TerrainDirty = 0;
    g_BriefIslands = g_Island.left; g_BriefShips = g_Ships.left;
    Rope_Reset();
#endif
    for (page = 0; page < 2; ++page)
    {
        Terrain_InitPage(page);
        DrawView(camera, page);
    }
    Render(0, camera, world, s_World.flight.y >> 8, s_Aircraft.shape);
    VDP_SetPage(0);
    VDP_SetHorizontalMode(VDP_HSCROLL_SINGLE);
    VDP_EnableMask(TRUE);
    VDP_SetHorizontalOffset(camera & 255);
    g_ScrollFine = (-camera) & 7;
    g_ScrollCoarse = ((camera & 255) + 7) >> 3;
    g_PlayFine = g_ScrollFine; g_PlayCoarse = g_ScrollCoarse;
#ifdef WINGS_P1_FLIGHT
#endif
    VDP_SetHBlankLine(171);
    VDP_EnableHBlank(TRUE);
    VDP_EnableDisplay(TRUE);
    g_DisplayCamera = camera;
    g_DisplayWorld = world;
    g_DisplaySurfaceWord = Mission_Query(world);
    g_DisplayScale = 1; g_DisplayWave = s_Wave; g_DisplayPilot = s_RenderPilot;
    g_DisplayHeave = s_RenderHeave; g_DisplayShipFrame = g_ShipFrame;
    g_DisplayX = world - camera;
    g_DisplayY = s_World.flight.y >> 8;
    g_SelectedFrame = s_Aircraft.shape;
    g_Turning = 0;
    base_steps = (g_VDP_REGSAV[9] & 2) ? WINGS_PRESENT_TICKS * 3 : WINGS_PRESENT_TICKS * 5 / 2;
    steps = base_steps;
    WaitVBlank();
    tick = g_VBlankTicks;
    Game_View(&g_Game,g_GameView);
    g_InputEnabled=1;
    g_Ready = 1;
    for (;;)
    {
        present_ticks=WINGS_PRESENT_TICKS; steps=base_steps;
#ifdef WINGS_P1_FLIGHT
#ifdef WINGS_HIGH_SCORES
        if (g_Game.phase==GAME_NAME) present_ticks=1;   /* every key tap */
#endif
#endif
#ifdef WINGS_P1_FLIGHT
        if (g_Game.phase==GAME_PLAY && (g_Carrier.stage==CARRIER_RAISING || g_Carrier.stage==CARRIER_LOWERING))
            present_ticks=CARRIER_PRESENT_TICKS;
        steps=(g_VDP_REGSAV[9]&2) ? present_ticks*3 : present_ticks*5/2;
#endif
#if (WINGS_PRESENT_TICKS & 1)
        steps = base_steps;
        if (!(g_VDP_REGSAV[9] & 2)) { steps += core_phase; core_phase ^= 1; }
#endif
        // Reserve draw time for bombs and rockets while retaining the 150 Hz flight and
        // weapon simulation clock. Hit-scan gunfire (flash overlay plus short
        // strike marks) fits the base presentation period.
        if (g_Combat.count>COMBAT_GUN_COUNT || g_Combat.secondary_cooldown ||
            g_Combat.secondary_pending || g_Combat.rockets || Weapons_PendingRestore()) present_ticks+=2;
#ifdef WINGS_P1_FLIGHT
        /* Heavy scenes: with 4+ smoke, gun or soldier shapes on screen, or
         * after a frame that came within a VBlank of the base deadline
         * (large puffs cost several pieces each), 2 more VBlanks
         * (docs/frame-budget.md). The carrier no longer needs its own
         * allowance on NTSC (2026-11-17: low over it, 99% of frames take
         * 116 ms of the 133). */
        if (g_Game.phase==GAME_PLAY && g_Carrier.stage==CARRIER_DECK &&
            (g_SmokeDrawnCount[g_DisplayPage] >= 4 || s_Tight)) present_ticks+=2;
        /* A ship's guns in view with 8+ shapes (barrels, splashes, the
         * plane's smoke): 2 more, an even 5 frames a second rather than
         * late ones (docs/ships.md). */
        if (s_ShipGuns && g_SmokeDrawnCount[g_DisplayPage] >= 8) present_ticks+=2;
#endif
        steps=(g_VDP_REGSAV[9]&2) ? present_ticks*3 : present_ticks*5/2;
        weapons=reset_weapons=0; input=0; turn=0;
        if (!g_HoldFlight)
        {
            reset_weapons=ReadActions();
#ifdef WINGS_P1_FLIGHT
            /* The briefing closes by itself after 240 PAL frames (0x8590),
             * 4.8 s; 288 NTSC fields. */
            if (Game_Wait(&g_Game,present_ticks,g_VDP_REGSAV[9]&2)) { ConsumeActions(); s_UiDirty=1; }
            /* The weapons are chosen over the carrier, the plane in the hold
             * (the original's game start). */
            if (g_Game.phase==GAME_LOADOUT && s_LastPhase==GAME_BRIEFING)
            {
                NewPlane(); g_Carrier.stage=CARRIER_HOLD;
            }
            s_LastPhase=g_Game.phase;
#ifdef WINGS_HIGH_SCORES
            /* A high score's name, typed: keys held as it opens are old. */
            if (g_Game.phase==GAME_NAME)
            {
                i=Menu_Key(!s_Typing); s_Typing=1;
                while (i) { if (Game_Type(&g_Game,i)) s_UiDirty=1; i=Menu_Key(0); }   /* all queued, one redraw */
            }
            else s_Typing=g_TypeMode=0;
#endif
#endif
            if (g_Game.phase==GAME_PLAY)
            {
#ifdef WINGS_P1_FLIGHT
                input=(u8)(s_Latest|s_Tapped) & 15; s_Tapped=0;
#else
                input=s_Latest & 15;
#endif
                weapons=((s_Latest & ACTION_PRIMARY) ? COMBAT_FIRE : 0) |
                        ((s_Latest & ACTION_SECONDARY) ? COMBAT_BOMB : 0);
#ifdef WINGS_P1_FLIGHT
                if (reset_weapons) steps=0; /* Publish the fully lowered platform first. */
                if (!FLIGHT_ON_DECK(&s_World.flight) && s_World.flight.y>LANDING_CHECK_Y)
                    Landing_Prepare(&s_World.flight,s_World.x>>8,&s_ContactBottom,&s_ContactSurface);
                else s_ContactBottom=0, s_ContactSurface=0;
#endif
                for (step=0; step<steps; ++step)
                {
#ifdef WINGS_P1_FLIGHT
                    /* Not at a tick's first or last step: no run starts there. */
                    if ((u8)(s_World.flight.step-1)<FLIGHT_TICK_STEPS-2 && g_Carrier.stage==CARRIER_DECK &&
                        s_World.flight.mode<FLIGHT_DEAD && !g_Engine.failed &&
                        (i=Step_Batch(steps-1-step,weapons))) { step+=i-1; continue; }
                    if (g_Carrier.stage!=CARRIER_DECK)
                    {
                        if (Carrier_Step(&g_Carrier)) {ConsumeActions();break;}
                    }
                    else
#endif
                    {
#ifdef WINGS_P1_FLIGHT
                        /* Sunk or burning (modes 6, 8): 12 s, or fire held after
                         * 2.4 s (0xaf7c), and the plane is lost. */
                        if (s_World.flight.mode>=FLIGHT_SINKING &&
                            (g_Crash.clock>=CRASH_TICKS || (g_Crash.clock>CRASH_SKIP_TICKS && weapons)))
                        { LosePlane(); ConsumeActions(); reset_weapons=1; break; }
                        /* Throttle (the flight model's flag): oil reads higher.
                         * Fuel burns in flight; no warnings once crashed (0xee38). */
                        if (++s_EngineSteps==ENGINE_TICK_STEPS)
                        {
                            s_EngineSteps=0;
                            Engine_Tick(&g_Engine,&g_Game.sortie,s_World.flight.mode==FLIGHT_AIRBORNE,
                                s_World.flight.throttle,s_World.flight.mode<FLIGHT_DEAD);
                        }
                        if (g_Engine.failed || s_World.flight.mode>=FLIGHT_DEAD)
                        {
                            /* No power and no guns (original mode 4): the plane falls. */
                            if (s_World.flight.mode==FLIGHT_AIRBORNE) Flight_EngineOut(&s_World.flight);
                            input=0; weapons=0;
                            g_Combat.primary_pending=g_Combat.secondary_pending=0;
                        }
#endif
                        World_StepSample(&s_World,input,step==steps-1);
#ifdef WINGS_P1_FLIGHT
                        StepContact();
#endif
                    if (Combat_Tick(&g_Combat)
#ifdef WINGS_P1_FLIGHT
                        && Combat_Required(&g_Combat,weapons)
#endif
                        )
                    {
                        if (((weapons & COMBAT_FIRE) || g_Combat.primary_pending) && g_Combat.cooldown<2)
                            g_Combat.aim_pitch=Aircraft_FlightPitch(&s_World.flight);
#ifdef WINGS_P1_FLIGHT
                        /* The rockets' inputs: launch angle and speed, the view;
                         * the ships' bob, for every weapon's burst on a deck. */
                        g_Combat.bob=g_ShipHeave+2;
                        if (g_Game.sortie.weapon==WEAPON_ROCKETS)
                        {
                            g_Combat.path=s_World.flight.path; g_Combat.speed=s_World.flight.speed;
                            g_Combat.far=g_TerrainFar;
                        }
#endif
                        Combat_Advance(&g_Combat,&g_Game.sortie,s_World.x>>8,s_World.flight.y>>8,
                            s_World.flight.vx,s_World.flight.vy,
#ifdef WINGS_P1_FLIGHT
                            s_World.flight.facing_left,
#else
                            s_Aircraft.facing_left,
#endif
                            weapons);
#ifdef WINGS_P1_FLIGHT
                        /* Only a weapon tick with a fresh burst or strike can hit
                         * anything (the count saturates at 65535). */
                        if (g_Combat.impacts != s_Impacts || s_Impacts == 65535u)
                        {
                            s_Impacts = g_Combat.impacts;
                            Island_Impacts(&g_Combat, &g_Game.progress.score);
                            Sound_Bursts();
                        }
#endif
                    }
                    }
                    if (++s_AnimTick==12)
                    {
                        s_AnimTick=0; s_Wave=s_Wave ? s_Wave-1 : 11;
#ifdef WINGS_P1_FLIGHT
                        /* One original tick: smoke drifts on through a crash; only
                         * a running sortie puts out new puffs. */
                        Smoke_Tick(&s_World.flight, s_World.x >> 8, g_Game.sortie.oil, s_World.flight.mode < FLIGHT_SINKING);
                        Island_Tick();
                        /* The ships' sinking clocks, and destroyed guns' smoke. */
                        if (g_Ships.smoking || g_Ships.sinking)
                            Ships_Tick(s_World.flight.mode == FLIGHT_AIRBORNE, &g_Game.progress.score);
                        /* The dugout guns (the original updates them once per
                         * drawn frame, probably at this rate). */
                        s_GunsDrawn = Island_Guns(&s_World.flight, s_World.x >> 8,
                            s_World.flight.mode == FLIGHT_AIRBORNE &&
                            g_Carrier.stage == CARRIER_DECK && g_Game.phase == GAME_PLAY,
                            &g_Engine, &g_Game.sortie);
                        s_SoldiersMoving = Island_Soldiers(&g_Game.progress.score);
                        /* Enemy planes (0xe7d6) and the torpedo-plane timer
                         * (0xbc02), after the player's move. */
                        /* Only with something to do: planes up, the timer
                         * running, ship lists with planes left. */
                        if (g_Planes.live || g_Planes.timer || g_Planes.lists) Step_Planes(weapons);
#endif
                    }
#ifdef WINGS_P1_FLIGHT
                    if (step==steps-1) Aircraft_SyncFlight(&s_Aircraft,&s_World.flight,s_World.x>>8);
#else
                    Aircraft_StepSample(&s_Aircraft,s_World.flight.vx,s_World.flight.vy,step==steps-1);
#endif
                }
                Ship_Advance(step<steps ? step+1 : steps);
#ifdef WINGS_P1_FLIGHT
                /* The gear slides one pixel per presented frame toward its
                 * state (the original: one per drawn frame). */
                { u8 down = Flight_GearDown(&s_World.flight, s_World.x >> 8) ? 5 : 0;
                  if (s_GearPos < down) ++s_GearPos; else if (s_GearPos > down) --s_GearPos; }
                s_Wheel = Aircraft_Wheel(&s_World.flight);
#endif
            }
        }
#ifdef WINGS_P1_FLIGHT
        /* The deck shows the spare planes (0x3abc). */
        Island_Parked(g_Game.progress.lives);
        /* The last island fell this frame: the next mission number, and the
         * rank's last mission promotes (its ticker says so). */
        if (g_Island.complete && !s_MissionAdvanced)
        {
            s_MissionAdvanced = 1;
            s_Promotion = Game_AdvanceMission(&g_Game);
            if (s_Promotion && g_Island.message == ISLAND_MESSAGE_MISSION) g_Island.message = ISLAND_MESSAGE_PROMOTION;
        }
        Sound_Update(&s_World.flight, s_World.x >> 8,
                     (g_Game.phase == GAME_PLAY ? SOUND_PLAYING : 0) | (s_World.flight.mode >= FLIGHT_SINKING ? SOUND_CRASHED : 0), steps);
        /* The ticker moves 2 px a VBlank (msx/message.c). */
        if (g_Game.phase==GAME_PLAY && (g_Island.message || g_MessageActive)) Message_Update(present_ticks);
#endif
        camera = s_World.camera;
        world = s_World.x >> 8;
        y = s_World.flight.y >> 8;
        g_TerrainFar = WINGS_FLIGHT_MAX_Y - y > 186;
#ifdef WINGS_P1_FLIGHT
        /* The camera follows the plane with its lead (core/fighters.c);
         * past the map ends the sea goes on. */
        i = g_TerrainFar ? CAMERA_FAR : 0;
        if (s_World.flight.facing_left) i |= CAMERA_LEFT;
        if (g_Game.phase != GAME_PLAY) i |= CAMERA_RESET;
        else if (s_World.flight.mode < FLIGHT_SINKING && g_Carrier.stage == CARRIER_DECK && !FLIGHT_ON_DECK(&s_World.flight)) i |= CAMERA_MOVE;
        camera = Camera_Follow(world, i, present_ticks);
#else
        camera = g_TerrainFar ? world >> 3 : world;
        { u16 maximum = g_TerrainFar ? ((WINGS_WORLD_WIDTH + 7) >> 3) - 256 : WINGS_WORLD_WIDTH - 256;
          camera = camera < 128 ? 0 : camera - 128; if (camera > maximum) camera = maximum; }
#endif
        g_ViewChange = 0;
        s_RenderHeave = !g_TerrainFar && (u16)(camera + 256) > CARRIER_X - 440u && camera < CARRIER_X + 336u ? g_ShipHeave : 0;
        { int16_t altitude = (int16_t)(WINGS_FLIGHT_MAX_Y - y);
          u8 pan = !g_TerrainFar && altitude > 131 ? (u8)(altitude - 131) : 0;  /* original 0x26e */
          /* Tile rows (software) plus a fine scroll of -1..7 px (hardware):
           * a plane holding height on a row boundary keeps its tile rows
           * (at -1 the last play line shows terrain row 171, still valid). */
          if (g_TerrainFar) s_ViewKey = 8;
          else if (s_ViewKey == 8 || pan + 1 < (u8)(s_ViewKey << 3) || pan - (s_ViewKey << 3) > 7)
              s_ViewKey = pan >> 3;
          s_RenderFine = g_TerrainFar ? 0 : (u8)(pan - (s_ViewKey << 3)); }
#ifdef WINGS_P1_FLIGHT
        s_CarrierView = !g_TerrainFar && (u16)(camera + 256) > CARRIER_X - 440u && camera < CARRIER_X + 336u;
#endif
        frame = s_Aircraft.shape;
#ifdef WINGS_P1_FLIGHT
        s_CrashFrame = s_World.flight.mode == FLIGHT_WRECK ? CRASH_WRECK_RIGHT + s_World.flight.facing_left : 255;
#endif
        page = g_DisplayPage ^ 1;
#ifdef WINGS_P1_FLIGHT
        /* The ships' guns (0x4c3e) run in the original's render loop (from
         * 0x38d2): once a presented frame, before it is drawn. */
        s_ShipGuns = g_Ships.present || g_Ships.splashes || g_Combat.torpedo.live || g_Combat.enemy.live ? Ships_Guns(&s_World.flight, s_World.x >> 8,
            s_World.flight.mode == FLIGHT_AIRBORNE &&
            g_Carrier.stage == CARRIER_DECK && g_Game.phase == GAME_PLAY,
            &g_Engine, &g_Game.sortie, &g_Combat) : 0;
#endif
#ifdef WINGS_P1_FLIGHT
        /* A front-end screen goes (its colours stay until the next page is
         * published); after the panel both pages are rebuilt. */
        if (s_Panel && g_Game.phase!=GAME_LOADOUT && g_Game.phase!=GAME_SERVICE) { s_Panel=0; s_PageScale[0]=s_PageScale[1]=255; }
        if (g_Game.phase!=GAME_RANK) s_RankShown=0;
        if (g_Game.phase!=GAME_INTRO) s_IntroShown=0;
        if (g_Game.phase!=GAME_BRIEFING) s_BriefColours=0;
        if (s_DashGone[page] && g_Game.phase!=GAME_BRIEFING && g_Game.phase!=GAME_RANK && g_Game.phase!=GAME_INTRO) { Dashboard_Restore(page); s_DashGone[page]=0; }
#endif
        if (g_Game.phase!=GAME_PLAY)
        {
#ifdef WINGS_P1_FLIGHT
            s_Band[0] = s_Band[1] = 0;
#endif
#ifdef WINGS_P1_FLIGHT
            /* Rank selection, full screen; then the highlight moves on the
             * page shown (msx/screen_end.c). */
            /* The intro's screens, full screen, each drawn on the hidden page. */
            if (g_Game.phase==GAME_INTRO)
            {
                page=g_DisplayPage;
                if (s_UiDirty)
                {
                    page^=1; Screens_Intro(page,g_Game.cursor);
                    s_DashGone[page]=1; s_PageScale[page]=255;
                    s_IntroShown=g_Game.cursor==GAME_INTRO_TITLE ? SCREENS_TITLE : SCREENS_INTRO;
                    s_UiDirty=0;
                }
            }
            else
            if (g_Game.phase==GAME_RANK)
            {
                page=g_DisplayPage;
                if (s_UiDirty)
                {
                    if (s_RankShown) Screens_RankLine(page,g_Game.cursor);
                    else
                    {
                        page^=1; Screens_Rank(page,g_Game.cursor);
                        s_DashGone[page]=1; s_PageScale[page]=255; s_RankShown=1;
                    }
                    s_UiDirty=0;
                }
            }
            else
            /* The briefing, full screen (msx/screen_end.c). */
            if (g_Game.phase==GAME_BRIEFING)
            {
                if (!s_UiDirty) page=g_DisplayPage;
                else
                {
                    Screens_Briefing(page,&g_Game);
                    s_BriefColours=s_DashGone[page]=1; s_PageScale[page]=255; s_UiDirty=0;
                }
            }
            else
            /* The weapon panel over the carrier view, frozen: at game start
             * the view is rendered first; in the hold it is shown already. */
            if (g_Game.phase==GAME_LOADOUT || g_Game.phase==GAME_SERVICE)
            {
                page=g_DisplayPage;
                if (s_UiDirty)
                {
                    if (!s_Panel && s_PageScale[page]==255) { page^=1; Render(page,camera,world,y,frame); s_PanelRendered=1; }
                    /* Drawn on the page shown: its colours first. */
                    else if (s_PaletteShown!=SCREENS_WEAPON) Screens_Palette(s_PaletteShown=SCREENS_WEAPON);
                    Screens_Weapons(page,s_PanelRendered ? camera : g_DisplayCamera,!s_Panel,&g_Game);
                    s_Panel=1; s_UiDirty=0;
                }
            }
            else
            /* "THE END" over the play view as it was, frozen (0xaf7c). */
            if (s_UiDirty && g_Game.phase==GAME_OVER)
            {
                /* Drawn on the page shown: the view stays as it is (not a
                 * render, so g_Rendering stays clear). */
                page=g_DisplayPage;
                Screens_DrawEnd(page,g_DisplayCamera);
                Dashboard_Status(page,g_Game.sortie.weapon,g_Game.sortie.stock,g_Game.progress.lives);
                VDP_CommandWait();
                s_PageScale[0]=s_PageScale[1]=255; s_UiDirty=0;
            }
            else
#endif
            if (s_UiDirty)
            {
                g_RenderPage=page; g_Rendering=1;
                Menu_Draw(page,&g_Game);
                Dashboard_Status(page,g_Game.sortie.weapon,g_Game.sortie.stock,g_Game.progress.lives);
                Dashboard_Kills(page,g_Game.progress.kills > 99 ? 99 : (u8)g_Game.progress.kills);
                Dashboard_Score(page,g_Game.progress.score);
                Dashboard_Gauges(page,s_RenderGauges,0);
                VDP_CommandWait(); g_Rendering=0;
                s_PageScale[page]=255; s_UiDirty=0;
            }
            else page=g_DisplayPage;
        }
        else if (
#ifdef WINGS_P1_FLIGHT
            g_DisplayElevator!=g_Carrier.depth ||
#endif
            reset_weapons || s_PageScale[page] != s_ViewKey ||
#ifdef WINGS_P1_FLIGHT
            g_DisplayGauges[0] != g_Engine.oil_needle || g_DisplayGauges[1] != g_Engine.fuel_needle ||
            g_DisplayGauges[2] != g_Engine.lamps || g_DisplayCrash != s_CrashFrame ||
            g_DisplayWheel != (g_TerrainFar || s_CrashFrame != 255 ? 255 : s_Wheel) || g_DisplayGear != s_GearPos ||
            SmokeActive() || s_GunsDrawn || s_ShipGuns || s_SoldiersMoving || g_MessageActive || g_SmokeDrawnCount[g_DisplayPage] || g_TerrainDirty ||
#endif
            g_DisplayWave != s_Wave || g_DisplayHeave != s_RenderHeave || camera != g_DisplayCamera || world != g_DisplayWorld || y != g_DisplayY || frame != g_SelectedFrame)
            Render(page, camera, world, y, frame);
        else page = g_DisplayPage;
        surface = s_RenderSurface;
#ifdef WINGS_P1_FLIGHT
        s_Tight = (u8)(g_VBlankTicks - tick) + 1 >= WINGS_PRESENT_TICKS;
#endif
        // Prepare the diagnostic/UI snapshot before the publication window.
        Game_View(&g_Game,s_NextGameView);
        // The deadline is a VBlank window. A completed page can still be
        // published if that window opened while rendering; do not discard it
        // and wait a ninth VBlank merely because the tick has reached eight.
        if ((u8)(g_VBlankTicks - tick) >= present_ticks)
        {
            if ((u8)(g_VBlankTicks - tick) > present_ticks || !(VDP_ReadStatus(2) & 64))
            {
                if (!g_ViewChange && g_Game.phase==GAME_PLAY)
                {
                    if (s_PanStep) ++g_PanOverruns; else ++g_MissedFrames;
                }
                WaitVBlank();
            }
        }
        else while ((u8)(g_VBlankTicks - tick) < present_ticks)
        {
#ifdef WINGS_P1_FLIGHT
            /* The ticker's text, with a whole frame still to spare. */
            if (g_MessageActive && g_Game.phase == GAME_PLAY && page != g_DisplayPage &&
                (u8)(g_VBlankTicks - tick) + 1 < present_ticks && Message_Work(page)) continue;
            /* The tile strips ahead, with a whole frame still to spare. */
            if (g_Game.phase == GAME_PLAY && (u8)(g_VBlankTicks - tick) + 1 < present_ticks &&
                Terrain_Prefetch(camera, s_World.flight.facing_left ? -1 : 1)) continue;
            /* The cockpit window's next picture, likewise (msx/cockpit.c). */
            if (g_Game.phase == GAME_PLAY && (u8)(g_VBlankTicks - tick) + 1 < present_ticks && Cockpit_Work()) continue;
#endif
            WaitVBlank();
        }
        tick = g_VBlankTicks;
        /* "THE END" keeps the view as shown; menus scroll to 0. */
        if (s_PanelRendered) s_PanelRendered=0;   /* the view just rendered: its scroll */
        else if (g_Game.phase==GAME_OVER || s_Panel) { camera=g_DisplayCamera; s_RenderHeave=g_DisplayHeave; s_RenderFine=g_DisplayFine; }
        else if (g_Game.phase!=GAME_PLAY) { camera=0; s_RenderHeave=0; s_RenderFine=0; }
        VDP_SetPage(page);
#ifdef WINGS_P1_FLIGHT
        /* The colours of the screen now shown, with it (msx/screen_end.c). */
        {
            u8 want = s_IntroShown ? s_IntroShown : s_RankShown ? SCREENS_RANK : s_BriefColours ? SCREENS_BRIEF : s_Panel ? SCREENS_WEAPON : SCREENS_PLAY;
            if (want!=s_PaletteShown) Screens_Palette(s_PaletteShown=want);
        }
#endif
        PublishScroll(page, camera);
        g_DisplayPage = page;
        g_DisplayCamera = camera;
        g_DisplayWorld = world;
        g_DisplayX =
            (g_TerrainFar ? FAR_X(world) : world) - camera;
        g_DisplayY = y;
        g_SelectedFrame = frame;
        g_Turning = s_Aircraft.turning;
        g_DisplaySurfaceWord = surface;
        g_DisplayScale = g_TerrainFar ? 8 : 1; g_DisplayWave = s_Wave; g_DisplayPilot = s_RenderPilot;
        g_DisplayHeave = s_RenderHeave; g_DisplayShipFrame = g_ShipFrame;
        __asm
            push bc
            push de
            push hl
            ld hl, #_s_NextGameView
            ld de, #_g_GameView
            ld bc, #8
            ldir
            pop hl
            pop de
            pop bc
        __endasm;
#ifdef WINGS_P1_FLIGHT
        g_DisplayElevator=g_Carrier.depth;
#endif
        g_DisplayGauges[0]=s_RenderGauges[0]; g_DisplayGauges[1]=s_RenderGauges[1];
        g_DisplayGauges[2]=s_RenderGauges[2]; g_DisplayCrash=s_RenderCrash;
#ifdef WINGS_P1_FLIGHT
        g_DisplayWheel=s_RenderWheel; g_DisplayGear=s_RenderGear; g_DisplayRope=s_RenderRope;
        g_DisplayScore = g_HudScore[page];
#endif
#ifdef WINGS_P1_FLIGHT
        if (g_Combat.sky_flash || s_SkyShown) SkyFlash();
#endif
        g_FramePublished ^= 1;
    }
}
