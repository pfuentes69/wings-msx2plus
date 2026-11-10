#include "bios.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "keyboard.h"
#include "core/flight.h"
#include "core/aircraft.h"
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

// Published display state is distinct from simulation/back-page state.
volatile u8 g_SelectedFrame, g_DisplayPage, g_DisplayX, g_DisplayY;
volatile u8 g_FacingLeft, g_Rendering, g_Ready, g_FramePublished;
volatile u8 g_Turning, g_TurnStep;
volatile u16 g_RenderCount, g_MissedFrames;

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
    const u8* source;
    int16_t dx = (int16_t)x + shape->dx, dy = (int16_t)y + shape->dy;
    int16_t left = dx < 0 ? 0 : dx, top = dy < 0 ? 0 : dy;
    int16_t right = dx + shape->width, bottom = dy + shape->height;
    u8 row, width, height, stride = shape->width / 2;
    u16 address;
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
    if (right > left && bottom > top)
    {
        width = right - left;
        height = bottom - top;
        source = shape->data + (top - dy) * stride + (left - dx) / 2;
        address = ((u16)page << 15) + (u16)top * 128 + left / 2;
        for (row = 0; row < height; ++row)
        {
            VDP_WriteVRAM(source, address, 0, width / 2);
            source += stride;
            address += 128;
        }
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
    u8 last_tick;
    g_Ready = g_Rendering = g_FramePublished = 0;
    g_RenderCount = g_MissedFrames = 0;
    g_DisplayPage = 0;
    s_PageValid[0] = s_PageValid[1] = 0;
    override = 0xff;
    Flight_Reset(&s_Flight);
    Aircraft_Reset(&s_Aircraft);
    VDP_SetMode(VDP_MODE_SCREEN5);
    VDP_EnableDisplay(FALSE);
    VDP_SetColor(0);
    VDP_SetPalette(g_HellcatPalette);
    VDP_FillVRAM(0, 0, 0, 0); // Clear pages 0 and 1, not the remaining 64 KiB.
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
        page = g_DisplayPage ^ 1;
        if (changed) DrawFrame(frame, x, y, page);
        while ((u8)(g_VBlankTicks - last_tick) < 2) WaitVBlank();
        if ((u8)(g_VBlankTicks - last_tick) > 2) ++g_MissedFrames;
        last_tick = g_VBlankTicks;
        if (changed)
        {
            VDP_SetPage(page);
            g_DisplayPage = page;
            g_DisplayX = x;
            g_DisplayY = y;
            g_SelectedFrame = frame;
            g_FacingLeft = s_Aircraft.facing_left;
        }
        g_Turning = s_Aircraft.turning;
        g_TurnStep = s_Aircraft.step;
        g_FramePublished ^= 1;
    }
}
