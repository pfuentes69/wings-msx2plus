#include "bios.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "keyboard.h"
#include "core/world.h"
#include "core/aircraft.h"
#ifdef WINGS_P1_FLIGHT
#include "core/carrier.h"
#include "msx/elevator.h"
CarrierState g_Carrier;
volatile u8 g_DisplayElevator;
#endif
#include "generated/hellcat_frames.h"
#ifndef WINGS_PRESENT_TICKS
#define WINGS_PRESENT_TICKS 2
#endif
#include "msx/terrain_renderer.h"
#include "generated/mission_tiles.h"
#include "core/mission.h"
#include "msx/dashboard.h"
#include "msx/ship.h"
#include "msx/weapons.h"
#include "core/combat.h"
#include "core/game.h"
#include "msx/input_sampler.h"
#include "msx/menu.h"
GameState g_Game;
u8 g_GameView[8], g_TopPalette[32], g_BottomPalette[32];
static u8 s_NextGameView[8];
static u16 s_LastControl;
static u8 s_UiDirty;
CombatState g_Combat;
#include "rom_mapper.h"
#include "msx/scenery_load.h"

volatile u8 g_ScrollFine, g_ScrollCoarse, g_VerticalOffset, g_LineSplit;
static u8 s_RenderHeave;
volatile u8 g_DashboardSplit;
volatile u16 g_DisplaySurfaceWord;
volatile u8 g_DisplayScale, g_DisplayWave, g_DisplayPilot, g_ViewChange;
volatile u8 g_DisplayHeave, g_DisplayShipFrame;
static u8 s_PageScale[2], s_Wave = 11, s_AnimTick, s_RenderPilot;
static u16 s_RenderSurface;
#include "input.h"

volatile u8 g_VBlankTicks, g_Ready, g_Rendering, g_FramePublished;
volatile u8 g_DisplayPage, g_SelectedFrame, g_DisplayX, g_Turning;
volatile u16 g_DisplayY;
volatile u8 g_HoldFlight, g_RenderPage;
volatile u16 g_DisplayCamera, g_DisplayWorld, g_MissedFrames;
static WorldState s_World;
static AircraftState s_Aircraft;
static u16 s_Camera[2], s_OldX[2];
static u8 s_OldY[2], s_OldWidth[2], s_OldHeight[2], s_Valid[2];
static u8 s_Keyboard;
static u8 s_Joystick;

void VDP_InterruptHandler(void)
{
    // The CRT saves all registers; direct writes leave interrupts disabled.
    __asm
        xor a
        ld (_g_DashboardSplit), a
        inc a
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
        ld a, (_g_LineSplit)
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
        or a
        jr nz, dashboard_low_palette$
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
        ld a, (_g_LineSplit)
        cp #170
        jr z, dashboard_palette$
        ld a, #1
        ld (_g_DashboardSplit), a
        // Leave time to return from this ISR before requesting the next.
        ld a, #174
        out (0x99), a
        ld a, #0x93
        out (0x99), a
        // Ocean pixels use only 0..5: stage the upper dashboard colors
        // during early scroll restoration, leaving a short final transfer.
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
        ret
    dashboard_palette$:
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
    __endasm;
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

// Save/restore the clean, byte-aligned footprint, splitting at the page seam.
// Backups live at x=0,y=212 in each page, never displayed.
static void Background(u8 page, u8 save)
{
    u16 ring = s_OldX[page];
    u16 base = (u16)page * 256;
    u8 offset = 0, width = s_OldWidth[page], part;
    while (width)
    {
        part = width;
        if ((u16)(ring & 255) + part > 256) part = 256 - (ring & 255);
        if (save)
            VDP_CommandHMMM(ring & 255, base + s_OldY[page],
                            offset, base + 212, part, s_OldHeight[page]);
        else
            VDP_CommandHMMM(offset, base + 212, ring & 255,
                            base + s_OldY[page], part, s_OldHeight[page]);
        offset += part;
        width -= part;
        ring = (ring + part) & 255;
    }
}

static void LoadShape(const AircraftShape* shape)
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
        Scenery_Read((offset >> 13) < 3 ? 8 + (offset >> 13) : 11 + (offset >> 13), offset & 8191, scratch, shape->width / 2);
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
    for (i=0; i<AIRCRAFT_STATIC_SHAPES; ++i) LoadShape(&g_AircraftShapes[i]);
}

/* The original cannon overlay matching the drawn pitch pose. There is no
 * source art for distant, ground or turning poses, so none is drawn there. */
static const AircraftShape* GunFlash(u8 frame)
{
    u8 i, slot, index = 255;
    if (!g_Combat.flash || g_TerrainFar) return 0;
#ifdef WINGS_P1_FLIGHT
    if (s_World.flight.mode == FLIGHT_GROUND) return 0;
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
        LoadShape(&g_GunFlash[index]);
        s_FlashSlot[slot] = index;
    }
    return &g_GunFlash[index];
}

/* Transparent copy of an atlas shape at world X dx / screen row dy,
 * clipped to the camera and the playfield rows above limit. */
static void CopyShape(u8 page, const AircraftShape* shape, int16_t dx, int16_t dy, u16 camera, int16_t limit)
{
    int16_t left = dx < (int16_t)camera ? (int16_t)camera : dx, right = dx + shape->width;
    int16_t top = dy < 0 ? 0 : dy, bottom = dy + shape->height;
    u16 base = (u16)page * 256;
    u8 ring, width, part, source_x;
    if (right > (int16_t)(camera + 256)) right = camera + 256;
    if (bottom > limit) bottom = limit;
    if (right <= left || bottom <= top) return;
    ring = left & 255;
    width = right - left;
    source_x = shape->atlas_x + left - dx;
    while (width)
    {
        part = width;
        if ((u16)ring + part > 256) part = 256 - ring;
        VDP_CommandLMMM(source_x, shape->atlas_y + top - dy, ring,
                        base + top, part, bottom - top, VDP_OP_TIMP);
        width -= part;
        source_x += part;
        ring += part;
    }
}

static void DrawAircraft(u8 page, u8 frame, u16 world, u16 y, u16 camera)
{
    const AircraftShape* shape = &g_AircraftShapes[frame];
    const AircraftShape* flash;
    int16_t dx, dy, fx = 0, fy = 0, left, top, right, bottom, limit = 172;
    if (frame >= AIRCRAFT_STATIC_SHAPES && s_GroundShape != frame)
    {
        LoadShape(shape);
        s_GroundShape=frame;
    }
    flash = GunFlash(frame);
    if (g_TerrainFar) { shape = Dashboard_FarShape(frame); world >>= 3; }
    dx = (int16_t)world + shape->dx - (g_TerrainFar ? 0 : 25);
    dy = (g_TerrainFar ? 161 - ((WINGS_FLIGHT_MAX_Y - y) >> 3) :
          WINGS_FLIGHT_MAX_Y - y > 131 ? 14 : 145 - (WINGS_FLIGHT_MAX_Y - y)) + shape->dy;
#ifdef WINGS_P1_FLIGHT
    if (s_World.flight.mode == FLIGHT_GROUND)
        dy = 129 - shape->height + g_Carrier.depth; /* Tire contact stays on deck across both ground poses. */
    else
#endif
    dy -= s_RenderHeave;
#ifdef WINGS_P1_FLIGHT
    if (g_Carrier.stage != CARRIER_DECK) limit = 145;
#endif
    left = dx; right = dx + shape->width;
    top = dy; bottom = dy + shape->height;
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
    if (top < 0) top = 0;
    if (bottom > limit) bottom = limit;
    s_Valid[page] = 0;
    if (right <= left || bottom <= top) return;
    s_OldX[page] = (left & 254);
    s_OldY[page] = top;
    s_OldWidth[page] = ((right + 1) & ~1) - (left & ~1);
    s_OldHeight[page] = bottom - top;
    Background(page, 1);
    s_Valid[page] = 1;
    CopyShape(page, shape, dx, dy, camera, limit);
    if (flash) CopyShape(page, flash, fx, fy, camera, limit);
}

static void Render(u8 page, u16 camera, u16 world, u16 y, u8 frame)
{
    u16 previous, next;
    g_RenderPage = page;
    g_ViewChange = s_PageScale[page] != g_TerrainFar;
    g_Rendering = 1;
    if (g_ViewChange)
    {
        s_Valid[page] = 0;
        VDP_CommandHMMV(0, (u16)page * 256, 256, 172, 0);
        Terrain_InitPage(page);
        for (previous = camera & 65528u; previous <= ((camera + 255) & 65528u); previous += 8)
            DrawColumn(previous, page);
        s_Camera[page] = camera;
        s_PageScale[page] = g_TerrainFar;
    }
    Weapons_Restore(page, g_ViewChange);
    if (s_Valid[page]) Background(page, 0);
    Dashboard_RestoreWaves(page, g_ViewChange);
    if (camera > s_Camera[page])
    {
        previous = (s_Camera[page] + 255) & 65528u;
        next = (camera + 255) & 65528u;
        while (previous < next)
        {
            previous += 8;
            DrawColumn(previous, page);
        }
    }
    else
    {
        previous = (s_Camera[page] + 8) & 65528u;
        next = (camera + 8) & 65528u;
        while (previous > next)
        {
            previous -= 8;
            DrawColumn(previous, page);
        }
    }
    s_Camera[page] = camera;
    if (!g_TerrainFar)
    {
#ifdef WINGS_P1_FLIGHT
        Elevator_Draw(page,camera,g_Carrier.depth,g_ViewChange);
#endif
        Ship_Draw(page, camera);
#ifdef WINGS_P1_FLIGHT
        Ship_DrawCrew(page, camera);
#endif
        Dashboard_Waves(page, camera, s_Wave, s_RenderHeave);
    }
    DrawAircraft(page, frame, world, y, camera);
    Weapons_Draw(page, camera, g_TerrainFar, s_RenderHeave, &g_Combat);
    Dashboard_Status(page, g_Game.sortie.weapon, g_Game.sortie.stock, g_Game.progress.lives);
    // A uniform guard line lets the raster reset settle before the panel.
    // Both old and new vertical offsets read the same dark separator pixel.
    VDP_CommandHMMV(0, (u16)page * 256 + 171 - s_RenderHeave,
                    256, s_RenderHeave + 1, 0x11);
    {
        u16 ahead = s_Aircraft.facing_left ? (world < 128 ? 0 : world - 128) : (world > WINGS_WORLD_WIDTH - 129 ? WINGS_WORLD_WIDTH - 1 : world + 128);
        u16 altitude = WINGS_FLIGHT_MAX_Y - y;
        s_RenderPilot = Dashboard_Draw(page, Mission_Surface(ahead), altitude > 255 ? 255 : altitude);
    }
    // Query the strip while the final miniature command is still executing.
    s_RenderSurface = Mission_Query(world);
    // Finish the hidden page before it can be published.
    VDP_CommandWait();
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
static u8 ReadActions(void)
{
    u8 reset_weapons=0, result, action, old_phase, old_cursor, old_notice, old_invert;
    u16 pressed;
    ControlEvent event;
#ifdef WINGS_P1_FLIGHT
    if (g_Game.phase==GAME_PLAY && g_Carrier.stage==CARRIER_HOLD)
    {
        Game_OpenService(&g_Game);s_UiDirty=1;ConsumeActions();return 0;
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
        if (g_Game.phase==GAME_PLAY && (pressed & (ACTION_PRIMARY|ACTION_SECONDARY)) &&
            Carrier_Request(&g_Carrier,&s_World.flight,s_World.x>>8))
        {
            Combat_Reset(&g_Combat);action=GAME_CONTEXT_CHANGED;
        }
        else
#endif
        action=Game_HandleAction(&g_Game,pressed);
        g_InputInvert=g_Game.invert;
        if (old_phase!=g_Game.phase || old_cursor!=g_Game.cursor || old_notice!=g_Game.notice || old_invert!=g_Game.invert) s_UiDirty=1;
        if (action & GAME_RESTARTED) Combat_Reset(&g_Combat);
        if (action & GAME_START_SORTIE)
        {
            World_Reset(&s_World); Aircraft_Reset(&s_Aircraft); Combat_Reset(&g_Combat);
#ifdef WINGS_P1_FLIGHT
            Carrier_Reset(&g_Carrier);
            Aircraft_SyncFlight(&s_Aircraft,&s_World.flight,s_World.x>>8);
#endif
            s_PageScale[0]=s_PageScale[1]=255; reset_weapons=1;
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
#ifdef WINGS_P1_FLIGHT
            /* Preserve a vertical tap sampled by VBlank even if it ended
             * before this foreground update. UP also cancels a latched dive. */
            if (s_World.flight.mode && (pressed & (ACTION_UP|ACTION_DOWN)) &&
                !(event.state & (ACTION_LEFT|ACTION_RIGHT)))
                s_World.flight.mode=(event.state & (ACTION_UP|ACTION_DOWN))==ACTION_DOWN ?
                    FLIGHT_STALL_DIVE : FLIGHT_AIRBORNE;
#endif
            if (pressed & ACTION_SECONDARY) g_Combat.secondary_pending=1;
            if (pressed & ACTION_PRIMARY) g_Combat.primary_pending=1;
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
    u16 column, camera, world, y;
    u16 surface;
    u8 weapons, reset_weapons, i;
    u8 page, frame, steps, step, input, tick, turn, held = 0;
    u8 base_steps, present_ticks, core_phase = 0;
    g_Ready = g_Rendering = g_FramePublished = g_HoldFlight = 0;
    g_MissedFrames = 0;
    g_InputEnabled=0; g_InputInvert=g_InputOverflow=0;
    Controls_Reset(&g_Controls); s_LastControl=0; s_UiDirty=1;
    Game_Reset(&g_Game);
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
    g_DisplayPage = 0;
    s_Valid[0] = s_Valid[1] = 0;
    World_Reset(&s_World);
#ifdef WINGS_P1_FLIGHT
    Carrier_Reset(&g_Carrier);
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
    VDP_FillVRAM(0, 0, 0, 0);
    VDP_FillVRAM(0, 0, 1, 0);
    LoadCaches();
    Dashboard_Load();
    Ship_Load();
#ifdef WINGS_P1_FLIGHT
    Elevator_Load();
#endif
    Terrain_Load();
    for (page = 0; page < 2; ++page)
    {
        Terrain_InitPage(page);
        for (column = camera & 65528u; column <= ((camera + 255) & 65528u); column += 8)
        {
            DrawColumn(column, page);
        }
    }
    Render(0, camera, world, s_World.flight.y >> 8, s_Aircraft.shape);
    VDP_SetPage(0);
    VDP_SetHorizontalMode(VDP_HSCROLL_SINGLE);
    VDP_EnableMask(TRUE);
    VDP_SetHorizontalOffset(camera & 255);
    g_ScrollFine = (-camera) & 7;
    g_ScrollCoarse = ((camera & 255) + 7) >> 3;
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
        if (g_Game.phase==GAME_PLAY && (g_Carrier.stage==CARRIER_RAISING || g_Carrier.stage==CARRIER_LOWERING))
            present_ticks=CARRIER_PRESENT_TICKS;
        steps=(g_VDP_REGSAV[9]&2) ? present_ticks*3 : present_ticks*5/2;
#endif
#if (WINGS_PRESENT_TICKS & 1)
        steps = base_steps;
        if (!(g_VDP_REGSAV[9] & 2)) { steps += core_phase; core_phase ^= 1; }
#endif
        // Reserve draw time independently for bombs and hit-scan gunfire while
        // retaining the 150 Hz flight and weapon simulation clock.
        if (g_Combat.count>COMBAT_GUN_COUNT || g_Combat.secondary_cooldown ||
            g_Combat.secondary_pending || Weapons_PendingRestore()) present_ticks+=2;
        if (g_Combat.projectile[0].kind || g_Combat.projectile[1].kind ||
            (g_Controls.latest & ACTION_PRIMARY)) present_ticks+=2;
        steps=(g_VDP_REGSAV[9]&2) ? present_ticks*3 : present_ticks*5/2;
        weapons=reset_weapons=0; input=0; turn=0;
        if (!g_HoldFlight)
        {
            reset_weapons=ReadActions();
            if (g_Game.phase==GAME_PLAY)
            {
                input=s_Latest & 15;
                weapons=((s_Latest & ACTION_PRIMARY) ? COMBAT_FIRE : 0) |
                        ((s_Latest & ACTION_SECONDARY) ? COMBAT_BOMB : 0);
#ifdef WINGS_P1_FLIGHT
                if (reset_weapons) steps=0; /* Publish the fully lowered platform first. */
#endif
                for (step=0; step<steps; ++step)
                {
#ifdef WINGS_P1_FLIGHT
                    if (g_Carrier.stage!=CARRIER_DECK)
                    {
                        if (Carrier_Step(&g_Carrier)) {ConsumeActions();break;}
                    }
                    else
#endif
                    {
                        World_StepSample(&s_World,input,step==steps-1);
                    if (Combat_Tick(&g_Combat)
#ifdef WINGS_P1_FLIGHT
                        && Combat_Required(&g_Combat,weapons)
#endif
                        )
                    {
                        if (((weapons & COMBAT_FIRE) || g_Combat.primary_pending) && g_Combat.cooldown<2)
                            g_Combat.aim_pitch=Aircraft_FlightPitch(&s_World.flight);
                        Combat_Advance(&g_Combat,&g_Game.sortie,s_World.x>>8,s_World.flight.y>>8,
                            s_World.flight.vx,s_World.flight.vy,
#ifdef WINGS_P1_FLIGHT
                            s_World.flight.facing_left,
#else
                            s_Aircraft.facing_left,
#endif
                            weapons);
                    }
                    }
                    if (++s_AnimTick==12) { s_AnimTick=0; s_Wave=s_Wave ? s_Wave-1 : 11; }
#ifdef WINGS_P1_FLIGHT
                    if (step==steps-1) Aircraft_SyncFlight(&s_Aircraft,&s_World.flight,s_World.x>>8);
#else
                    Aircraft_StepSample(&s_Aircraft,s_World.flight.vx,s_World.flight.vy,step==steps-1);
#endif
                }
                Ship_Advance(step<steps ? step+1 : steps);
            }
        }
        camera = s_World.camera;
        world = s_World.x >> 8;
        y = s_World.flight.y >> 8;
        g_TerrainFar = WINGS_FLIGHT_MAX_Y - y > 186;
        camera = g_TerrainFar ? world >> 3 : world;
        { u16 maximum = g_TerrainFar ? ((WINGS_WORLD_WIDTH + 7) >> 3) - 256 : WINGS_WORLD_WIDTH - 256;
          camera = camera < 128 ? 0 : camera - 128; if (camera > maximum) camera = maximum; }
        g_ViewChange = 0;
        s_RenderHeave = !g_TerrainFar && camera + 256 > 6592 && camera < 7368 ? g_ShipHeave : 0;
        frame = s_Aircraft.shape;
        page = g_DisplayPage ^ 1;
        if (g_Game.phase!=GAME_PLAY)
        {
            if (s_UiDirty)
            {
                g_RenderPage=page; g_Rendering=1;
                Menu_Draw(page,&g_Game);
                Dashboard_Status(page,g_Game.sortie.weapon,g_Game.sortie.stock,g_Game.progress.lives);
                VDP_CommandWait(); g_Rendering=0;
                s_PageScale[page]=255; s_UiDirty=0;
            }
            else page=g_DisplayPage;
        }
        else if (
#ifdef WINGS_P1_FLIGHT
            g_DisplayElevator!=g_Carrier.depth ||
#endif
            reset_weapons || s_PageScale[page] != g_TerrainFar || g_DisplayWave != s_Wave || g_DisplayHeave != s_RenderHeave || camera != g_DisplayCamera || world != g_DisplayWorld || y != g_DisplayY || frame != g_SelectedFrame)
            Render(page, camera, world, y, frame);
        else page = g_DisplayPage;
        surface = s_RenderSurface;
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
                ++g_MissedFrames;
                WaitVBlank();
            }
        }
        else while ((u8)(g_VBlankTicks - tick) < present_ticks) WaitVBlank();
        tick = g_VBlankTicks;
        if (g_Game.phase!=GAME_PLAY) { camera=0; s_RenderHeave=0; }
        g_ScrollFine = (-camera) & 7;
        g_ScrollCoarse = ((camera & 255) + 7) >> 3;
        VDP_SetPage(page);
        g_VerticalOffset = 0 - s_RenderHeave;
        VDP_SetVerticalOffset(g_VerticalOffset);
        g_LineSplit = s_RenderHeave ? 169 - s_RenderHeave : 170;
        VDP_SetHBlankLine(g_LineSplit);
        VDP_SetHorizontalOffset(camera & 255);
        g_DisplayPage = page;
        g_DisplayCamera = camera;
        g_DisplayWorld = world;
        g_DisplayX =
            (g_TerrainFar ? world >> 3 : world) - camera;
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
        g_FramePublished ^= 1;
    }
}
