#include "vdp_ring.h"
#include "vdp.h"

/* Resident: the overlays in every segment use it. In SDCC's C each part of
 * a copy cost 8 field stores through the stack frame plus the seam loop
 * (~1,000-2,000 T-states); here the fixed fields are set once per copy. */
void Vdp_RingCopy(u8 ring, u16 width) __naked
{
    (void)ring; (void)width;
    __asm
        ; sdcccall(1): A ring, DE width
        ld (_g_VDP_Command + 4), a      ; DX
        ld hl, #_g_VDP_Command + 5
        ld (hl), #0
        neg                             ; the room to the seam, 0 for 256
        jr z, ring_one$
        ld c, a
        ld b, #0
        ex de, hl
        or a
        sbc hl, bc                      ; width - room
        jr c, ring_back$
        jr z, ring_back$
        push hl                         ; two parts: up to the seam, the rest from 0
        ld (_g_VDP_Command + 8), bc
        push bc
        call _VDP_CommandSetupR32
        pop bc
        ld hl, (_g_VDP_Command + 0)
        add hl, bc
        ld (_g_VDP_Command + 0), hl     ; SX past the first part
        xor a
        ld (_g_VDP_Command + 4), a      ; DX 0
        pop hl
        ld (_g_VDP_Command + 8), hl
        jp _VDP_CommandSetupR32
    ring_back$:
        add hl, bc
        ex de, hl
    ring_one$:
        ld (_g_VDP_Command + 8), de     ; NX
        jp _VDP_CommandSetupR32
    __endasm;
}
