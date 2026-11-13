#include "carrier.h"
#ifdef WINGS_P1_FLIGHT
void Carrier_Reset(CarrierState* state)
{
    state->stage=CARRIER_RAISING;state->depth=CARRIER_DEPTH;state->tick=0;
}
void Carrier_Raise(CarrierState* state) { state->stage=CARRIER_RAISING;state->tick=0; }
uint8_t Carrier_Request(CarrierState* state,const FlightState* flight,uint16_t world)
{
    if (state->stage!=CARRIER_DECK || flight->mode!=FLIGHT_GROUND || flight->vx || flight->turn_ticks ||
        world<CARRIER_X-6 || world>CARRIER_X+6) return 0;
    state->stage=CARRIER_LOWERING;state->tick=0;return 1;
}
uint8_t Carrier_Step(CarrierState* state)
{
    if (state->stage==CARRIER_DECK || state->stage==CARRIER_HOLD) return 0;
    if (++state->tick<CARRIER_PIXEL_TICKS) return 0;
    state->tick=0;
    if (state->stage==CARRIER_RAISING)
    {
        if (!--state->depth) {state->stage=CARRIER_DECK;return 1;}
    }
    else if (++state->depth==CARRIER_DEPTH) {state->stage=CARRIER_HOLD;return 1;}
    return 0;
}
#endif
