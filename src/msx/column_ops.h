#pragma once
/* Terrain column helpers (hand-written Z80, see column_ops.c). */
void Column_Decode(const unsigned char* run, unsigned short* out);
unsigned char Column_Equal(const unsigned short* a, const unsigned short* b);
/* A sinking hull column one stage lower: the first row whose tile differs
 * from row 0's (TERRAIN_MAP_ROWS if none), the rows shifted down one; 255
 * and nothing shifted when a row holds no tile. */
unsigned char Column_Lower(unsigned short* cache);
/* Redraw the changed runs of one terrain column (see column_ops.c). */
extern unsigned char g_ColumnX;
extern unsigned short g_ColumnY;
void Column_Runs(unsigned short* cache, const unsigned short* decoded);
/* Dynamic overlays mark their affected tile rows for repaint on ring reuse:
 * map rows first..last (first <= last) of every ring column from world x
 * left & ~7 up to right, on page. Set g_DirtyRange, then call. */
typedef struct DirtyRange { unsigned short left, right; unsigned char page, first, last; } DirtyRange;
extern DirtyRange g_DirtyRange;
void Terrain_DirtyOverlay(void);
/* Defined by the terrain streamer (terrain_renderer.h). */
extern unsigned short g_TerrainColumns[2][32];
