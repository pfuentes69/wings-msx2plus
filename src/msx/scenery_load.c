#include "scenery_load.h"
#include "system.h"
#include "rom_mapper.h"
// Linked first, below 6000h: all callers resume with resident bank 1 restored.
void Scenery_Read(u8 bank, u16 offset, u8* destination, u8 size)
{
    SET_BANK_SEGMENT(1, bank);
    while (size--)
    {
        if (offset == 8192) { offset = 0; ++bank; SET_BANK_SEGMENT(1, bank); }
        *destination++ = *((const u8*)(0x6000 + offset++));
    }
    SET_BANK_SEGMENT(1, 1);
}
void Scenery_ReadEnd(void) {}
