#pragma once
#include "core.h"
#include "../core/controls.h"
extern ControlQueue g_Controls;
extern volatile u8 g_InputEnabled, g_InputInvert, g_InputOverflow;
void Input_Sample(void);
/* Typing (a high score's name): while g_TypeMode is set, each VBlank the
 * keyboard rows 0..8 are scanned and every key newly down is queued, in
 * order, as row * 8 + bit (8 entries; more are dropped). g_KeyDown holds
 * the rows as last scanned, 1 = down. Menu_Key (msx/menu.c) reads it. */
extern volatile u8 g_TypeMode, g_KeyHead, g_KeyTail;
extern volatile u8 g_KeyQueue[8], g_KeyDown[9];
