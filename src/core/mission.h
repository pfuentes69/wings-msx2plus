#pragma once
#include <stdint.h>

#define MISSION_SEA 0
#define MISSION_CARRIER 1
#define MISSION_ISLAND 2

/* Exact source strip query: low two bits are class, next nine are object ID.
 * Out-of-strip queries return zero. No collision height is implied. */
uint16_t Mission_Query(int16_t x);
/* Class-only lookup over the original surface intervals. */
uint8_t Mission_Surface(uint16_t x);
