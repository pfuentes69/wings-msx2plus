#include "bios.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "keyboard.h"
#include "core/flight.h"
#include "core/aircraft.h"
#include "core/scenery.h"
#include "generated/hellcat_frames.h"

volatile u8 g_VBlankTicks;

// MSXgl's IM2 ISR acknowledges the VDP and preserves the CPU registers.
void VDP_InterruptHandler(void)
{
    ++g_VBlankTicks;
}

static FlightState s_Flight;
static AircraftState s_Aircraft;
static u8 s_PageX[2], s_PageY[2], s_PageWidth[2], s_PageHeight[2], s_PageValid[2];
static u8 s_PageScenery[2];
static u16 s_Camera;
static u8 s_Scenery, s_Paused, s_Reverse, s_ScrollPhase;

// Published display state is distinct from simulation/back-page state.
volatile u8 g_SelectedFrame, g_DisplayPage, g_DisplayX, g_DisplayY;
volatile u8 g_FacingLeft, g_Rendering, g_Ready, g_FramePublished;
volatile u8 g_Turning, g_TurnStep;
volatile u16 g_RenderCount, g_MissedFrames;
volatile u16 g_DisplayCamera;
volatile u8 g_DisplayScenery, g_ScrollPaused, g_ScrollReverse;

static void LoadCaches(void)
{
    const AircraftShape* shape;
    const u8* source;
    u8 i, row, column, buffer[128];
    u16 address;
    for (i = 0; i < AIRCRAFT_SHAPE_COUNT; ++i)
    {
        shape = &g_AircraftShapes[i];
        source = shape->data;
        address = shape->atlas_y * 128 + shape->atlas_x / 2;
        for (row = 0; row < shape->height; ++row)
        {
            VDP_WriteVRAM(source, address, 1, shape->width / 2);
            source += shape->width / 2;
            address += 128;
        }
    }
    for (i = 0; i < 2; ++i)
        for (row = 0; row < 16; ++row)
        {
            for (column = 0; column < 128; ++column)
                buffer[column] = (Scenery_Pixel((u16)i * 256 + (u16)column * 2, row) << 4)
                    | Scenery_Pixel((u16)i * 256 + (u16)column * 2 + 1, row);
            address = ((u16)i << 15) + (u16)(196 + row) * 128;
            VDP_WriteVRAM(buffer, address, 1, 128);
        }
}

static void DrawScenery(u8 page)
{
    u16 camera = s_Camera & 510;
    u16 source_x = camera & 255;
    u16 source_y = camera < 256 ? 708 : 964;
    u16 width = 256 - source_x;
    u16 dest_y = (u16)page * 256 + 196;
    if (s_Scenery)
    {
        VDP_CommandHMMM(source_x, source_y, 0, dest_y, width, 16);
        VDP_CommandWait();
        if (source_x)
        {
            VDP_CommandHMMM(0, source_y == 708 ? 964 : 708, width, dest_y, source_x, 16);
            VDP_CommandWait();
        }
    }
    else if (s_PageScenery[page])
    {
        VDP_CommandHMMV(0, dest_y, 256, 16, 0);
        VDP_CommandWait();
    }
    s_PageScenery[page] = s_Scenery;
}

static void WaitVBlank(void)
{
    __asm
        halt
    __endasm;
}

static u8 ReadDirection(void)
{
    static const u8 directions[9] = { 0, 1, 3, 2, 6, 4, 12, 8, 9 };
    u8 keyboard = BIOS_GetJoystickDirection(BIOS_JOYSTICK_KEYBOARD);
    u8 joystick = BIOS_GetJoystickDirection(BIOS_JOYSTICK_PORT1);
    return directions[keyboard <= 8 ? keyboard : 0] | directions[joystick <= 8 ? joystick : 0];
}

static void DrawFrame(u8 frame, u8 x, u8 y, u8 page)
{
    const AircraftShape* shape = &g_AircraftShapes[frame];
    int16_t dx = (int16_t)x + shape->dx, dy = (int16_t)y + shape->dy;
    int16_t left = dx < 0 ? 0 : dx, top = dy < 0 ? 0 : dy;
    int16_t right = dx + shape->width, bottom = dy + shape->height;
    u8 width, height;
    if (right > 256) right = 256;
    if (bottom > 212) bottom = 212;
    g_Rendering = 1;
    if (s_PageValid[page])
    {
        VDP_CommandHMMV(s_PageX[page], (u16)s_PageY[page] + (u16)page * 256,
                        s_PageWidth[page], s_PageHeight[page], 0);
        VDP_CommandWait();
    }
    s_PageValid[page] = 0;
    DrawScenery(page);
    if (right > left && bottom > top)
    {
        width = right - left;
        height = bottom - top;
        VDP_CommandLMMM(shape->atlas_x + left - dx, shape->atlas_y + top - dy,
                        left, (u16)page * 256 + top, width, height, VDP_OP_TIMP);
        VDP_CommandWait();
        s_PageX[page] = left;
        s_PageY[page] = top;
        s_PageWidth[page] = width;
        s_PageHeight[page] = height;
        s_PageValid[page] = 1;
    }
    g_Rendering = 0;
    ++g_RenderCount;
}

void main(void)
{
    u8 input, keys, frame, x, y, page, step, steps, override;
    u8 changed;
    u8 turn_key, turn_was_down = 0;
    u8 scene_keys, scene_was_down = 0, pressed;
    u8 last_tick;
    g_Ready = g_Rendering = g_FramePublished = 0;
    g_RenderCount = g_MissedFrames = 0;
    g_DisplayPage = 0;
    s_PageValid[0] = s_PageValid[1] = 0;
    s_PageScenery[0] = s_PageScenery[1] = 0;
    s_Camera = g_DisplayCamera = 0;
    s_Scenery = s_Paused = s_Reverse = s_ScrollPhase = 0;
    g_DisplayScenery = g_ScrollPaused = g_ScrollReverse = 0;
    override = 0xff;
    Flight_Reset(&s_Flight);
    Aircraft_Reset(&s_Aircraft);
    VDP_SetMode(VDP_MODE_SCREEN5);
    VDP_EnableDisplay(FALSE);
    VDP_SetColor(0);
    VDP_SetPalette(g_HellcatPalette);
    VDP_FillVRAM(0, 0, 0, 0); // Clear pages 0 and 1, not the remaining 64 KiB.
    LoadCaches();
    steps = (g_VDP_REGSAV[9] & 2) ? 6 : 5; // 150 Hz core at 25/30 presentations per second.
    g_DisplayX = 104;
    g_DisplayY = 88;
    g_SelectedFrame = s_Aircraft.shape;
    g_Turning = g_TurnStep = 0;
    g_FacingLeft = 0;
    DrawFrame(s_Aircraft.shape, 104, 88, 0);
    VDP_SetPage(0);
    VDP_EnableDisplay(TRUE);
    WaitVBlank();
    last_tick = g_VBlankTicks;
    g_Ready = 1;
    for (;;)
    {
        input = ReadDirection();
        scene_keys = 0;
        if (IS_KEY_PRESSED(BIOS_GetKeyboardMatrix(KEY_ROW(KEY_S)), KEY_S)) scene_keys |= 1;
        if (IS_KEY_PRESSED(BIOS_GetKeyboardMatrix(KEY_ROW(KEY_P)), KEY_P)) scene_keys |= 2;
        if (IS_KEY_PRESSED(BIOS_GetKeyboardMatrix(KEY_ROW(KEY_R)), KEY_R)) scene_keys |= 4;
        pressed = scene_keys & ~scene_was_down;
        scene_was_down = scene_keys;
        if (pressed & 1) s_Scenery ^= 1;
        if (pressed & 2) s_Paused ^= 1;
        if (pressed & 4) s_Reverse ^= 1;
        if (s_Scenery && !s_Paused)
            for (step = 0; step < steps; ++step)
            {
                s_ScrollPhase += 2;
                if (s_ScrollPhase >= 5)
                {
                    s_ScrollPhase -= 5;
                    s_Camera = (s_Camera + (s_Reverse ? 511 : 1)) & 511;
                }
            }
        turn_key = IS_KEY_PRESSED(BIOS_GetKeyboardMatrix(KEY_ROW(KEY_T)), KEY_T);
        if (turn_key && !turn_was_down && !s_Flight.vx && !s_Flight.vy)
        {
            Aircraft_RequestTurn(&s_Aircraft);
            override = 0xff;
        }
        turn_was_down = turn_key;
        if (BIOS_GetJoystickTrigger(BIOS_TRIGGER_SPACEBAR) || BIOS_GetJoystickTrigger(BIOS_TRIGGER_PORT1_TRIG1))
        {
            Flight_Reset(&s_Flight);
            Aircraft_Reset(&s_Aircraft);
            override = 0xff;
        }
        else
        {
            for (step = 0; step < steps; ++step)
            {
                Flight_Step(&s_Flight, input);
                Aircraft_Step(&s_Aircraft, s_Flight.vx, s_Flight.vy);
            }
            if (input) override = 0xff;
            else
            {
                keys = BIOS_GetKeyboardMatrix(0);
                if (!(keys & 2)) override = 0;
                else if (!(keys & 4)) override = 1;
                else if (!(keys & 8)) override = 2;
            }
        }
        frame = override == 0xff || s_Aircraft.turning ? s_Aircraft.shape : Aircraft_ManualPose(override, s_Aircraft.facing_left);
        x = (s_Flight.x >> 8) & 0xfe; // SCREEN 5 transfers start on a two-pixel byte boundary.
        y = s_Flight.y >> 8;
        changed = x != g_DisplayX || y != g_DisplayY || frame != g_SelectedFrame || s_Aircraft.facing_left != g_FacingLeft;
        changed |= s_Scenery != g_DisplayScenery || (s_Scenery && (s_Camera & 510) != g_DisplayCamera);
        page = g_DisplayPage ^ 1;
        if (changed) DrawFrame(frame, x, y, page);
        if ((u8)(g_VBlankTicks - last_tick) >= 2)
        {
            ++g_MissedFrames;
            WaitVBlank(); // An overrun must still publish inside a fresh VBlank.
        }
        else while ((u8)(g_VBlankTicks - last_tick) < 2) WaitVBlank();
        last_tick = g_VBlankTicks;
        if (changed)
        {
            VDP_SetPage(page);
            g_DisplayPage = page;
            g_DisplayX = x;
            g_DisplayY = y;
            g_SelectedFrame = frame;
            g_FacingLeft = s_Aircraft.facing_left;
            g_DisplayCamera = s_Camera & 510;
            g_DisplayScenery = s_Scenery;
        }
        g_Turning = s_Aircraft.turning;
        g_TurnStep = s_Aircraft.step;
        g_ScrollPaused = s_Paused;
        g_ScrollReverse = s_Reverse;
        g_FramePublished ^= 1;
    }
}
