#ifndef WINGS_GAME_H
#define WINGS_GAME_H
#include <stdint.h>
#include "controls.h"
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
typedef struct MissionProgress { uint16_t map, objectives; } MissionProgress;
typedef struct SortieState { uint8_t weapon,stock,oil,fuel; } SortieState;
typedef struct GameState {
    GameProgress progress;
    MissionProgress mission;
    SortieState sortie;
    uint8_t phase,cursor,invert,notice;
} GameState;

uint8_t Game_WeaponStock(uint8_t weapon);
void Game_SetLoadout(GameState* game, uint8_t weapon);
void Game_OpenService(GameState* game);
void Game_Reset(GameState* game);
/* A crash costs one plane. Returns 1 while planes remain, else enters GAME_OVER. */
uint8_t Game_LosePlane(GameState* game);
uint8_t Game_HandleAction(GameState* game, uint16_t pressed);
void Game_View(const GameState* game, uint8_t* view);
#endif
