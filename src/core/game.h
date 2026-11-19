#ifndef WINGS_GAME_H
#define WINGS_GAME_H
#include <stdint.h>
#include "controls.h"
#include "../msx/banking.h"
#define GAME_RANK 0
#define GAME_BRIEFING 1
#define GAME_LOADOUT 2
#define GAME_PLAY 3
#define GAME_PAUSE 4
#define GAME_LOAD_MENU 5
#define GAME_SAVE_MENU 6
#define GAME_SERVICE 7
#define GAME_OVER 8
#define WEAPON_BOMBS 0
#define WEAPON_ROCKETS 1
#define WEAPON_TORPEDO 2
#define GAME_START_SORTIE 1
#define GAME_CONTEXT_CHANGED 2
#define GAME_RESTARTED 4
#define GAME_LEAVE_SERVICE 8

typedef struct GameProgress { uint32_t score; uint16_t kills; uint8_t rank,lives; } GameProgress;
/* The mission: its number within the rank (1-based, -$5c3e) and the map
 * it flies (0..14, from the rank and number: -$7b9f). */
typedef struct MissionProgress { uint8_t map, number; uint16_t objectives; } MissionProgress;
typedef struct SortieState { uint8_t weapon,stock,oil,fuel; } SortieState;
typedef struct GameState {
    GameProgress progress;
    MissionProgress mission;
    SortieState sortie;
    uint8_t phase,cursor,invert,notice;
} GameState;

uint8_t Game_WeaponStock(uint8_t weapon) WINGS_BANKED;
void Game_SetLoadout(GameState* game, uint8_t weapon) WINGS_BANKED;
void Game_OpenService(GameState* game) WINGS_BANKED;
void Game_Reset(GameState* game) WINGS_BANKED;
/* A crash costs one plane. Returns 1 while planes remain, else enters GAME_OVER. */
uint8_t Game_LosePlane(GameState* game) WINGS_BANKED;
uint8_t Game_HandleAction(GameState* game, uint16_t pressed) WINGS_BANKED;
/* The mission's last objective is done (0x5694): the next mission number,
 * and past the rank's last one the next rank (at most the 7th). Returns 1
 * for a promotion: its extra plane comes back on board (Game_NextMission). */
uint8_t Game_AdvanceMission(GameState* game) WINGS_BANKED;
/* Back in the hold with the mission complete (0x0122): the promotion's
 * plane, then the next mission's briefing. */
void Game_NextMission(GameState* game, uint8_t promoted) WINGS_BANKED;
void Game_View(const GameState* game, uint8_t* view) WINGS_BANKED;
/* Once a presented frame: the briefing closes by itself after 240 PAL
 * frames (0x8590), 4.8 s; 288 NTSC fields. ticks: VBlanks since the last
 * call; pal: nonzero at 50 Hz. Returns 1 when it moved on (to the loadout). */
uint8_t Game_Wait(GameState* game, uint8_t ticks, uint8_t pal) WINGS_BANKED;
#endif
