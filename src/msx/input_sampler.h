#pragma once
#include "core.h"
#include "../core/controls.h"
extern ControlQueue g_Controls;
extern volatile u8 g_InputEnabled, g_InputInvert, g_InputOverflow;
void Input_Sample(void);
