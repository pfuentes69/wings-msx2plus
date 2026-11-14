/* Hand-written Z80 P1 flight step, included by flight.c for SDCC builds.
 * Behaviour is identical to the C reference in flight.c (StepControls +
 * Flight_StepWorldSample under WINGS_P1_FLIGHT); tests/test_flight_z80.py
 * runs both on an emulated Z80 and compares every field.
 *
 * SDCC sdcccall(1) interface: HL = state, DE = x, stack = return address,
 * input (byte), sample_pose (byte). The callee removes the two argument
 * bytes. IX and IY are preserved; AF, BC, DE and HL are clobbered.
 *
 * FlightState layout: 0 x, 2 y (4 bytes), 6 vx, 8 vy, 10 frame,
 * 11 facing_left, 12 mode, 13 turn_ticks, 14 target_left, 15 ground_tick.
 *
 * Domain: |vx|, |vy| and the targets stay far below 32,768, so 16-bit
 * differences cannot overflow (same assumption as the C code on SDCC,
 * whose int is 16 bits). */

/* Constants below are hard-coded in the assembly; fail the build if the
 * C definitions drift. */
typedef char FlightZ80CheckTaxiMin[(FLIGHT_TAXI_MIN_X == 6617u) ? 1 : -1];
typedef char FlightZ80CheckTaxiMax[(FLIGHT_TAXI_MAX_X == 7336u) ? 1 : -1];
typedef char FlightZ80CheckLaunch[(FLIGHT_LAUNCH_ZONE == 6657u) ? 1 : -1];
typedef char FlightZ80CheckTakeoff[(FLIGHT_TAKEOFF_SPEED == 154) ? 1 : -1];
typedef char FlightZ80CheckTaxiTurn[(FLIGHT_TAXI_TURN_TICKS == 240u) ? 1 : -1];
typedef char FlightZ80CheckTurn[(FLIGHT_TURN_TICKS == 110u) ? 1 : -1];
typedef char FlightZ80CheckAccel[(FLIGHT_GROUND_ACCEL_TICKS == 5u) ? 1 : -1];
typedef char FlightZ80CheckMaxY[(WINGS_FLIGHT_MAX_Y == 1200u) ? 1 : -1];
typedef char FlightZ80CheckModes[(FLIGHT_GROUND == 0 && FLIGHT_AIRBORNE == 1 &&
    FLIGHT_STALL == 2 && FLIGHT_STALL_DIVE == 3) ? 1 : -1];
typedef char FlightZ80CheckInput[(FLIGHT_UP == 1 && FLIGHT_RIGHT == 2 &&
    FLIGHT_DOWN == 4 && FLIGHT_LEFT == 8) ? 1 : -1];

/* World width varies with the mission manifest, so the bound is data. */
const uint32_t g_FlightWorldMax = (uint32_t)(WINGS_WORLD_WIDTH - 1u) * 256u;
uint8_t g_FlightStepInput;
int16_t g_FlightStepClimb;

void Flight_StepWorldSample(FlightState* state, uint32_t* x, uint8_t input, uint8_t sample_pose) __naked
{
    __asm
        push    iy
        push    de                      ; x pointer, popped at fsw_world$
        push    hl
        pop     iy                      ; IY = state
        ld      hl, #6
        add     hl, sp                  ; [x][iy][ret][input][pose]
        ld      a, (hl)
        ld      (_g_FlightStepInput), a
        ld      b, a
        and     a, #0x0a                ; horizontal = input & (LEFT | RIGHT)
        cp      a, #0x0a
        jr      nz, fsw_h$
        xor     a, a
    fsw_h$:
        ld      c, a                    ; C = horizontal (0, 2 right, 8 left)
        ld      a, b
        and     a, #0x05                ; vertical = input & (UP | DOWN)
        cp      a, #0x05
        jr      nz, fsw_v$
        xor     a, a
    fsw_v$:
        ld      b, a                    ; B = vertical (0, 1 up, 4 down)
        ld      l, 6 (iy)
        ld      h, 7 (iy)
        bit     7, h
        jr      z, fsw_speed$
        xor     a, a                    ; speed = -vx
        sub     a, l
        ld      l, a
        sbc     a, a
        sub     a, h
        ld      h, a
    fsw_speed$:                         ; HL = speed
        ld      a, 12 (iy)
        or      a, a
        jp      nz, fsw_air$

        ; ---- ground ----
        xor     a, a
        ld      8 (iy), a               ; vy = 0
        ld      9 (iy), a
        ld      a, 13 (iy)
        or      a, a
        jr      z, fsw_g_free$
        xor     a, a                    ; taxi turn in progress: vx = 0
        ld      6 (iy), a
        ld      7 (iy), a
        dec     13 (iy)
        jp      nz, fsw_world$
        ld      a, 14 (iy)
        ld      11 (iy), a              ; facing_left = target_left
        jp      fsw_world$
    fsw_g_free$:
        ld      a, c
        or      a, a
        jr      z, fsw_g_idle$
        call    fsw_leftflag$           ; A = (horizontal == LEFT)
        cp      a, 11 (iy)
        jr      z, fsw_g_same$
        call    fsw_approach0$          ; reversing: brake to a stop
        ld      15 (iy), #0
        ld      a, h
        or      a, l
        jr      nz, fsw_g_store$
        call    fsw_leftflag$
        ld      14 (iy), a              ; target_left = horizontal == LEFT
        ld      13 (iy), #240           ; FLIGHT_TAXI_TURN_TICKS
        jr      fsw_g_store$
    fsw_g_same$:                        ; accelerate while speed < 205 (signed)
        bit     7, h
        jr      nz, fsw_g_accel$
        ld      a, h
        or      a, a
        jr      nz, fsw_g_idle$
        ld      a, l
        cp      a, #205
        jr      nc, fsw_g_idle$
    fsw_g_accel$:
        inc     15 (iy)
        ld      a, 15 (iy)
        cp      a, #5                   ; FLIGHT_GROUND_ACCEL_TICKS
        jr      nz, fsw_g_store$
        ld      15 (iy), #0
        inc     hl
        jr      fsw_g_store$
    fsw_g_idle$:
        ld      15 (iy), #0
        ld      a, c
        or      a, a
        call    z, fsw_approach0$       ; no horizontal input: coast down
    fsw_g_store$:
        call    fsw_store_vx$
        jp      fsw_world$

        ; ---- airborne / stall ----
    fsw_air$:
        ld      a, c
        or      a, a
        jr      z, fsw_a_nohoriz$
        ld      a, 13 (iy)
        or      a, a
        jr      nz, fsw_a_climb$
        call    fsw_leftflag$
        cp      a, 11 (iy)
        jr      z, fsw_a_climb$
        ld      a, 11 (iy)              ; start a turn: target_left = !facing
        or      a, a
        ld      a, #0
        jr      nz, fsw_a_target$
        inc     a
    fsw_a_target$:
        ld      14 (iy), a
        ld      13 (iy), #110           ; FLIGHT_TURN_TICKS
    fsw_a_climb$:
        ld      a, b
        ld      de, #-96
        cp      a, #1
        jr      z, fsw_a_climbset$
        ld      de, #96
        cp      a, #4
        jr      z, fsw_a_climbset$
        ld      de, #0
    fsw_a_climbset$:
        ld      (_g_FlightStepClimb), de
        ld      de, #205
        ld      a, #1                   ; FLIGHT_AIRBORNE
        jr      fsw_a_mode$
    fsw_a_nohoriz$:
        ld      a, b
        cp      a, #1
        jr      nz, fsw_a_notup$
        ld      de, #32
        ld      (_g_FlightStepClimb), de
        ld      a, #2                   ; FLIGHT_STALL, target 32
        jr      fsw_a_mode$
    fsw_a_notup$:
        or      a, a
        jr      nz, fsw_a_dive$
        ld      a, 12 (iy)
        cp      a, #3
        jr      z, fsw_a_dive$
        ld      de, #0
        ld      (_g_FlightStepClimb), de
        ld      de, #154
        ld      a, #1                   ; FLIGHT_AIRBORNE
        jr      fsw_a_mode$
    fsw_a_dive$:
        ld      de, #48
        ld      (_g_FlightStepClimb), de
        ld      de, #154
        ld      a, #3                   ; FLIGHT_STALL_DIVE (latched)
    fsw_a_mode$:
        ld      12 (iy), a
        ld      a, 13 (iy)
        or      a, a
        jr      z, fsw_a_speed$
        push    hl                      ; turning: climb += 64
        ld      hl, (_g_FlightStepClimb)
        ld      bc, #64
        add     hl, bc
        ld      (_g_FlightStepClimb), hl
        pop     hl
        dec     13 (iy)
        jr      nz, fsw_a_speed$
        ld      a, 14 (iy)
        ld      11 (iy), a              ; facing_left = target_left
    fsw_a_speed$:
        call    fsw_approach$           ; speed = Approach(speed, target)
        call    fsw_store_vx$
        ld      l, 8 (iy)
        ld      h, 9 (iy)
        ld      de, (_g_FlightStepClimb)
        call    fsw_approach$           ; vy = Approach(vy, climb)
        ld      8 (iy), l
        ld      9 (iy), h
        ld      a, h                    ; y32 = (int32)y + vy -> H L D E
        rla
        sbc     a, a
        ld      c, a
        ld      a, 2 (iy)
        add     a, l
        ld      e, a
        ld      a, 3 (iy)
        adc     a, h
        ld      d, a
        ld      a, 4 (iy)
        adc     a, c
        ld      l, a
        ld      a, 5 (iy)
        adc     a, c
        ld      h, a
        bit     7, h
        jr      z, fsw_y_nonneg$
        xor     a, a                    ; above the top: y = 0, vy = 0
        ld      2 (iy), a
        ld      3 (iy), a
        ld      4 (iy), a
        ld      5 (iy), a
        ld      8 (iy), a
        ld      9 (iy), a
        jr      fsw_world$
    fsw_y_nonneg$:
        ld      a, 9 (iy)               ; only while vy > 0
        bit     7, a
        jr      nz, fsw_y_store$
        or      a, 8 (iy)
        jr      z, fsw_y_store$
        ld      a, #0x00                ; FLIGHT_MAX_Y = 0x0004B000
        sub     a, e
        ld      a, #0xb0
        sbc     a, d
        ld      a, #0x04
        sbc     a, l
        ld      a, #0x00
        sbc     a, h
        jr      nc, fsw_y_store$
        ld      de, #0xb000
        ld      hl, #0x0004
        xor     a, a
        ld      8 (iy), a
        ld      9 (iy), a
    fsw_y_store$:
        ld      2 (iy), e
        ld      3 (iy), d
        ld      4 (iy), l
        ld      5 (iy), h

        ; ---- horizontal world position ----
    fsw_world$:
        pop     de                      ; DE = x pointer
        ld      a, 12 (iy)              ; leftward takeoff from the deck
        or      a, a
        jr      nz, fsw_w_next$
        or      a, 13 (iy)
        jr      nz, fsw_w_next$
        or      a, 11 (iy)
        jr      z, fsw_w_next$
        ld      a, (_g_FlightStepInput)
        ld      c, a
        and     a, #0x0a
        cp      a, #8
        jr      nz, fsw_w_next$
        ld      a, c
        and     a, #0x05
        cp      a, #1
        jr      nz, fsw_w_next$
        ld      l, 6 (iy)               ; vx <= -154
        ld      h, 7 (iy)
        ld      bc, #154
        add     hl, bc
        bit     7, h
        jr      nz, fsw_w_fast$
        ld      a, h
        or      a, l
        jr      nz, fsw_w_next$
    fsw_w_fast$:
        ld      h, d                    ; (*x >> 8) <= 6657 (0x1A01)
        ld      l, e
        inc     hl
        ld      c, (hl)
        inc     hl
        ld      b, (hl)
        inc     hl
        ld      a, (hl)
        or      a, a
        jr      nz, fsw_w_next$
        ld      a, #0x01
        sub     a, c
        ld      a, #0x1a
        sbc     a, b
        jr      c, fsw_w_next$
        ld      12 (iy), #1             ; FLIGHT_AIRBORNE
    fsw_w_next$:
        ld      a, 7 (iy)               ; next = (int32)*x + vx -> H L E C
        rla
        sbc     a, a
        ld      b, a
        ex      de, hl                  ; HL = x pointer
        push    hl
        ld      a, (hl)
        add     a, 6 (iy)
        ld      c, a
        inc     hl
        ld      a, (hl)
        adc     a, 7 (iy)
        ld      e, a
        inc     hl
        ld      a, (hl)
        adc     a, b
        ld      d, a
        inc     hl
        ld      a, (hl)
        adc     a, b
        ld      h, a
        ld      l, d
        ld      a, 12 (iy)
        or      a, a
        jr      nz, fsw_w_bounds$
        bit     7, h                    ; ground: next < 6617 * 256 (0x0019D900)?
        jr      nz, fsw_w_gmin$
        ld      a, c
        sub     a, #0x00
        ld      a, e
        sbc     a, #0xd9
        ld      a, l
        sbc     a, #0x19
        ld      a, h
        sbc     a, #0x00
        jr      nc, fsw_w_gmax$
    fsw_w_gmin$:
        ld      c, #0x00
        ld      e, #0xd9
        ld      hl, #0x0019
        call    fsw_stop_ground$
    fsw_w_gmax$:                        ; ground: next > 7336 * 256 (0x001CA800)?
        ld      a, #0x00
        sub     a, c
        ld      a, #0xa8
        sbc     a, e
        ld      a, #0x1c
        sbc     a, l
        ld      a, #0x00
        sbc     a, h
        jr      nc, fsw_w_bounds$
        ld      c, #0x00
        ld      e, #0xa8
        ld      hl, #0x001c
        call    fsw_stop_ground$
    fsw_w_bounds$:
        bit     7, h                    ; next < 0
        jr      z, fsw_w_max$
        ld      hl, #0
        ld      e, l
        ld      c, l
        xor     a, a
        ld      6 (iy), a
        ld      7 (iy), a
    fsw_w_max$:                         ; next > g_FlightWorldMax
        ld      a, (_g_FlightWorldMax + 0)
        sub     a, c
        ld      a, (_g_FlightWorldMax + 1)
        sbc     a, e
        ld      a, (_g_FlightWorldMax + 2)
        sbc     a, l
        ld      a, (_g_FlightWorldMax + 3)
        sbc     a, h
        jr      nc, fsw_w_store$
        ld      a, (_g_FlightWorldMax + 0)
        ld      c, a
        ld      a, (_g_FlightWorldMax + 1)
        ld      e, a
        ld      hl, (_g_FlightWorldMax + 2)
        xor     a, a
        ld      6 (iy), a
        ld      7 (iy), a
    fsw_w_store$:
        ex      (sp), hl                ; HL = x pointer, stack = next bytes 3..2
        ld      (hl), c
        inc     hl
        ld      (hl), e
        inc     hl
        pop     de
        ld      (hl), e
        inc     hl
        ld      (hl), d
        pop     iy
        pop     hl                      ; return address
        pop     af                      ; drop input and sample_pose
        jp      (hl)

        ; ---- helpers ----
    fsw_stop_ground$:                   ; vx = 0, ground_tick = 0
        xor     a, a
        ld      6 (iy), a
        ld      7 (iy), a
        ld      15 (iy), a
        ret
    fsw_leftflag$:                      ; A = (C == FLIGHT_LEFT), preserves HL
        ld      a, c
        cp      a, #8
        ld      a, #0
        ret     nz
        inc     a
        ret
    fsw_store_vx$:                      ; vx = facing_left ? -HL : HL
        ld      a, 11 (iy)
        or      a, a
        jr      z, fsw_store_pos$
        xor     a, a
        sub     a, l
        ld      l, a
        sbc     a, a
        sub     a, h
        ld      h, a
    fsw_store_pos$:
        ld      6 (iy), l
        ld      7 (iy), h
        ret
    fsw_approach0$:                     ; HL = Approach(HL, 0)
        ld      de, #0
    fsw_approach$:                      ; HL = Approach(HL = value, DE = target)
        push    de
        ex      de, hl                  ; HL = target, DE = value
        or      a, a
        sbc     hl, de                  ; HL = target - value
        jr      z, fsw_ap_value$
        jp      m, fsw_ap_above$
        ld      a, h                    ; value below target
        or      a, a
        jr      nz, fsw_ap_add5$
        ld      a, l
        cp      a, #5
        jr      nc, fsw_ap_add5$
        pop     hl                      ; within 5: snap to target
        ret
    fsw_ap_add5$:
        ex      de, hl
        ld      de, #5
        add     hl, de
        pop     de
        ret
    fsw_ap_above$:                      ; value above target: HL = -(value - target)
        ld      a, h
        inc     a
        jr      nz, fsw_ap_sub5$
        ld      a, l
        cp      a, #0xfc                ; value - target < 5 <=> HL >= -4
        jr      c, fsw_ap_sub5$
        pop     hl
        ret
    fsw_ap_sub5$:
        ex      de, hl
        ld      de, #-5
        add     hl, de
        pop     de
        ret
    fsw_ap_value$:
        ex      de, hl
        pop     de
        ret
    __endasm;
}
