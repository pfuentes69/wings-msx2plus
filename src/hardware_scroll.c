#include "bios.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "keyboard.h"

volatile u8 g_VBlankTicks, g_Ready, g_Rendering, g_FramePublished;
volatile u8 g_Paused, g_Reverse;
volatile u8 g_HoldCamera; // Harness capture hold; independent of the P control.
volatile u16 g_DisplayCamera, g_MissedFrames, g_StreamedColumns;
volatile u16 g_StreamWorld;

void VDP_InterruptHandler(void) { ++g_VBlankTicks; }

static void WaitVBlank(void)
{
    __asm
        halt
    __endasm;
}

// Authored 4096-pixel world, sampled in 8-pixel columns. No source map data.
// Update only outside the currently displayed 256-pixel window.
static void DrawColumn(u16 world)
{
    u16 ring = world & 511;
    u16 x = ring & 255, y = ring < 256 ? 0 : 256;
    u16 block = (world & 4095) >> 3;
    u8 top = 100 + ((block * 13 + (block >> 3) * 7) & 63);
    u8 color = 3 + ((block >> 3) % 12);
    g_StreamWorld = world;
    VDP_CommandHMMV(x, y, 8, top, 0);
    VDP_CommandWait();
    VDP_CommandHMMV(x, y + top, 8, 192 - top, (color << 4) | color);
    VDP_CommandWait();
    VDP_CommandHMMV(x, y + 192, 8, 20, 0xdd);
    VDP_CommandWait();
    // Distant marker makes each 512-pixel region distinguishable.
    VDP_CommandHMMV(x, y + 32 + ((block >> 6) & 7) * 4, 8, 4, 0xbb);
    VDP_CommandWait();
}

void main(void)
{
    static const u8 palette[32] = {
        0,0, 0,0, 0x11,6, 0x33,7, 0x17,1, 0x27,3, 0x51,5, 0x27,6,
        0x71,1, 0x73,3, 0x61,6, 0x66,6, 0x11,7, 0x22,2, 0x44,4, 0x77,7
    };
    u16 camera = 0, next, column;
    u8 tick, keys, held = 0, pressed, step, steps, phase = 0, delta;
    g_Ready = g_Rendering = g_FramePublished = 0;
    g_Paused = g_Reverse = g_HoldCamera = 0;
    g_DisplayCamera = g_MissedFrames = g_StreamedColumns = 0;
    VDP_SetMode(VDP_MODE_SCREEN5);
    VDP_EnableDisplay(FALSE);
    VDP_SetColor(0);
    VDP_SetPalette(palette);
    VDP_FillVRAM(0, 0, 0, 0);
    VDP_FillVRAM(0, 0, 1, 0); // Sentinel region: no runtime commands may touch it.
    for (column = 0; column < 512; column += 8) DrawColumn(column);
    // R#2 bit 5 must be set to expose both halves of the scrolling ring.
    VDP_SetPage(1);
    VDP_SetHorizontalMode(VDP_HSCROLL_DOUBLE);
    VDP_EnableMask(TRUE);
    VDP_SetHorizontalOffset(0);
    VDP_EnableDisplay(TRUE);
    steps = (g_VDP_REGSAV[9] & 2) ? 6 : 5;
    WaitVBlank();
    tick = g_VBlankTicks;
    g_Ready = 1;
    for (;;)
    {
        keys = 0;
        if (IS_KEY_PRESSED(BIOS_GetKeyboardMatrix(KEY_ROW(KEY_P)), KEY_P)) keys |= 1;
        if (IS_KEY_PRESSED(BIOS_GetKeyboardMatrix(KEY_ROW(KEY_R)), KEY_R)) keys |= 2;
        pressed = keys & ~held;
        held = keys;
        if (pressed & 1) g_Paused ^= 1;
        if (pressed & 2) g_Reverse ^= 1;
        delta = 0;
        if (!g_Paused && !g_HoldCamera)
            for (step = 0; step < steps; ++step)
            {
                phase += 3; // 90 px/s with the same 150 Hz core as flight.
                if (phase >= 5) { phase -= 5; ++delta; }
            }
        next = (camera + (g_Reverse ? 4096 - delta : delta)) & 4095;
        g_Rendering = 1;
        if ((next >> 3) != (camera >> 3))
        {
            // Incoming column is outside the currently published viewport.
            column = g_Reverse ? next & 4088
                               : ((next & 4088) + 256) & 4095;
            DrawColumn(column);
            ++g_StreamedColumns;
        }
        g_Rendering = 0;
        if ((u8)(g_VBlankTicks - tick) >= 2)
        {
            ++g_MissedFrames;
            WaitVBlank();
        }
        else while ((u8)(g_VBlankTicks - tick) < 2) WaitVBlank();
        tick = g_VBlankTicks;
        camera = next;
        VDP_SetHorizontalOffset(camera & 511);
        g_DisplayCamera = camera;
        g_FramePublished ^= 1;
    }
}
