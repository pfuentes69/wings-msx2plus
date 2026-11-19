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
#define GAME_OVER 8      /* "The end" (0xaf7c): 150 frames, or a button after 30 */
#define GAME_NAME 9      /* a high score's name (0x9856): typed, 16 at most */
#define GAME_SCORES 10   /* the ten best (0x9856): 1800 frames or a button */
#define GAME_SCORE_COUNT 10
#define GAME_NAME_LENGTH 16
#define WEAPON_BOMBS 0
#define WEAPON_ROCKETS 1
#define WEAPON_TORPEDO 2
/* A weapon's line in the original's weapon panel (0 Rockets, 1 Bombs,
 * 2 Torpedo, top to bottom). */
#define GAME_WEAPON_LINE(weapon) ((weapon) == WEAPON_BOMBS ? 1 : (weapon) == WEAPON_ROCKETS ? 0 : 2)
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

/* The high-score table (docs/research/amiga-hiscores.md): ten entries,
 * best first; a score of 0 is an empty row. RAM only (the original keeps a
 * `highscore` file). Built with WINGS_HIGH_SCORES only: set aside while it
 * can't be saved; without it a game's end goes back to rank selection. */
typedef struct HighScore { uint32_t score; uint8_t rank; char name[GAME_NAME_LENGTH]; } HighScore;
extern HighScore g_HighScores[GAME_SCORE_COUNT];
extern char g_Name[GAME_NAME_LENGTH];   /* the name being entered */
extern uint8_t g_NameLength;

uint8_t Game_WeaponStock(uint8_t weapon) WINGS_BANKED;
/* Boot: the table empty (RAM is not cleared). */
void Game_ClearScores(void) WINGS_BANKED;
/* A key typed while a name is entered: 'A'..'Z', '0'..'9', ' ', '.' are
 * added, 8 deletes the last. Returns 1 when the name changed. */
uint8_t Game_Type(GameState* game, uint8_t key) WINGS_BANKED;
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
/* Once a presented frame, the screens that move on by themselves, in PAL
 * frames (NTSC fields 6/5 as many): the briefing after 240 (0x8590), "the
 * end" after 150 (0xaf7c), the high scores after 1800 (0x9856). ticks:
 * VBlanks since the last call; pal: nonzero at 50 Hz. Returns 1 when the
 * phase changed. */
uint8_t Game_Wait(GameState* game, uint8_t ticks, uint8_t pal) WINGS_BANKED;
#endif
