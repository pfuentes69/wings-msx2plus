#ifndef WINGS_SESSION_H
#define WINGS_SESSION_H
#include "game.h"
#define SESSION_SIZE 32
#define SESSION_VERSION 2   /* 2: map and mission number in bytes 18, 19 */
/* P0 schema for portable state and inventory round trips. P2/P6 extend it for
 * deck/elevator/enemy state before enabling user-facing disk saves. */
typedef struct SessionState {
    GameState game;
    uint16_t x,y;
    int16_t vx,vy;
    uint8_t left;
} SessionState;
uint8_t Session_Encode(const SessionState* source, uint8_t on_carrier, uint8_t* bytes);
uint8_t Session_Decode(const uint8_t* bytes, uint16_t size, SessionState* destination);
#endif
