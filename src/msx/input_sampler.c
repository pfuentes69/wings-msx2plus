#include "input_sampler.h"
#include "system_port.h"

ControlQueue g_Controls;
volatile u8 g_InputEnabled = 0;
volatile u8 g_InputInvert, g_InputOverflow;
extern volatile u8 g_VBlankTicks;
static u8 s_Sampled = 0;

static u8 s_Raw[7];

// Fixed-bank ISR fast path: read every VBlank, decode only changed samples.
// Return number of changed bytes in A; IX/IY are preserved by this leaf.
static u8 Input_Read(void) __naked
{
    __asm
        ld hl, #_s_Raw
        ld b, #0
        in a, (0xaa)
        ld d, a
        and #0xf0
        ld e, a
        ld a, e
        or #3
        out (0xaa), a
        in a, (0xa9)
        cp (hl)
        jr z, sample_0$
        inc b
sample_0$:
        ld (hl), a
        inc hl
        ld a, e
        or #4
        out (0xaa), a
        in a, (0xa9)
        cp (hl)
        jr z, sample_1$
        inc b
sample_1$:
        ld (hl), a
        inc hl
        ld a, e
        or #6
        out (0xaa), a
        in a, (0xa9)
        cp (hl)
        jr z, sample_2$
        inc b
sample_2$:
        ld (hl), a
        inc hl
        ld a, e
        or #7
        out (0xaa), a
        in a, (0xa9)
        cp (hl)
        jr z, sample_3$
        inc b
sample_3$:
        ld (hl), a
        inc hl
        ld a, e
        or #8
        out (0xaa), a
        in a, (0xa9)
        cp (hl)
        jr z, sample_4$
        inc b
sample_4$:
        ld (hl), a
        inc hl
        ld a, d
        out (0xaa), a
        ld a, #15
        out (0xa0), a
        in a, (0xa2)
        ld d, a
        and #191
        or #15
        out (0xa1), a
        ld a, #14
        out (0xa0), a
        in a, (0xa2)
_Input_JoySample::
        ld c, a
        ld a, #15
        out (0xa0), a
        ld a, d
        out (0xa1), a
        ld a, (_g_InputInvert)
        or a
        jr z, sample_joy$
        ld a, c
        and #252
        ld d, a
        ld a, c
        and #1
        add a, a
        or d
        ld d, a
        ld a, c
        and #2
        rrca
        or d
        ld c, a
sample_joy$:
        ld a, c
        cp (hl)
        jr z, sample_5$
        inc b
sample_5$:
        ld (hl), a
        inc hl
    __endasm;
#ifdef WINGS_DEBUG_CONTROLS
    __asm
        in a, (0xaa)
        ld d, a
        and #240
        or #5
        out (0xaa), a
        in a, (0xa9)
        cp (hl)
        jr z, sample_6$
        inc b
sample_6$:
        ld (hl), a
        ld a, d
        out (0xaa), a
    __endasm;
#endif
    __asm
        ld a, b
        ret
    __endasm;
}

// The CRT saves registers. No BIOS input function may enable IRQs here.
void Input_Sample(void)
{
    u8 row3,row4,row6,row7,row8,joy,overflow;
#ifdef WINGS_DEBUG_CONTROLS
    u8 row5;
#endif
    u16 state=0;
    if (!g_InputEnabled) return;
    if (!Input_Read() && s_Sampled) return;
    s_Sampled=1;
    row3=s_Raw[0]; row4=s_Raw[1]; row6=s_Raw[2];
    row7=s_Raw[3]; row8=s_Raw[4]; joy=s_Raw[5];
#ifdef WINGS_DEBUG_CONTROLS
    row5=s_Raw[6];
#endif
    if (!(joy&1) || !(row8&32)) state|=ACTION_UP;
    if (!(joy&2) || !(row8&64)) state|=ACTION_DOWN;
    if (!(joy&4) || !(row8&16)) state|=ACTION_LEFT;
    if (!(joy&8) || !(row8&128)) state|=ACTION_RIGHT;
    if (!(joy&16) || !(row8&1)) state|=ACTION_PRIMARY;
    if (!(joy&32) || !(row4&8) || !(row6&4)) state|=ACTION_SECONDARY;
    if (!(row7&128)) state|=ACTION_ENTER;
    if (!(row7&4)) state|=ACTION_ESCAPE;
    if (!(row6&2))
    {
        if (!(row4&128)) state|=ACTION_RESTART;
        if (!(row3&8)) state|=ACTION_INVERT;
        if (!(row4&2)) state|=ACTION_LOAD;
        if (!(row3&16)) state|=ACTION_SAVE;
    }
#ifdef WINGS_DEBUG_CONTROLS
    else if (!(row4&128)) state|=ACTION_DEBUG_RESET;
    if (!(row5&2)) state|=ACTION_DEBUG_TURN;
#endif
    overflow=g_Controls.overflow;
    Controls_Store(&g_Controls,state,g_VBlankTicks);
    if (!overflow && g_Controls.overflow && g_InputOverflow!=255) ++g_InputOverflow;
}
