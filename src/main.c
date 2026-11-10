#include "bios.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "core/flight.h"
#include "generated/hellcat_frames.h"

volatile u8 g_VBlankTicks;

// MSXgl's IM2 ISR acknowledges the VDP and preserves the CPU registers.
void VDP_InterruptHandler(void)
{
    ++g_VBlankTicks;
}

static FlightState s_Flight;
static u8 s_PageX[2], s_PageY[2], s_PageValid[2];

// Published display state is distinct from simulation/back-page state.
volatile u8 g_SelectedFrame, g_DisplayPage, g_DisplayX, g_DisplayY;
volatile u8 g_FacingLeft, g_Rendering, g_Ready, g_FramePublished;
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

static void DrawFrame(u8 frame, u8 left, u8 x, u8 y, u8 page)
{
    u8 row;
    const u8* source = left ? g_HellcatFramesLeft[frame] : g_HellcatFrames[frame];
    u16 address = ((u16)page << 15) + (u16)y * 128 + x / 2;
    g_Rendering = 1;
    if (s_PageValid[page])
    {
        VDP_CommandHMMV(s_PageX[page], (u16)s_PageY[page] + (u16)page * 256, HELLCAT_WIDTH, HELLCAT_HEIGHT, 0);
        VDP_CommandWait();
    }
    for (row = 0; row < HELLCAT_HEIGHT; ++row)
    {
        VDP_WriteVRAM(source, address, 0, HELLCAT_ROW_BYTES);
        source += HELLCAT_ROW_BYTES;
        address += 128;
    }
    s_PageX[page] = x;
    s_PageY[page] = y;
    s_PageValid[page] = 1;
    g_Rendering = 0;
    ++g_RenderCount;
}

void main(void)
{
    u8 input, keys, frame, x, y, page, step, steps, override;
    u8 changed;
    u8 last_tick;
    g_Ready = g_Rendering = g_FramePublished = 0;
    g_RenderCount = g_MissedFrames = 0;
    g_DisplayPage = 0;
    s_PageValid[0] = s_PageValid[1] = 0;
    override = 0xff;
    Flight_Reset(&s_Flight);
    VDP_SetMode(VDP_MODE_SCREEN5);
    VDP_EnableDisplay(FALSE);
    VDP_SetColor(0);
    VDP_SetPalette(g_HellcatPalette);
    VDP_FillVRAM(0, 0, 0, 0); // Clear pages 0 and 1, not the remaining 64 KiB.
    steps = (g_VDP_REGSAV[9] & 2) ? 6 : 5; // 150 Hz core at 25/30 presentations per second.
    g_DisplayX = 104;
    g_DisplayY = 88;
    g_SelectedFrame = 1;
    g_FacingLeft = 0;
    DrawFrame(1, 0, 104, 88, 0);
    VDP_SetPage(0);
    VDP_EnableDisplay(TRUE);
    WaitVBlank();
    last_tick = g_VBlankTicks;
    g_Ready = 1;
    for (;;)
    {
        input = ReadDirection();
        if (BIOS_GetJoystickTrigger(BIOS_TRIGGER_SPACEBAR) || BIOS_GetJoystickTrigger(BIOS_TRIGGER_PORT1_TRIG1))
        {
            Flight_Reset(&s_Flight);
            override = 0xff;
        }
        else
        {
            for (step = 0; step < steps; ++step) Flight_Step(&s_Flight, input);
            if (input) override = 0xff;
            else
            {
                keys = BIOS_GetKeyboardMatrix(0);
                if (!(keys & 2)) override = 0;
                else if (!(keys & 4)) override = 1;
                else if (!(keys & 8)) override = 2;
            }
        }
        frame = override == 0xff ? s_Flight.frame : override;
        x = (s_Flight.x >> 8) & 0xfe; // SCREEN 5 transfers start on a two-pixel byte boundary.
        y = s_Flight.y >> 8;
        changed = x != g_DisplayX || y != g_DisplayY || frame != g_SelectedFrame || s_Flight.facing_left != g_FacingLeft;
        page = g_DisplayPage ^ 1;
        if (changed) DrawFrame(frame, s_Flight.facing_left, x, y, page);
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
            g_FacingLeft = s_Flight.facing_left;
        }
        g_FramePublished ^= 1;
    }
}
