#include "controls.h"

void Controls_Reset(ControlQueue* q)
{
    q->raw=q->latest=q->blocked=0;
    q->head=q->tail=q->overflow=0;
}

void Controls_Store(ControlQueue* q, uint16_t state, uint8_t stamp)
{
    uint8_t next;
    q->raw=state;
    q->blocked &= state;
    state &= ~q->blocked;
    if (state == q->latest) return;
    q->latest=state;
    if (q->overflow) return;
    next=(q->head+1)&(INPUT_QUEUE_SIZE-1);
    if (next==q->tail) { q->overflow=1; return; }
    q->events[q->head].state=state;
    q->events[q->head].stamp=stamp;
    q->head=next;
}

void Controls_Block(ControlQueue* q)
{
    q->tail=q->head;
    q->blocked=q->raw & ACTION_BUTTONS;
    q->latest=q->raw & ~q->blocked;
    q->overflow=0;
}

uint8_t Controls_Pop(ControlQueue* q, ControlEvent* event)
{
    if (q->overflow) { Controls_Block(q); return 2; }
    if (q->head==q->tail) return 0;
    *event=q->events[q->tail];
    q->tail=(q->tail+1)&(INPUT_QUEUE_SIZE-1);
    return 1;
}
