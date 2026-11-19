#include "screens.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "../generated/screens_art.h"
#include "../generated/terrain.h"
#include "scenery_load.h"
#include "dashboard.h"
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
    /* Full screen, unscrolled: all 256 columns show (the play view masks
     * the left 8, which its scroll exposes). */
    VDP_EnableMask(!on);
}

/* Rank selection (shapes/selectrank, recomposed to 256 wide: banks 53..)
 * full screen at row 6, and the chosen rank's line highlighted (the
 * original's blue band, selectrank.shp rnk0..rnk6: bank 57). */
#define RANK_TOP 6
static u8 s_RankLine;
static void RankLine(u16 base, u8 line, u8 highlighted)
{
    u8 row, y = RANK_LINE_Y + line * RANK_LINE_STEP;
    u16 offset;
    for (row = 0; row < RANK_LINE_HEIGHT; ++row, ++y)
    {
        if (highlighted)
            Scenery_Read(RANK_LINE_BANK, ((u16)line * RANK_LINE_HEIGHT + row) * RANK_LINE_BYTES, s_Row, RANK_LINE_BYTES);
        else
        {
            offset = (u16)y * 128 + RANK_LINE_X / 2;
            Scenery_Read(RANK_BANK + (offset >> 13), offset & 8191, s_Row, RANK_LINE_BYTES);
        }
        VDP_WriteVRAM(s_Row, (base + RANK_TOP + y) * 128 + RANK_LINE_X / 2, 0, RANK_LINE_BYTES);
    }
}

void Screens_Rank(u8 page, u8 line) WINGS_BANKED
{
    u8 row;
    u16 offset = 0, base = (u16)page * 256;
    VDP_CommandHMMV(0, base, 256, 212, 0);
    VDP_CommandWait();
    for (row = 0; row < 200; ++row, offset += 128)
    {
        Scenery_Read(RANK_BANK + (offset >> 13), offset & 8191, s_Row, 128);
        VDP_WriteVRAM(s_Row, (base + RANK_TOP + row) * 128, 0, 128);
    }
    RankLine(base, line, 1);
    s_RankLine = line;
}

void Screens_RankLine(u8 page, u8 line) WINGS_BANKED
{
    u16 base = (u16)page * 256;
    if (line == s_RankLine) return;
    RankLine(base, s_RankLine, 0);
    RankLine(base, line, 1);
    s_RankLine = line;
}

/* Its palette over the whole screen (1: the dashboard's rows too), or the
 * play's and the dashboard's back (0). */
extern u8 g_BottomPalette[32];
void Screens_RankColours(u8 on) WINGS_BANKED
{
    u8 i;
    if (!on) { Dashboard_CopyPalette(g_BottomPalette); Screens_BriefingColours(0); return; }
    for (i = 2; i < 32; ++i) g_TopPalette[i] = g_BottomPalette[i] = g_RankPalette[i];
    VDP_SetPaletteEntry(0, g_RankPalette[0] | ((u16)g_RankPalette[1] << 8));
    VDP_EnableMask(FALSE);   /* all 256 columns, as for the briefing */
}
