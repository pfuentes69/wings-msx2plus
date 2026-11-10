#include "bios.h"

// Toolchain smoke test only. Asset decoding precedes the gameplay prototype.
void main(void)
{
    BIOS_SetScreenMode(5);
    for (;;)
    {
        __asm
            halt
        __endasm;
    }
}
