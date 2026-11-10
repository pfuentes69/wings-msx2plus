#include "bios.h"
#include "vdp.h"
#include "generated/hellcat_frames.h"

#define PLANE_X 104
#define PLANE_Y 88

// These symbols also make input/page timing observable in openMSX.
volatile u8 g_SelectedFrame;
volatile u8 g_DisplayPage;
volatile u8 g_Rendering;
volatile u16 g_RenderCount;

static void WaitVBlank(void)
{
    __asm
        halt
    __endasm;
}

static void DrawLabels(u8 page)
{
    static const u8 digits[3][5] = {
        { 2, 6, 2, 2, 7 }, { 7, 1, 7, 4, 7 }, { 7, 1, 7, 1, 7 }
    };
    u8 digit, row, bit;
    for (digit = 0; digit < 3; ++digit)
        for (row = 0; row < 5; ++row)
            for (bit = 0; bit < 3; ++bit)
            {
                u8 color = (digits[digit][row] & (4 >> bit)) ? 0xee : 0;
                u16 address = ((u16)page << 15) + (144 + row * 2) * 128 + 45 + digit * 16 + bit;
                VDP_Poke(color, address, 0);
                VDP_Poke(color, address + 128, 0);
            }
}

static void DrawFrame(u8 frame, u8 page)
{
    u8 row, digit;
    const u8* source = g_HellcatFrames[frame];
    u16 address = ((u16)page << 15) + PLANE_Y * 128 + PLANE_X / 2;
    g_Rendering = 1;
    for (row = 0; row < HELLCAT_HEIGHT; ++row)
    {
        VDP_WriteVRAM(source, address, 0, HELLCAT_ROW_BYTES);
        source += HELLCAT_ROW_BYTES;
        address += 128;
    }
    // Erase the previous page's selection and draw the current underline.
    for (digit = 0; digit < 3; ++digit)
        VDP_FillVRAM(digit == frame ? 0xcc : 0, ((u16)page << 15) + 160 * 128 + 43 + digit * 16, 0, 7);
    g_Rendering = 0;
    ++g_RenderCount;
}

void main(void)
{
    u8 selected, keys, page;
    g_SelectedFrame = 0;
    g_DisplayPage = 0;
    g_Rendering = 0;
    g_RenderCount = 0;
    VDP_SetMode(VDP_MODE_SCREEN5);
    VDP_EnableDisplay(FALSE);
    VDP_SetColor(0);
    VDP_SetPalette(g_HellcatPalette);
    // Two 32 KiB SCREEN 5 pages; the other 64 KiB VRAM stays unused.
    VDP_FillVRAM(0, 0, 0, 0);
    DrawLabels(0);
    DrawLabels(1);
    DrawFrame(0, 0);
    VDP_SetPage(0);
    VDP_EnableDisplay(TRUE);
    for (;;)
    {
        WaitVBlank();
        keys = BIOS_GetKeyboardMatrix(0);
        selected = g_SelectedFrame;
        if (!(keys & 0x02)) selected = 0; // 1
        else if (!(keys & 0x04)) selected = 1; // 2
        else if (!(keys & 0x08)) selected = 2; // 3
        if (selected != g_SelectedFrame)
        {
            page = g_DisplayPage ^ 1;
            DrawFrame(selected, page);
            // Publish a complete frame only at the following VBlank.
            WaitVBlank();
            VDP_SetPage(page);
            g_DisplayPage = page;
            g_SelectedFrame = selected;
        }
    }
}
