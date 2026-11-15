#include "message.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_MISSION)
#include "vdp.h"
#include "vdp_inl.h"
#include "../core/island.h"
#include "../generated/font.h"

#ifdef WINGS_P1_FLIGHT
u8 g_MessageActive, g_MessageWait;
u16 g_MessageScroll[2];
static char s_Text[MESSAGE_TEXT_MAX + 1];
static u16 s_Offset;        /* the text pixel at the band's right edge */
static u16 s_TextEnd;       /* the text's width in pixels, once drawn to its end (else 0xFFFF) */
static u8 s_Stale;          /* a new text started over a running one: blank the rings */
/* Per page: text pixels written (even), and the character holding the
 * next one with its first pixel. */
static u16 s_Drawn[2], s_CharStart[2];
static u8 s_Next[2];

/* Both texts and the bonus fit (no bounds checks in the copies). */
typedef char TextFits[sizeof(g_MessageCleared) + sizeof(g_MessageMission) + 5 <= MESSAGE_TEXT_MAX ? 1 : -1];

/* The island's message (0x3f6e) with the executable's sprintf for its one
 * %ld, the bonus; the mission's last island (0x5694) appends "Good work
 * ..." over the final full stop. Digits by subtraction: SDCC divides
 * through a slow call. */
static void Compose(u16 value, u8 mission)
{
    static const u16 power[5] = {10000, 1000, 100, 10, 1};
    const char* text = g_MessageCleared;
    char* out = s_Text;
    char c;
    u8 n, digit, started = 0;
    while ((c = *text++) != '%') *out++ = c;
    text += 2;   /* "ld" */
    for (n = 0; n < 5; ++n)
    {
        digit = '0';
        while (value >= power[n]) { value -= power[n]; ++digit; }
        if (digit != '0' || started || n == 4) { *out++ = digit; started = 1; }
    }
    while ((*out++ = *text++)) {}
    --out;
    if (mission)
    {
        text = g_MessageMission;
        --out;
        while ((*out++ = *text++)) {}
    }
}

static u8 Glyph(char c)
{
    return c < FONT_FIRST || c > FONT_LAST ? 0 : (u8)(c - FONT_FIRST);
}

void Message_Update(u8 vblanks) WINGS_BANKED
{
    if (g_Island.message)
    {
        /* Not while the pages redraw the score for the bonus (the frame the
         * island is cleared and the next): the ticker starts after them. */
        if (!g_MessageWait) g_MessageWait = 3;
        if (--g_MessageWait) return;
        Compose(g_Island.bonus, g_Island.message == ISLAND_MESSAGE_MISSION);
        g_Island.message = ISLAND_MESSAGE_NONE;
        s_TextEnd = 0xFFFF;   /* Message_Draw finds it */
        /* A ticker still running restarts: blank both bands first. */
        s_Stale = g_MessageActive;
        s_Offset = 0;
        s_Drawn[0] = s_Drawn[1] = 0xFFFF;
        g_MessageActive = 1;
        return;
    }
    if (!g_MessageActive) return;
    /* Never far ahead of the text written: with no time to spare the
     * ticker slows down rather than jumping. */
    s_Offset += (u16)vblanks << 1;
    {
        u16 a = s_Drawn[0] == 0xFFFF ? 0 : s_Drawn[0], b = s_Drawn[1] == 0xFFFF ? 0 : s_Drawn[1];
        if (b > a) a = b;
        if (s_Offset > a + 8) s_Offset = a + 8;
    }
}

/* CellRows' arguments: the VRAM address of the cell's first row (rows
 * follow every 128 bytes), the glyph's 1-bit rows (0: blank) and their
 * stride, the first pixel pair and the bytes (pixel pairs) to write. */
static u16 s_CellAddr;
static const u8* s_CellBits;
static u8 s_CellStride, s_CellSkip, s_CellBytes, s_CellRow;
typedef char FontInk[FONT_INK == 11 && FONT_HEIGHT == 12 ? 1 : -1];   /* CellRows' constants */

/* The cell's 12 rows straight to the VDP: each pixel pair (two bits, left
 * first) becomes a byte, ink 11 on the sky (0). ~100 T-states a byte; in
 * SDCC's C a byte cost several hundred. The cell never crosses the end of
 * the band's 256-px ring (Message_Draw splits it). */
static void CellRows(void) __naked
{
    __asm
        ld a, #12
        ld (_s_CellRow), a
    cell_row$:
        // VRAM address: R14 = bits 14..16, then the low 14 bits for writing
        ld hl, (_s_CellAddr)
        ld a, h
        rlca
        rlca
        and #3
        di
        out (0x99), a
        ld a, #0x8e
        out (0x99), a
        ld a, l
        out (0x99), a
        ld a, h
        and #0x3f
        or #0x40
        ei
        out (0x99), a
        ld de, #128
        add hl, de
        ld (_s_CellAddr), hl
        ld a, (_s_CellBytes)
        ld b, a
        ld hl, (_s_CellBits)
        ld a, h
        or l
        jr nz, cell_glyph$
    cell_blank$:
        out (0x98), a
        djnz cell_blank$
        jr cell_next$
    cell_glyph$:
        // DE: the byte holding the first pair; C: it, that pair on top;
        // H: the output bytes left in it
        ld a, (_s_CellSkip)
        ld c, a
        rrca
        rrca
        and #0x3f
        ld e, a
        ld d, #0
        add hl, de
        ex de, hl
        ld a, c
        and #3
        ld l, a
        ld a, #4
        sub l
        ld h, a
        ld a, (de)
        inc de
        ld c, a
        inc l
        jr cell_skip_test$
    cell_skip$:
        rl c
        rl c
    cell_skip_test$:
        dec l
        jr nz, cell_skip$
    cell_pair$:
        rl c
        sbc a, a
        and #0xb0
        ld l, a
        rl c
        sbc a, a
        and #0x0b
        or l
        out (0x98), a
        dec h
        jr nz, cell_same$
        ld a, (de)
        inc de
        ld c, a
        ld h, #4
    cell_same$:
        djnz cell_pair$
        ld hl, (_s_CellBits)
        ld a, (_s_CellStride)
        ld e, a
        ld d, #0
        add hl, de
        ld (_s_CellBits), hl
    cell_next$:
        ld hl, #_s_CellRow
        dec (hl)
        jr nz, cell_row$
        ret
    __endasm;
}

/* What the page shows: the text pixel at the band's right edge, no
 * further than what it holds; and the ticker's end, once both pages' rings
 * hold only blanks past the text. */
static void Show(u8 page)
{
    u16 drawn = s_Drawn[page];
    g_MessageScroll[page] = drawn < 2 ? 0 : drawn - 2 < s_Offset ? drawn - 2 : s_Offset;
    if (s_TextEnd != 0xFFFF && s_Drawn[0] != 0xFFFF && s_Drawn[1] != 0xFFFF &&
        s_Drawn[0] >= s_TextEnd + 256 && s_Drawn[1] >= s_TextEnd + 256)
        g_MessageActive = s_Stale = 0;
}

void Message_Draw(u8 page, u8 rebuilt) WINGS_BANKED
{
    u16 target = s_Offset + 8, drawn, end, other;
    if (!g_MessageActive) return;
    if (rebuilt || s_Drawn[page] == 0xFFFF)
    {
        /* A cleared page, or a new text over a ring that may hold an old
         * one (blanked first): from the band's left edge (its first 8 px
         * are masked) to target, the whole 256-px ring. */
        if (!rebuilt && s_Stale)
        {
            VDP_CommandHMMV(0, ((u16)page << 8) + 1, 256, FONT_HEIGHT, 0);
            VDP_CommandWait();
        }
        s_Drawn[page] = s_Offset > 248 ? s_Offset - 248 : 0;
        s_Next[page] = 0; s_CharStart[page] = 0;
    }
    /* What the other page already wrote (its ring holds the 256 px before
     * its mark): copy it with the VDP, which runs alongside the CPU. */
    drawn = s_Drawn[page];
    other = s_Drawn[page ^ 1];
    if (other != 0xFFFF && other > drawn && drawn + 256 >= other)
    {
        if (other > target) other = target;
        while (drawn < other)
        {
            end = (drawn | 255) + 1;
            if (end > other) end = other;
            VDP_CommandHMMM((u8)drawn, ((u16)(page ^ 1) << 8) + 1, (u8)drawn, ((u16)page << 8) + 1,
                            end - drawn, FONT_HEIGHT);
            drawn = end;
        }
        s_Drawn[page] = drawn;
    }
    Show(page);
}

u8 Message_Work(u8 page) WINGS_BANKED
{
    u16 target = s_Offset + 8, drawn = s_Drawn[page], start = s_CharStart[page], end;
    u8 next = s_Next[page], g, width;
    if (!g_MessageActive || drawn == 0xFFFF || drawn >= target) return 0;
    /* The character holding pixel `drawn` (blanks past the text). */
    while (s_Text[next] && start + (width = g_FontAdvance[Glyph(s_Text[next])]) <= drawn)
    {
        start += width; ++next;
    }
    /* No further than the ring's end. */
    end = (drawn | 255) + 1;
    if (end > target) end = target;
    if (s_Text[next])
    {
        g = Glyph(s_Text[next]);
        width = g_FontAdvance[g];
        if (start + width < end) end = start + width;
        s_CellBits = g ? g_FontBits + g_FontOffset[g] : 0;
        s_CellStride = (width + 7) >> 3;
        s_CellSkip = (u8)(drawn - start) >> 1;
    }
    else
    {
        s_CellBits = 0;
        s_TextEnd = start;   /* the terminator's place */
    }
    s_CellBytes = (u8)((end - drawn) >> 1);
    s_CellAddr = ((u16)page << 15) + 128 + ((u8)drawn >> 1);
    CellRows();
    s_Drawn[page] = end; s_Next[page] = next; s_CharStart[page] = start;
    Show(page);
    return 1;
}
#endif
