#include "game.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_GAME)
#include "engine.h"

uint8_t Game_WeaponStock(uint8_t weapon) WINGS_BANKED
{
    return weapon==WEAPON_BOMBS ? 30 : weapon==WEAPON_ROCKETS ? 15 : weapon==WEAPON_TORPEDO ? 1 : 0;
}

void Game_SetLoadout(GameState* game, uint8_t weapon) WINGS_BANKED
{
    if (weapon>WEAPON_TORPEDO) return;
    game->sortie.weapon=weapon;
    game->sortie.stock=Game_WeaponStock(weapon);
}

/* Missions per rank (-$5ab6) and each mission's map by rank * 4 + number
 * (-$7b9f): 15 maps over 7 ranks. Only map 0 (mission A) is decoded yet;
 * the others fly it too until the campaign is (P6). */
static const uint8_t s_MissionsPerRank[7] = {3, 3, 2, 2, 1, 1, 3};
static const uint8_t s_MissionMap[28] = {
    0, 0, 1, 2,  0, 3, 4, 5,  0, 6, 7, 0,  0, 8, 9, 0,
    0, 10, 0, 0, 0, 11, 0, 0, 0, 12, 13, 14};

static void FirstMission(GameState* game)
{
    game->mission.number=1;
    game->mission.map=s_MissionMap[(uint8_t)(game->progress.rank<<2)+1];
}

uint8_t Game_AdvanceMission(GameState* game) WINGS_BANKED
{
    uint8_t promoted=0;
    if (++game->mission.number>s_MissionsPerRank[game->progress.rank])
    {
        game->mission.number=1;
        if (game->progress.rank<6) ++game->progress.rank;
        promoted=1;
    }
    game->mission.map=s_MissionMap[(uint8_t)(game->progress.rank<<2)+game->mission.number];
    return promoted;
}

void Game_NextMission(GameState* game, uint8_t promoted) WINGS_BANKED
{
    /* The HUD shows one digit of planes. */
    if (promoted && game->progress.lives<9) ++game->progress.lives;
    /* The hold repairs and refuels, as for a service. */
    game->sortie.oil=ENGINE_OIL_FULL; game->sortie.fuel=ENGINE_FUEL_FULL;
    game->phase=GAME_BRIEFING; game->cursor=game->notice=0;
}

void Game_Reset(GameState* game) WINGS_BANKED
{
    game->progress.score=0; game->progress.kills=0;
    game->progress.rank=0; game->progress.lives=3;
    game->mission.objectives=0; FirstMission(game);
    Game_SetLoadout(game,WEAPON_BOMBS);
    game->sortie.oil=ENGINE_OIL_FULL; game->sortie.fuel=ENGINE_FUEL_FULL;
    game->phase=GAME_RANK; game->cursor=game->invert=game->notice=0;
}

uint8_t Game_LosePlane(GameState* game) WINGS_BANKED
{
    if (game->progress.lives) --game->progress.lives;
    if (game->progress.lives) return 1;
    game->phase=GAME_OVER; game->cursor=game->notice=0;
    return 0;
}

void Game_OpenService(GameState* game) WINGS_BANKED
{
    game->phase=GAME_SERVICE;game->cursor=game->sortie.weapon;game->notice=0;
    Game_SetLoadout(game,game->sortie.weapon);
    /* The hold repairs and refuels to full (manual; values from the executable). */
    game->sortie.oil=ENGINE_OIL_FULL; game->sortie.fuel=ENGINE_FUEL_FULL;
}

uint8_t Game_HandleAction(GameState* game, uint16_t pressed) WINGS_BANKED
{
    uint8_t old=game->phase, prev, next, count;
    if (pressed & ACTION_RESTART)
    {
        prev=game->invert; Game_Reset(game); game->invert=prev;
        return GAME_CONTEXT_CHANGED|GAME_RESTARTED;
    }
    if (old==GAME_PLAY && (pressed & (ACTION_LOAD|ACTION_SAVE)))
    {
        game->phase=pressed & ACTION_LOAD ? GAME_LOAD_MENU : GAME_SAVE_MENU;
        game->cursor=GAME_PLAY;
        return GAME_CONTEXT_CHANGED;
    }
    if (pressed & ACTION_INVERT) { game->invert^=1; return 0; }
    if (pressed & ACTION_ESCAPE)
    {
        if (old==GAME_PLAY) game->phase=GAME_PAUSE;
        else if (old==GAME_PAUSE) game->phase=GAME_PLAY;
        else if (old==GAME_LOAD_MENU || old==GAME_SAVE_MENU)
        { game->phase=game->cursor; game->cursor=game->progress.rank; }
        return game->phase!=old ? GAME_CONTEXT_CHANGED : 0;
    }
    if (old==GAME_PAUSE || old==GAME_PLAY) return 0;
    count=old==GAME_RANK ? 8 : (old==GAME_LOADOUT || old==GAME_SERVICE) ? 3 : 0;
    if (count)
    {
        prev=!!(pressed & (ACTION_UP|ACTION_LEFT));
        next=!!(pressed & (ACTION_DOWN|ACTION_RIGHT));
        if (prev!=next)
        {
            if (next) game->cursor=(game->cursor+1)%count;
            else game->cursor=game->cursor ? game->cursor-1 : count-1;
            game->notice=0;
            if (old==GAME_LOADOUT || old==GAME_SERVICE) Game_SetLoadout(game,game->cursor);
        }
    }
    if (!(pressed & (ACTION_BUTTONS))) return 0;
    if (old==GAME_OVER)
    {
        /* High-score entry arrives with P6; return to rank selection. */
        prev=game->invert; Game_Reset(game); game->invert=prev;
        return GAME_CONTEXT_CHANGED;
    }
    if (old==GAME_RANK)
    {
        if (game->cursor==7) { game->phase=GAME_LOAD_MENU; game->cursor=GAME_RANK; }
        else { game->progress.rank=game->cursor; FirstMission(game); game->phase=GAME_BRIEFING; }
    }
    else if (old==GAME_BRIEFING)
    {
        game->phase=GAME_LOADOUT; game->cursor=0; Game_SetLoadout(game,WEAPON_BOMBS);
    }
    else if (old==GAME_LOADOUT || old==GAME_SERVICE)
    {
        // P3/P4 implement rocket/torpedo behavior. Never consume their stock
        // or launch a bomb disguised as a different selected weapon.
        if (game->sortie.weapon!=WEAPON_BOMBS) { game->notice=1; return 0; }
        game->phase=GAME_PLAY;
        return GAME_CONTEXT_CHANGED|(old==GAME_SERVICE ? GAME_LEAVE_SERVICE : GAME_START_SORTIE);
    }
    else if (old==GAME_LOAD_MENU || old==GAME_SAVE_MENU)
        { game->phase=game->cursor; game->cursor=game->progress.rank; }
    return game->phase!=old ? GAME_CONTEXT_CHANGED : 0;
}

void Game_View(const GameState* game, uint8_t* view) WINGS_BANKED
{
    view[0]=game->phase; view[1]=game->progress.rank; view[2]=game->progress.lives;
    view[3]=game->sortie.weapon; view[4]=game->sortie.stock; view[5]=game->invert;
    view[6]=game->cursor; view[7]=game->notice;
}
