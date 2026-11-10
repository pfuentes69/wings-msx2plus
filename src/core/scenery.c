#include "scenery.h"

uint8_t Scenery_Pixel(uint16_t x, uint8_t y)
{
    static const uint8_t heights[64] = {
        0,0,0,0,1,2,4,6,8,9,10,11,12,11,10,8,
        7,6,4,2,1,0,0,0,0,0,0,0,0,0,0,0,
        0,0,0,1,3,5,7,9,10,12,14,13,12,10,8,7,
        8,9,8,7,5,4,3,1,0,0,0,0,0,0,0,0
    };
    uint8_t height;
    x &= 511;
    height = heights[x >> 3] >> 1;
    if (y < 4) return 0;
    if (height && y >= 13 - height && y < 14)
        return y == 13 - height ? 12 : 15;
    if (y >= 14) return 13;
    if ((y == 6 || y == 11) && ((x + (y == 6 ? 0 : 17)) & 63) < 12) return 11;
    return 13;
}
