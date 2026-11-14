#pragma once
/* Terrain column helpers (hand-written Z80, see column_ops.c). */
void Column_Decode(const unsigned char* run, unsigned short* out);
unsigned char Column_Equal(const unsigned short* a, const unsigned short* b);
/* Redraw the changed runs of one terrain column (see column_ops.c). */
extern unsigned char g_ColumnX;
extern unsigned short g_ColumnY;
void Column_Runs(unsigned short* cache, const unsigned short* decoded);
