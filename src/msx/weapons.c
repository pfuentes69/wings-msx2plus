#include "weapons.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_HUD)
#include "dashboard.h"
#include "vdp.h"
#include "vdp_inl.h"

typedef struct Footprint { u8 x, y, width, height; } Footprint;
static Footprint s_Old[2][COMBAT_COUNT];
static u16 s_Camera;
static u8 s_Page, s_BombPose, s_Count[2];

void Weapons_Init(void) WINGS_BANKED
{
    u8 page, i;
    s_Count[0]=s_Count[1]=0;
    for (page = 0; page < 2; ++page)
        for (i = 0; i < COMBAT_COUNT; ++i) s_Old[page][i].width = 0;
}

static void Backup(u8 page, u8 index, u8 save)
{
    Footprint* f = &s_Old[page][index];
    u16 x = f->x, bx = g_WeaponBackupX[page*COMBAT_COUNT+index];
    u8 width = f->width, part;
    while (width)
    {
        part = width;
        if (x + part > 256) part = 256-x;
        if (save)
            VDP_CommandHMMM(x, (u16)page*256+f->y, bx,
                            g_WeaponBackupY[page*COMBAT_COUNT+index], part, f->height);
        else
            VDP_CommandHMMM(bx, g_WeaponBackupY[page*COMBAT_COUNT+index], x,
                            (u16)page*256+f->y, part, f->height);
        width -= part; bx += part; x = 0;
    }
}

void Weapons_Restore(u8 page, u8 cleared) WINGS_BANKED
{
    u8 i = s_Count[page];
    // Later backups can contain earlier effects: unwind in reverse draw order.
    while (i--)
    {
        if (s_Old[page][i].width && !cleared) Backup(page, i, 0);
        s_Old[page][i].width = 0;
    }
}

static void Mark(i16 x, i16 y, u8 width, u8 height, u8 color)
{
    i16 right = x+width, bottom = y+height, ox=x, oy=y;
    u16 ring, part;
    if (x < (i16)(s_Camera+8)) x = s_Camera+8;
    if (right > (i16)(s_Camera+256)) right = s_Camera+256;
    if (y < 0) y = 0;
    if (bottom > 171) bottom = 171;
    if (right <= x || bottom <= y) return;
    width = right-x; height = bottom-y; ring = x & 255;
    while (width)
    {
        part = width; if (ring+part > 256) part = 256-ring;
        if (color) VDP_CommandLMMV(ring, (u16)s_Page*256+y, part, height, color, VDP_OP_IMP);
        else VDP_CommandLMMM(g_BombX[s_BombPose]+x-ox, g_BombY[s_BombPose]+y-oy,
                            ring, (u16)s_Page*256+y, part, height, VDP_OP_TIMP);
        width -= part; x += part; ring = 0;
    }
}

void Weapons_Draw(u8 page, u16 camera, u8 far, u8 heave, const CombatState* state) WINGS_BANKED
{
    u8 i, kind;
    i16 x, y, left, right, top, bottom;
    Footprint* f;
    const CombatProjectile* p;
    s_Camera = camera; s_Page = page; s_Count[page]=state->count;
    for (i = 0; i < state->count; ++i)
    {
        p = &state->projectile[i]; kind = p->kind;
        if (!kind) continue;
        x = p->x >> 2;
        y = p->y >> 2;
        if (far) { x >>= 3; y = 161-((1200-y)>>3); }
        else y = y-1039-heave;
        // Back up only the affected pixels (plus byte alignment). Small
        // rounds must not pay for a full impact cross on every page restore.
        if (far) { left=x&~1; right=left+2; top=y; bottom=y+(kind>=COMBAT_IMPACT ? 2 : 1); }
        else if (kind==COMBAT_FALLING_BOMB) { left=(x-3)&~1; right=left+8; top=y-3; bottom=y+3; }
        else { left=(x-3)&~1; right=left+8; top=y-3; bottom=y+4; }
        if (left < (i16)((camera+8)&65534u)) left = (camera+8)&65534u;
        if (right > (i16)((camera+257)&65534u)) right = (camera+257)&65534u;
        if (top < 0) top = 0;
        if (bottom > 171) bottom = 171;
        if (right <= left || bottom <= top) continue;
        f = &s_Old[page][i];
        f->x = left & 255; f->y = top;
        f->width = right-left; f->height = bottom-top;
        Backup(page, i, 1);
        if (far) Mark(x, y, 1, kind >= COMBAT_IMPACT ? 2 : 1, 11);
        else if (kind == COMBAT_FALLING_BOMB)
        {
            // Two discrete rotations after release: horizontal, diagonal, down.
            s_BombPose = p->life > 95 ? 0 : p->life > 92 ? 1 : 2;
            if (s_BombPose != 2 && p->vx > 0) s_BombPose += 3;
            Mark(x-4, y-4, 8, 8, 0);
        }
        else
        {
            Mark(x-3, y, 7, 1, kind == COMBAT_SPLASH ? 5 : 14);
            Mark(x, y-3, 1, 7, kind == COMBAT_SPLASH ? 5 : 14);
            Mark(x-1, y-1, 3, 3, 11);
        }
    }
}

u8 Weapons_PendingRestore(void) WINGS_BANKED
{
    return s_Count[0]>COMBAT_GUN_COUNT || s_Count[1]>COMBAT_GUN_COUNT;
}
