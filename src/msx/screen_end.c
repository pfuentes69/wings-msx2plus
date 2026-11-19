#include "screens.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "../generated/screens_art.h"
#include "../generated/terrain.h"
#include "scenery_load.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_SCREEN_END)

#define END_X ((256 - END_PLATE_WIDTH) / 2)
#define END_Y 56

void Screens_DrawEnd(u8 page, u16 camera) WINGS_BANKED
{
    u8 row, x = (u8)camera + END_X, first;
    u16 base = (u16)page * 256;
    const u8* source = g_EndPlate;
    /* Into the page's spare rows as it is, then over the view without its
     * transparent (0) pixels, centred in the view: the page is a ring
     * scrolled by the camera, so the copy splits at its seam. */
    for (row = 0; row < END_PLATE_HEIGHT; ++row, source += END_PLATE_WIDTH / 2)
        VDP_WriteVRAM(source, (base + 212 + row) * 128, 0, END_PLATE_WIDTH / 2);
    first = (u16)x + END_PLATE_WIDTH > 256 ? (u8)(256 - x) : END_PLATE_WIDTH;
    VDP_CommandLMMM(0, base + 212, x, base + END_Y, first, END_PLATE_HEIGHT, VDP_OP_TIMP);
    if (first < END_PLATE_WIDTH)
        VDP_CommandLMMM(first, base + 212, 0, base + END_Y, END_PLATE_WIDTH - first, END_PLATE_HEIGHT, VDP_OP_TIMP);
    VDP_CommandWait();
}


/* The briefing (0x8590), full screen on black: rank.iff's frame (from
 * banks 51..) at row 58, and the values printed into it in newarmyfont
 * where the original prints them (296, 61), (340, 73), (340, 119),
 * (340, 131) on rank.iff, the frame there at (198, 54). */
#define BRIEF_Y 58
static const char* const s_BriefRanks[7] = {
    "Midshipman", "Ensign", "Lt. Jr. Gr.", "Lieutenant", "Lt.Commd", "Commander", "Captain"};
static u8 s_Row[128];
static char s_Values[4][12];
static const u8 s_ValueX[4] = {98, 142, 142, 142};
static const u8 s_ValueY[4] = {7, 19, 65, 77};

static void Number(char* out, u8 value)
{
    if (value >= 10) *out++ = '0' + value / 10;
    *out++ = '0' + value % 10;
    *out = 0;
}

/* Row r of a value's glyphs into s_Row (ink BRIEF_INK on the frame's black). */
static void Glyphs(const char* text, u8 x, u8 r)
{
    u8 k, i, width, stride;
    const u8* bits;
    for (; *text; ++text)
    {
        for (k = 0; k < BRIEF_FONT_COUNT && g_BriefFontChars[k] != *text; ++k) {}
        if (k == BRIEF_FONT_COUNT) continue;
        width = g_BriefFontWidth[k];
        stride = (width + 7) >> 3;
        bits = g_BriefFontBits + g_BriefFontOffset[k] + (u16)r * stride;
        for (i = 0; i < width; ++i, ++x)
            if (bits[i >> 3] & (0x80 >> (i & 7)))
                s_Row[x >> 1] |= x & 1 ? BRIEF_INK : BRIEF_INK << 4;
    }
}

void Screens_Briefing(u8 page, const GameState* game) WINGS_BANKED
{
    u8 row, v;
    u16 offset = 0, base = (u16)page * 256;
    const char* rank = s_BriefRanks[game->progress.rank < 7 ? game->progress.rank : 6];
    for (v = 0; rank[v]; ++v) s_Values[0][v] = rank[v];
    s_Values[0][v] = 0;
    Number(s_Values[1], game->mission.number);
    Number(s_Values[2], g_BriefIslands);
    Number(s_Values[3], g_BriefShips);
    VDP_CommandHMMV(0, base, 256, 212, 0);    /* black, the dashboard's rows too */
    VDP_CommandWait();
    for (row = 0; row < BRIEF_FRAME_HEIGHT; ++row, offset += 128)
    {
        Scenery_Read(BRIEF_BANK + (offset >> 13), offset & 8191, s_Row, 128);
        for (v = 0; v < 4; ++v)
            if ((u8)(row - s_ValueY[v]) < BRIEF_FONT_HEIGHT) Glyphs(s_Values[v], s_ValueX[v], row - s_ValueY[v]);
        VDP_WriteVRAM(s_Row, (base + BRIEF_Y + row) * 128, 0, 128);
    }
}

/* The play area's palette for the briefing (1), or back (0); colour 0 (the
 * sky, black here) is set directly: the line interrupt leaves it alone. */
extern u8 g_TopPalette[32];
void Screens_BriefingColours(u8 on) WINGS_BANKED
{
    u8 i;
    const u8* colours = on ? g_BriefPalette : g_TerrainPalette;
    for (i = 2; i < 32; ++i) g_TopPalette[i] = colours[i];
    VDP_SetPaletteEntry(0, colours[0] | ((u16)colours[1] << 8));
}
