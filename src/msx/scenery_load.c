#include "scenery_load.h"
#include "system.h"
#include "rom_mapper.h"
// Linked first, below 6000h: all callers resume with resident bank 1 restored.
// The copy helper lives in this module too, so it stays mapped while bank 1
// (6000h-7FFFh) holds the data being read.

static u16 s_CopySize;
/* LDIR s_CopySize (> 0) bytes from HL to DE (sdcccall(1): src, dst). */
static void CopyBytes(const u8* source, u8* destination) __naked
{
    (void)source; (void)destination;
    __asm
        ld      bc, (_s_CopySize)
        ldir
        ret
    __endasm;
}

/* Window 1 (6000h-7FFFh) = segment, sdcccall(1): A. Always LD (nn),A, the
 * form loaders patch: SofaRun's memory-mapper mode rewrites only that one
 * (docs/diag-rom.md); the macro compiled to LD (HL),A. */
static void SetBank1(u8 segment) __naked
{
    (void)segment;
    __asm
        ld      (0x6800), a
        ret
    __endasm;
}

/* One LDIR per bank-sized chunk: the byte loop in C cost ~80 T-states per
 * byte, ~8 ms for a 280-byte dial patch. */
void Scenery_Read(u8 bank, u16 offset, u8* destination, u8 size)
{
    u16 chunk;
    SetBank1(bank);
    while (size)
    {
        if (offset == 8192) { offset = 0; ++bank; SetBank1(bank); }
        chunk = 8192 - offset;
        if (chunk > size) chunk = size;
        s_CopySize = chunk;
        CopyBytes((const u8*)(0x6000 + offset), destination);
        destination += chunk; offset += chunk; size -= (u8)chunk;
    }
    SetBank1(1);
}
void Scenery_ReadEnd(void) {}
