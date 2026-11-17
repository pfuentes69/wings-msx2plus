#ifndef WINGS_CONTROLS_H
#define WINGS_CONTROLS_H
#include <stdint.h>
#define ACTION_UP 1u
#define ACTION_RIGHT 2u
#define ACTION_DOWN 4u
#define ACTION_LEFT 8u
#define ACTION_PRIMARY 16u
#define ACTION_SECONDARY 32u
#define ACTION_ENTER 64u
#define ACTION_ESCAPE 128u
#define ACTION_RESTART 256u
#define ACTION_INVERT 512u
#define ACTION_LOAD 1024u
#define ACTION_SAVE 2048u
#define ACTION_DEBUG_RESET 4096u
#define ACTION_DEBUG_TURN 8192u
/* Cheats (F1 refills the weapon): not in the original. */
#define ACTION_CHEAT_REFILL 16384u
#define ACTION_BUTTONS (ACTION_PRIMARY|ACTION_SECONDARY|ACTION_ENTER)
#define INPUT_QUEUE_SIZE 8

typedef struct ControlEvent { uint16_t state; uint8_t stamp; } ControlEvent;
typedef struct ControlQueue {
    ControlEvent events[INPUT_QUEUE_SIZE];
    uint16_t raw, latest, blocked;
    uint8_t head, tail, overflow;
} ControlQueue;

void Controls_Reset(ControlQueue* q);
/* Single producer (VBlank), single consumer. Platform consumer disables IRQs. */
void Controls_Store(ControlQueue* q, uint16_t state, uint8_t stamp);
/* Pop returns 1 for an event, 2 for overflow resynchronization, 0 if empty. */
uint8_t Controls_Pop(ControlQueue* q, ControlEvent* event);
void Controls_Block(ControlQueue* q);
#endif
