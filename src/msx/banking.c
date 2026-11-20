#include "banking.h"
#include "core.h"

// Resident helpers required by SDCC's ___sdcc_bcall_ehl trampoline.
// They must preserve every register except A (set_bank keeps A as well).
// g_Bank3Segment is the crt0 shadow of the ASCII8 window-3 register. The
// shadow is written first: an interrupt that maps window 3 for itself puts
// back the segment the shadow names (docs/music.md), so the shadow must
// never name an older segment than the register holds.
void Banking_Trampolines(void) __naked
{
    __asm
    set_bank::
        ld (_g_Bank3Segment), a
        ld (0x7800), a
        ret
    get_bank::
        ld a, (_g_Bank3Segment)
        ret
    __endasm;
}
