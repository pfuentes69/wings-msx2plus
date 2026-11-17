#ifndef WINGS_BARREL_H
#define WINGS_BARREL_H
#include <stdint.h>
/* The barrel by altitude row and dx / 40 (0x4db8), for the island's dugout
 * guns and the ships' guns: DATA -$63e2, read as one byte array at
 * ((altitude >> 5) - 1) * 8 + dx / 40 + 3. The index runs from -17 (below
 * altitude 32, dx -512) to 47 (altitude 186, dx 512); the ends read the
 * neighbouring constant tables, kept as they are. Include from one module
 * per segment (each gets its copy). */
#define BARREL_BASE 17
static const uint8_t s_Barrel[65] = {
    2, 2, 3, 3, 3, 1, 2, 3, 3, 0, 1, 2, 3, 0, 1, 2, 3,
    0, 0, 0, 3, 3, 6, 6, 6,  0, 1, 1, 3, 3, 5, 5, 6,  1, 1, 2, 3, 3, 4, 5, 5,
    1, 2, 2, 3, 3, 4, 4, 5,  2, 2, 3, 3, 3, 3, 4, 4,  1, 2, 3, 2, 1, 2, 3, 2};
#endif
