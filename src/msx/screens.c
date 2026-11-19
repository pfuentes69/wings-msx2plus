#include "screens.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "../generated/screens_art.h"
#include "../generated/terrain.h"
#include "dashboard.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_SCREENS)

/* The panel's place in the view: the original's right margin (32 of 320
 * px) as 24 of 256, 20 rows down. */
#define PANEL_X 136
#define PANEL_Y 20
#define PANEL_BYTES (WEAPON_PANEL_WIDTH / 2)
static u8 s_PanelRing;   /* ring x of its left edge (even: whole bytes) */
static u16 s_PanelBase;  /* its page's first row */

/* Rows of the panel's packed pixels at ring x s_PanelRing, split at the
 * ring's seam. */
static void Rows(const u8* source, u8 row, u8 count)
{
    u16 first = 256 - s_PanelRing;
    u16 address = (s_PanelBase + PANEL_Y + row) * 128;
    first = first >= WEAPON_PANEL_WIDTH ? PANEL_BYTES : first / 2;
    for (; count; --count, source += PANEL_BYTES, address += 128)
    {
        VDP_WriteVRAM(source, address + s_PanelRing / 2, 0, (u8)first);
        if (first < PANEL_BYTES) VDP_WriteVRAM(source + first, address, 0, PANEL_BYTES - (u8)first);
    }
}

static void Line(u8 line, u8 highlighted)
{
    u8 row = g_WeaponLineRow[line];
    Rows(highlighted ? g_WeaponLines + g_WeaponLineOffset[line] : g_WeaponPanel + (u16)row * PANEL_BYTES,
         row, g_WeaponLineHeight[line]);
}

void Screens_WeaponPanel(u8 page, u16 camera, u8 line) WINGS_BANKED
{
    s_PanelRing = (u8)(camera + PANEL_X) & 254;
    s_PanelBase = (u16)page * 256;
    Rows(g_WeaponPanel, 0, WEAPON_PANEL_HEIGHT);
    Line(line, 1);
}

void Screens_WeaponLine(u8 page, u8 from, u8 to) WINGS_BANKED
{
    s_PanelBase = (u16)page * 256;
    /* The lines share a row with their neighbours: the old one first. */
    Line(from, 0);
    Line(to, 1);
}

/* Weapon selection on this page (the view already behind it): the whole
 * panel the first time, else the highlight moved; and the dashboard's
 * weapon and stock. */
static u8 s_Line;
void Screens_Weapons(u8 page, u16 camera, u8 first, const GameState* game) WINGS_BANKED
{
    u8 line = GAME_WEAPON_LINE(game->cursor);
    if (first) Screens_WeaponPanel(page, camera, line);
    else Screens_WeaponLine(page, s_Line, line);
    s_Line = line;
    Dashboard_Status(page, game->sortie.weapon, game->sortie.stock, game->progress.lives);
    VDP_CommandWait();
}
