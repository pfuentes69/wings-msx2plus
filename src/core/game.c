#include "game.h"

uint8_t Game_WeaponStock(uint8_t weapon)
{
    return weapon==WEAPON_BOMBS ? 30 : weapon==WEAPON_ROCKETS ? 15 : weapon==WEAPON_TORPEDO ? 1 : 0;
}

void Game_SetLoadout(GameState* game, uint8_t weapon)
{
    if (weapon>WEAPON_TORPEDO) return;
    game->sortie.weapon=weapon;
    game->sortie.stock=Game_WeaponStock(weapon);
}

void Game_Reset(GameState* game)
{
    game->progress.score=0; game->progress.kills=0;
    game->progress.rank=0; game->progress.lives=3;
    game->mission.map=0; game->mission.objectives=0;
    Game_SetLoadout(game,WEAPON_BOMBS);
    game->sortie.oil=game->sortie.fuel=255;
    game->phase=GAME_RANK; game->cursor=game->invert=game->notice=0;
}

void Game_OpenService(GameState* game)
{
    game->phase=GAME_SERVICE;game->cursor=game->sortie.weapon;game->notice=0;
    Game_SetLoadout(game,game->sortie.weapon);
    game->sortie.oil=game->sortie.fuel=255;
}

uint8_t Game_HandleAction(GameState* game, uint16_t pressed)
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
    if (old==GAME_RANK)
    {
        if (game->cursor==7) { game->phase=GAME_LOAD_MENU; game->cursor=GAME_RANK; }
        else { game->progress.rank=game->cursor; game->phase=GAME_BRIEFING; }
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

void Game_View(const GameState* game, uint8_t* view)
{
    view[0]=game->phase; view[1]=game->progress.rank; view[2]=game->progress.lives;
    view[3]=game->sortie.weapon; view[4]=game->sortie.stock; view[5]=game->invert;
    view[6]=game->cursor; view[7]=game->notice;
}
