#include "banking.h"
#include "core.h"

// Resident helpers required by SDCC's ___sdcc_bcall_ehl trampoline.
// They must preserve every register except A (set_bank keeps A as well).
// g_Bank3Segment is the crt0 shadow of the ASCII8 window-3 register.
void Banking_Trampolines(void) __naked
{
    __asm
    set_bank::
        ld (0x7800), a
        ld (_g_Bank3Segment), a
        ret
    get_bank::
        ld a, (_g_Bank3Segment)
        ret
    __endasm;
}
