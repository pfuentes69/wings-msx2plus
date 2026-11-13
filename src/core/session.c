#include "session.h"
#include <string.h>

static void Put16(uint8_t* p, uint16_t v) { p[0]=v; p[1]=v>>8; }
static uint16_t Get16(const uint8_t* p) { return p[0]|((uint16_t)p[1]<<8); }
static uint8_t Check(const uint8_t* bytes)
{
    uint8_t crc=0,i,bit;
    for (i=0; i<31; ++i)
    {
        crc^=bytes[i];
        for (bit=0; bit<8; ++bit) crc=crc&128 ? (crc<<1)^7 : crc<<1;
    }
    return crc;
}
static uint8_t Valid(const SessionState* state)
{
    return state->game.progress.rank<7 && state->game.progress.lives &&
        state->game.sortie.weapon<=WEAPON_TORPEDO &&
        state->game.sortie.stock<=Game_WeaponStock(state->game.sortie.weapon) &&
        state->game.invert<=1 && state->game.mission.map<15 &&
        state->x<7608 && state->y<=1200 && state->left<=1 &&
        state->vx>=-205 && state->vx<=205 && state->vy>=-154 && state->vy<=154;
}
uint8_t Session_Encode(const SessionState* s, uint8_t on_carrier, uint8_t* p)
{
    uint32_t score=s->game.progress.score;
    if (!on_carrier || !Valid(s)) return 0;
    p[0]='W';p[1]='M';p[2]='S';p[3]='X';p[4]=SESSION_VERSION;
    p[5]=s->game.progress.rank;p[6]=s->game.progress.lives;
    p[7]=s->game.sortie.weapon;p[8]=s->game.sortie.stock;
    p[9]=s->game.sortie.oil;p[10]=s->game.sortie.fuel;p[11]=s->game.invert;
    Put16(p+12,score);Put16(p+14,score>>16);
    Put16(p+16,s->game.progress.kills);Put16(p+18,s->game.mission.map);
    Put16(p+20,s->game.mission.objectives);Put16(p+22,s->x);Put16(p+24,s->y);
    Put16(p+26,s->vx);Put16(p+28,s->vy);p[30]=s->left;p[31]=Check(p);
    return 1;
}
uint8_t Session_Decode(const uint8_t* p, uint16_t size, SessionState* out)
{
    SessionState next;
    if (size!=SESSION_SIZE || p[0]!='W' || p[1]!='M' || p[2]!='S' || p[3]!='X' ||
        p[4]!=SESSION_VERSION || p[31]!=Check(p)) return 0;
    memset(&next,0,sizeof(next));Game_Reset(&next.game);
    next.game.progress.rank=p[5];next.game.progress.lives=p[6];
    next.game.sortie.weapon=p[7];next.game.sortie.stock=p[8];
    next.game.sortie.oil=p[9];next.game.sortie.fuel=p[10];next.game.invert=p[11];
    next.game.progress.score=Get16(p+12)|((uint32_t)Get16(p+14)<<16);
    next.game.progress.kills=Get16(p+16);next.game.mission.map=Get16(p+18);
    next.game.mission.objectives=Get16(p+20);next.x=Get16(p+22);next.y=Get16(p+24);
    next.vx=(int16_t)Get16(p+26);next.vy=(int16_t)Get16(p+28);next.left=p[30];
    next.game.phase=GAME_PLAY;
    if (!Valid(&next)) return 0;
    *out=next;return 1;
}
