#pragma once
/* Terrain column helpers (hand-written Z80, see column_ops.c). */
void Column_Decode(const unsigned char* run, unsigned short* out);
unsigned char Column_Equal(const unsigned short* a, const unsigned short* b);
