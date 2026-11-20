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


/* The briefing (the original's 0x8590 shows rank.iff's frame with the
 * rank, the mission, and the mission's islands and ships): the port's own
 * compact panel, centred on black, in the original's layout and colours
 * (blue labels, the red heading, light grey values on black compartments in
 * a grey frame) with the menu's small letters. */
#define BRIEF_X 48      /* even: the fills and the letters are whole bytes */
#define BRIEF_Y 64
#define BRIEF_W 160
#define BRIEF_H 85
#define BRIEF_LABEL (BRIEF_X + 12)
#define BRIEF_VALUE (BRIEF_X + 68)
#define BRIEF_RED 1
#define BRIEF_BLUE 2
static const char* const s_BriefRanks[7] = {
    "MIDSHIPMAN", "ENSIGN", "LT. JR. GR.", "LIEUTENANT", "LT. COMMANDER", "COMMANDER", "CAPTAIN"};
static u8 s_Row[128];
static char s_Number[4];

static const char* Number(u8 value)
{
    char* out = s_Number;
    if (value >= 100) { *out++ = '0' + value / 100; value %= 100; *out++ = '0' + value / 10; }
    else if (value >= 10) *out++ = '0' + value / 10;
    *out++ = '0' + value % 10;
    *out = 0;
    return s_Number;
}

/* The small font's glyph for a character (lower case as upper; unknown: a
 * space). */
static u8 Glyph(u8 c)
{
    const char* extra = SMALL_FONT_EXTRA;
    u8 k;
    if (c >= 'a' && c <= 'z') c -= 32;
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= '0' && c <= '9') return c - '0' + 26;
    if (c == '.') return 38;
    if (c == ':') return 39;
    for (k = 0; extra[k]; ++k) if (extra[k] == c) return 40 + k;
    return 37;
}

/* Text in the small font (6 px a character) at even x, this ink on black. */
static void Text(u16 base, u8 x, u8 y, const char* text, u8 ink)
{
    u8 row, i, k, c, bits, length = 0;
    u8* out;
    while (text[length]) ++length;
    for (row = 0; row < 7; ++row)
    {
        out = s_Row;
        for (i = 0; i < length; ++i)
        {
            c = Glyph(text[i]);
            bits = g_SmallFont[c * 7 + row];
            for (k = 0; k < 3; ++k, bits <<= 2)
                *out++ = (bits & 0x80 ? ink << 4 : 0) | (bits & 0x40 ? ink : 0);
        }
        VDP_WriteVRAM(s_Row, (base + y + row) * 128 + x / 2, 0, length * 3);
    }
}

static void Fill(u16 base, u8 x, u8 y, u16 width, u8 height, u8 colour)
{
    VDP_CommandHMMV(x, base + y, width, height, colour * 0x11);
    VDP_CommandWait();
}

/* A black compartment set into the frame (a dark line above, a light one
 * below), its top at y. */
static void Compartment(u16 base, u8 y, u8 height)
{
    Fill(base, BRIEF_X + 4, y - 1, BRIEF_W - 8, 1, 3);
    Fill(base, BRIEF_X + 4, y + height, BRIEF_W - 8, 1, 6);
    Fill(base, BRIEF_X + 4, y, BRIEF_W - 8, height, 0);
}

void Screens_Briefing(u8 page, const GameState* game) WINGS_BANKED
{
    u16 base = (u16)page * 256;
    Fill(base, 0, 0, 256, 212, 0);    /* black, the dashboard's rows too */
    /* The frame: mid grey, lit top and left, shadowed bottom and right. */
    Fill(base, BRIEF_X, BRIEF_Y, BRIEF_W, BRIEF_H, 5);
    Fill(base, BRIEF_X, BRIEF_Y, BRIEF_W, 1, 7);
    Fill(base, BRIEF_X, BRIEF_Y, 2, BRIEF_H, 6);
    Fill(base, BRIEF_X, BRIEF_Y + BRIEF_H - 1, BRIEF_W, 1, 3);
    Fill(base, BRIEF_X + BRIEF_W - 2, BRIEF_Y + 1, 2, BRIEF_H - 1, 3);
    Compartment(base, BRIEF_Y + 4, 26);
    Compartment(base, BRIEF_Y + 34, 17);
    Compartment(base, BRIEF_Y + 55, 26);
    Text(base, BRIEF_LABEL, BRIEF_Y + 9, "RANK:", BRIEF_BLUE);
    Text(base, BRIEF_VALUE, BRIEF_Y + 9, s_BriefRanks[game->progress.rank < 7 ? game->progress.rank : 6], BRIEF_INK);
    Text(base, BRIEF_LABEL, BRIEF_Y + 19, "MISSION:", BRIEF_BLUE);
    Text(base, BRIEF_VALUE, BRIEF_Y + 19, Number(game->mission.number), BRIEF_INK);
    Text(base, BRIEF_X + 24, BRIEF_Y + 39, "MISSION OBJECTIVES:", BRIEF_RED);
    Text(base, BRIEF_LABEL, BRIEF_Y + 60, "ISLANDS:", BRIEF_BLUE);
    Text(base, BRIEF_VALUE, BRIEF_Y + 60, Number(g_BriefIslands), BRIEF_INK);
    Text(base, BRIEF_LABEL, BRIEF_Y + 70, "SHIPS:", BRIEF_BLUE);
    Text(base, BRIEF_VALUE, BRIEF_Y + 70, Number(g_BriefShips), BRIEF_INK);
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
    /* After "THE END": its plate was staged over the wave frames. */
    Dashboard_LoadWaves();
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

/* The intro (docs/intro.md): screen 0 the title (wingstitle, banks 59..),
 * 1 the credits, 2.. the story's pages, full screen on black. */
typedef char IntroScreens[(STORY_PAGES + 2 == GAME_INTRO_SCREENS) ? 1 : -1];
static char s_Line[STORY_LINE + 1];
static void Piece(u16 base, u8 i)
{
    u8 row;
    u16 offset = g_IntroPieceOffset[i];
    for (row = 0; row < g_IntroPieceHeight[i]; ++row, offset += g_IntroPieceBytes[i])
    {
        Scenery_Read(g_IntroPieceBank[i], offset, s_Row, g_IntroPieceBytes[i]);
        VDP_WriteVRAM(s_Row, (base + g_IntroPieceY[i] + row) * 128 + g_IntroPieceX[i] / 2, 0, g_IntroPieceBytes[i]);
    }
}
static void Centred(u16 base, u8 y, const char* text)
{
    u8 length = 0;
    while (text[length]) ++length;
    Text(base, (u8)((256 - 6 * length) / 2) & 0xfe, y, text, INTRO_TEXT);
}

void Screens_Intro(u8 page, u8 screen) WINGS_BANKED
{
    u8 row, i;
    u16 offset = 0, base = (u16)page * 256;
    Fill(base, 0, 0, 256, 212, 0);
    if (screen == GAME_INTRO_TITLE)
    {
        for (row = 0; row < 200; ++row, offset += 128)
        {
            Scenery_Read(TITLE_BANK + (offset >> 13), offset & 8191, s_Row, 128);
            VDP_WriteVRAM(s_Row, (base + TITLE_TOP + row) * 128, 0, 128);
        }
        return;
    }
    if (screen == GAME_INTRO_CREDITS)
    {
        Centred(base, 8, "ADAPTED FROM THE AMIGA VERSION");
        for (i = 0; i < INTRO_PIECE_HEADING; ++i) Piece(base, i);
        Centred(base, 200, "PORTED BY PFUENTES69 (& CLAUDE)");
        return;
    }
    screen -= GAME_INTRO_STORY;
    if (!screen) Piece(base, INTRO_PIECE_HEADING);
    offset = STORY_OFFSET + (u16)g_StoryPageFirst[screen] * STORY_LINE;
    for (i = 0; i < g_StoryPageCount[screen]; ++i, offset += STORY_LINE)
    {
        Scenery_Read(STORY_BANK, offset, (u8*)s_Line, STORY_LINE);
        s_Line[STORY_LINE] = 0;
        Text(base, (256 - 6 * STORY_COLUMNS) / 2, g_StoryPageTop[screen] + 9 * i, s_Line, INTRO_TEXT);
    }
}

/* At boot (docs/intro.md): the title on page 0 shown at once, its rows
 * 212.. cleared; then the rest of VRAM cleared behind it (the screen mode
 * is set, the display off). */
void Screens_BootTitle(void) WINGS_BANKED
{
    VDP_FillVRAM(0, 212 * 128, 0, 44 * 128);
    Screens_Intro(0, GAME_INTRO_TITLE);
    Screens_Palette(SCREENS_TITLE);
    VDP_SetPage(0);
    /* No scroll from the first field: the V-blank handler then keeps it at
     * g_ScrollFine/g_ScrollCoarse, which boot zeroes (the user, 2026-11-20:
     * the title showed displaced, then moved). */
    VDP_SetVerticalOffset(0);
    VDP_SetHorizontalOffset(0);
    VDP_EnableDisplay(TRUE);
    VDP_FillVRAM(0, 0x8000, 0, 0x8000);
    VDP_FillVRAM(0, 0, 1, 0);
}

extern u8 g_TopPalette[32], g_BottomPalette[32];   /* world_flight.c */
static void Load(const u8* colours) __naked
{
    colours;   /* HL: all 16 entries (0 too), interrupts off throughout */
    __asm
        di
        xor a
        out (0x99), a
        ld a, #0x90
        out (0x99), a
        ld bc, #0x209a
        otir
        ei
        ret
    __endasm;
}

void Screens_Palette(u8 which) WINGS_BANKED
{
    u8 i;
    const u8* top = which == SCREENS_BRIEF ? g_BriefPalette : which == SCREENS_RANK ? g_RankPalette :
                    which == SCREENS_TITLE ? g_TitlePalette : which == SCREENS_INTRO ? g_IntroPalette : g_TerrainPalette;
    for (i = 0; i < 32; ++i) g_TopPalette[i] = top[i];
    if (which == SCREENS_WEAPON)
        for (i = 0; i < 8; ++i) g_TopPalette[24 + i] = g_WeaponColours[i];
    if (which >= SCREENS_RANK)   /* the whole screen's */
        for (i = 0; i < 32; ++i) g_BottomPalette[i] = top[i];
    else Dashboard_CopyPalette(g_BottomPalette);
    Load(g_TopPalette);
    VDP_EnableMask(which < SCREENS_BRIEF);
    /* The border is colour 1: the play's dark sea, the same in the play's and
     * the dashboard's palettes. The full-screen ones give colour 1 other
     * uses (the briefing's red): their border is colour 0, black there. */
    VDP_SetColor(which < SCREENS_BRIEF ? 1 : 0);
}
