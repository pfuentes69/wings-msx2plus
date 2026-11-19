set extra_symbols {g_Planes}
source [file join $env(WINGS_ROOT) tools smoke_lib.tcl]
# Enemy planes have their own verifier (docs/enemy-planes.md); the P0's
# pixel model does not know them: keep the torpedo-plane timer (g_Planes
# +152) at 0, so none comes.
no_torpedo_planes
proc ready {} {
    if {[value g_Ready]!=1 || [view 2]!=3 || [view 4]!=30} {after time 0.05 ready;return}
    require [expr {[view 0]==0 && [view 2]==3 && [view 4]==30}] "New game state"
    set ::armed 1
    dump debugdevices.txt [debug list]
    snap rank {pulse 8 32 {cursor 7 {pulse 7 128 {phase 5 load_menu}}}}
}
proc load_menu {} {snap load_menu {pulse 7 128 {phase 0 choose_rank}}}
proc choose_rank {} {pulse 8 64 {pulse 8 64 {cursor 2 {pulse 7 128 {phase 1 brief}}}}}
proc brief {} {
    require [expr {[view 1]==2}] "Rank selection"
    snap briefing {keymatrixdown 4 8; phase 2 {after time 0.3 hold_confirm}}
}
proc hold_confirm {} {
    require [expr {[view 0]==2 && [stat 32]==0}] "Secondary confirmation leaked: phase=[view 0] stock=[view 4] fired=[stat 32]"
    keymatrixup 4 8
    # The weapon panel's order: Rockets, Bombs, Torpedo (up from bombs).
    after time 0.1 {pulse 8 32 {cursor 1 rockets}}
}
proc notice {then} {
    if {[view 7]==1} {after time 0.05 $then} else {after time 0.025 [list notice $then]}
}
proc rockets {} {
    require [expr {[view 3]==1 && [view 4]==15}] "Rocket inventory"
    # Rockets are playable: no confirmation here. The wait keeps the old
    # confirmation's 0.85 s, so the flights after it keep their timing.
    snap rockets {after time 0.85 {pulse 8 32 {cursor 2 torpedo}}}
}
proc torpedo {} {
    require [expr {[view 3]==2 && [view 4]==1}] "Torpedo inventory"
    # The torpedo is playable: no confirmation here (the wait keeps the old
    # confirmation's 0.8 s, so the flights after it keep their timing).
    snap torpedo {after time 0.8 {pulse 8 32 {cursor 0 loadout}}}
}
proc loadout {} {snap loadout {keymatrixdown 6 4; phase 3 held_start}}
proc held_start {} {
    if {[view 0]!=3} {after time 0.05 held_start;return}
    require [expr {[view 4]==30 && [stat 32]==0 && [stat 30]==0}] "Held GRAPH leaked into flight"
    keymatrixup 6 4
    lift_pose lift_start 0 31 {lift_pose lift_rise_24 0 24 {lift_pose lift_rise_16 0 16 {lift_pose lift_rise_8 0 8 {wait_lift_up {snap start deck_smoke}}}}}
}
# Smoke over the carrier's overlay columns (signalmen 6958.., elevator
# 7004..7068), some low enough to cross the overlay rows: drawn, then erased
# without leftovers once the puffs burn out (2.8 s). Puffs: x, y, xf, yf,
# vx, vy, stage, life.
proc deck_smoke {} {
    set bytes {}
    foreach {x y vx vy} {6936 1090 0 255  6950 1140 128 0  6990 1120 255 128  7000 1150 64 64  7030 1100 200 30  7040 1145 0 0  6960 1130 90 200  7010 1080 30 90} {
        append bytes [binary format sscccccc $x $y 0 0 $vx $vy 5 6]
    }
    debug write_block memory $::addr(g_Smoke) $bytes
    after time 1.0 {set ::wanted_smoke 4;snap deck_smoke_live {after time 2.4 {snap deck_smoke_cleared {deck_height 0}}}}
}
# P1 release: use ordinary keyboard controls to roll from the parked position.
proc deck_height {height} {
    set ::wanted_height $height
    snap deck_$height [expr {$height<2 ? "deck_height [expr {$height+1}]" : "service_left_start"}]
}
proc service_left_start {} {
    # Spend an actual bomb while moving slightly on the platform: a moving
    # aircraft is not elevator-eligible. Stop within the boarding tolerance.
    keymatrixdown 8 16
    after time 0.3 {keymatrixdown 4 8}
    after time 0.4 {keymatrixup 4 8;keymatrixup 8 16}
    after time 0.9 service_left_lower
}
proc service_left_lower {} {
    require [expr {[view 4]==29 && [value g_Carrier]==1}] "No actual secondary spent before service"
    keymatrixdown 8 1
    lift_pose lift_left_down_8 2 8 {keymatrixup 8 1;pause_lift}
}
proc pause_lift {} {
    pulse 7 4 {phase 4 lift_pause_capture}
}
proc lift_pause_capture {} {
    snap lift_paused {after time 0.4 lift_pause_capture_wait}
}
proc lift_pause_capture_wait {} {
    snap lift_pause_wait {pulse 7 4 {phase 3 lift_resume}}
}
proc lift_resume {} {
    lift_pose lift_left_down_16 2 16 {lift_pose lift_left_down_24 2 24 {lift_pose lift_left_inside 3 32 {phase 7 service_left_menu}}}
}
proc service_left_menu {} {
    require [expr {[view 4]==30 && [stat 30]==0 && [stat 32]==0}] "Service did not reload or elevator fired weapons"
    snap service_left {pulse 8 32 {cursor 1 {require [expr {[view 0]==7 && [view 4]==15}] "Service rocket preview";after time 0.85 {pulse 8 64 {cursor 0 {pulse 7 128 {phase 3 {lift_pose lift_left_up_24 0 24 {lift_pose lift_left_up_8 0 8 {wait_lift_up service_left_return}}}}}}}}}}
}
proc service_left_return {} {
    require [expr {[value g_SelectedFrame]==52 && [view 4]==30}] "Left heading lost across service"
    snap lift_left_return {keymatrixdown 8 128;service_turn_right}
}
proc service_turn_right {} {
    if {[value g_Turning] || [value g_SelectedFrame]!=51} {after time 0.025 service_turn_right;return}
    keymatrixup 8 128
    after time 0.3 service_right_lower
}
proc service_right_lower {} {
    keymatrixdown 4 8
    lift_pose lift_right_down_8 2 8 {keymatrixup 4 8;lift_pose lift_right_down_24 2 24 {lift_pose lift_right_inside 3 32 {phase 7 service_right_menu}}}
}
proc service_right_menu {} {
    snap service_right {keymatrixdown 8 1;phase 3 {lift_pose lift_right_up_24 0 24 {lift_pose lift_right_up_8 0 8 {wait_lift_up service_right_return}}}}
}
proc service_right_return {} {
    require [expr {[value g_SelectedFrame]==51 && [view 4]==30 && [value g_Carrier]==1 && [stat 30]==0}] "Right heading lost or held confirmation leaked"
    keymatrixup 8 1
    snap lift_right_return {keymatrixdown 8 16;service_turn_left}
}
proc service_turn_left {} {
    if {[value g_Turning] || [value g_SelectedFrame]!=52} {after time 0.025 service_turn_left;return}
    keymatrixup 8 16
    after time 0.3 taxi_start
}
proc taxi_start {} {
    # Turn round on the deck at rest (the original's on-deck turn): capture
    # each new pose, then stop facing right; then the same back to the left.
    set ::taxi_n 0;set ::last_turn_pose -1;set ::turn_seen 0
    set ::wanted_turn 1;set ::turn_done taxi_right_end
    keymatrixdown 8 128
    taxi_more right
}
proc taxi_more {direction} {
    snap taxi_${direction}_[incr ::taxi_n] [list taxi_more $direction]
}
proc taxi_right_end {} {
    keymatrixup 8 128
    wait_for {[world_byte 13]==0 && [speed]==0} {
        require [expr {[word g_DisplayY]==1160 && ![world_byte 11]}] "Deck turn changed height or heading"
        set ::wanted_frame 51
        snap taxi_right_stop {
            set ::taxi_n 0;set ::last_turn_pose -1;set ::turn_seen 0
            set ::wanted_turn 1;set ::turn_done taxi_left_end
            keymatrixdown 8 16
            taxi_more left
        }
    } "deck turn right" 5
}
proc taxi_left_end {} {
    keymatrixup 8 16
    wait_for {[world_byte 13]==0 && [speed]==0} {
        require [expr {[word g_DisplayY]==1160 && [world_byte 11]}] "Deck turn changed height or heading"
        set ::wanted_frame 52
        snap taxi_left_stop taxi_restart
    } "deck turn left" 5
}
proc taxi_restart {} {
    keymatrixdown 6 2;keymatrixdown 4 128
    after time 0.15 {keymatrixup 4 128;keymatrixup 6 2}
    after time 0.3 {after_game {pulse 7 128 {phase 1 {pulse 7 128 {phase 2 {pulse 7 128 {phase 3 {wait_lift_up launch_roll}}}}}}}}
}
# Flight from the release controls; the original model runs once per 12
# simulation steps (12.5 Hz). Keyboard row 8: 1 space, 16 left, 32 up,
# 64 down, 128 right.
proc launch_roll {} {
    require [expr {[word g_DisplayWorld]==7032 && [word g_DisplayY]==1160}] "Deck start placement"
    fly 16
    snap slow_roll {after time 4.1 accelerating_roll}
}
proc accelerating_roll {} {
    require [expr {[value g_SelectedFrame]==52 && [speed]<600 && [speed]>200}] "Tail down while accelerating: speed=[speed]"
    snap accelerating_roll {wait_for {[world_byte 17]} {set ::wanted_frame 16;snap ground_roll lift_off} "tail up" 5}
}
proc lift_off {} {
    # Rolled off the bow below flying speed: climb away; the plane dips first.
    wait_for {[world_byte 12]==1} {set ::lowest_y 0;fly 48;takeoff_watch} "leave the deck" 8
}
proc takeoff_watch {} {
    if {[world_y]>$::lowest_y} {set ::lowest_y [world_y]}
    if {[world_y]>=1150} {after time 0.01 takeoff_watch;return}
    require [expr {$::lowest_y<1180 && [world_x]<6593}] "Takeoff dipped too low: y=$::lowest_y"
    puts $::report "takeoff lowest_y=$::lowest_y speed=[speed]"
    snap takeoff {pilot 16 800;wait_for {[world_x]<5900 && abs([world_y]-800)<12} turn_start "climb out" 20}
}
proc turn_start {} {
    pilot_off
    set ::turn_y [world_y]
    fly 128
    wait_for {[world_byte 13]>2} {set ::wanted_frame [turn_shapes];snap turn turn_wait} "bank" 3
}
proc turn_wait {} {
    wait_for {![world_byte 13] && ![world_byte 11]} turn_end "turn right" 8
}
proc turn_end {} {
    require [expr {[world_y]>$::turn_y}] "A turn must lose height: y=[world_y] before=$::turn_y"
    snap turn_complete {set ::compensate_y [world_y];fly 48;wait_for {[world_byte 13]>2} compensated_wait "bank back" 3}
}
proc compensated_wait {} {
    wait_for {![world_byte 13] && [world_byte 11]} compensated_turn "turn left" 8
}
proc compensated_turn {} {
    require [expr {[world_y]<$::compensate_y}] "Climbing through the turn must gain height"
    snap compensated_turn {pilot 16 700;wait_for {abs([world_y]-700)<10 && [climb]==0} stall_start "level off" 10}
}
proc stall_start {} {
    pilot_off
    require [expr {[world_x]<5700}] "Stall test too close to the carrier: x=[world_x]"
    fly 32
    set ::wanted_frame 43
    snap stall_held {set ::stall_y [world_y];after time 0.4 stall_sink}
}
proc stall_sink {} {
    require [expr {[world_y]>$::stall_y && [speed]>=1000}] "Held stall must sink with the nose up, keeping airspeed"
    fly 0
    set ::wanted_frame 16
    snap stall_released {
        # A complete tap while the foreground is held must still start a dive.
        debug write memory $::addr(g_HoldFlight) 1
        keymatrixdown 8 64
        after time 0.06 {keymatrixup 8 64}
        after time 0.12 {debug write memory $::addr(g_HoldFlight) 0}
        after time 0.7 dive_latched
    }
}
proc dive_latched {} {
    set ::dive_pose [value g_SelectedFrame]
    require [expr {$::dive_pose in {44 45 46} && [climb]<0}] "A Down tap must start a dive: pose=$::dive_pose climb=[climb]"
    set ::dive_y [world_y]
    snap dive_released {after time 0.5 dive_persists}
}
proc dive_persists {} {
    require [expr {[value g_SelectedFrame]==$::dive_pose && [world_y]>$::dive_y}] "Dive did not persist after release"
    snap dive_persistent {fly 32;wait_for {[climb]>=0} {fly 0;set ::wanted_frame 16;snap dive_recovered {fly 48;wait_for {[world_y]<400} head_right "climb" 15}} "recover" 3}
}
proc enter_in_flight {} {
    require [expr {[stat 32]==0 && [stat 30]==0 && [view 4]==30}] "Enter fired a weapon"
    keymatrixdown 8 1
    after time 8.5 gun_end
}
proc gun_end {} {
    keymatrixup 8 1
    require [expr {[stat 30]>30 && [view 4]==30}] "Gun limit or secondary stock coupling"
    snap guns {keymatrixdown 4 8; after time 0.1 {keymatrixdown 6 4}; after time 1 {keymatrixup 4 8}; after time 1.8 {keymatrixup 6 4};after time 2.2 aliases_end}
}
proc aliases_end {} {
    keymatrixup 6 4
    set ::alias_bombs [stat 32]
    require [expr {$::alias_bombs>=7 && $::alias_bombs<=9 && [view 4]==30-$::alias_bombs}] "Held aliases: drops=$::alias_bombs stock=[view 4]"
    snap aliases {after time 0.12 buffered_press}
}
proc buffered_press {} {
    # Suspend the foreground while VBlank still samples a press and release.
    debug write memory $::addr(g_HoldFlight) 1
    keymatrixdown 4 8
    after time 0.04 {keymatrixdown 6 4}
    after time 0.06 {keymatrixup 4 8}
    after time 0.08 {keymatrixup 6 4}
    after time 0.12 {debug write memory $::addr(g_HoldFlight) 0}
    after time 0.5 short_end
}
proc short_end {} {
    require [expr {[view 4]==29-$::alias_bombs && [stat 32]==$::alias_bombs+1}] "Short secondary press lost during foreground stall"
    snap short_press {pulse 7 4 {phase 4 paused}}
}
proc paused {} {snap paused {pulse 8 1 {pulse 4 8 {pulse 6 4 {pulse 7 128 pause_wait}}}}}
proc pause_wait {} {
    require [expr {[view 0]==4 && [view 4]==29-$::alias_bombs && [stat 32]==$::alias_bombs+1}] "Non-ESC key resumed or fired"
    snap pause_wait {keymatrixdown 6 2;keymatrixdown 3 8;after time 0.08 {keymatrixup 3 8;keymatrixup 6 2};after time 0.4 inverted}
}
proc inverted {} {
    require [expr {[view 5]==1 && [view 0]==4}] "Ctrl-F inversion"
    snap inverted {pulse 7 4 {phase 3 resumed}}
}
proc resumed {} {
    set ::climb_y [word g_DisplayY]
    snap resumed {keymatrixdown 8 160; after time 0.45 {keymatrixup 8 160};after time 1.6 debug_keys}
}
proc debug_keys {} {
    set ::before_y [word g_DisplayY]
    require [expr {$::before_y<$::climb_y}] "Keyboard arrows incorrectly inverted with joystick"
    keymatrixdown 4 128;keymatrixdown 5 2
    after time 0.4 {keymatrixup 4 128;keymatrixup 5 2}
    after time 0.65 no_debug
}
proc no_debug {} {
    require [expr {[word g_DisplayY]==$::before_y && ![value g_Turning]}] "Debug controls enabled in release profile"
    snap no_debug {
        set ::gun_before [stat 30];set ::joy 47
        after time 0.8 {set ::joy 63}
        after time 1.1 joy_guns
    }
}
proc joy_guns {} {
    require [expr {[stat 30]>$::gun_before && [view 4]==29-$::alias_bombs}] "Native trigger 1"
    snap joystick_guns {
        set ::joy_bomb_before [stat 32]
        set ::joy 31;keymatrixdown 4 8;keymatrixdown 6 4
        after time 0.2 {keymatrixup 4 8;keymatrixup 6 4}
        after time 2.2 {set ::joy 63}
        after time 2.5 joy_secondary
    }
}
proc joy_secondary {} {
    require [expr {[stat 32]-$::joy_bomb_before>=9 && [stat 32]-$::joy_bomb_before<=11 && [view 4]==30-[stat 32]}] "Native trigger 2 repeat/alias aggregation: drops=[stat 32] before=$::joy_bomb_before"
    set ::joy 63;set ::joy_stock [view 4]
    snap joystick_secondary {set ::joy_y [word g_DisplayY];set ::joy 62;after time 0.5 {set ::joy 63};after time 1.2 joy_inverted}
}
proc joy_inverted {} {
    require [expr {[word g_DisplayY]>$::joy_y}] "Joystick vertical inversion"
    snap joystick_inverted {keymatrixdown 6 2;keymatrixdown 4 2;after time 0.15 {keymatrixup 4 2;keymatrixup 6 2};phase 5 in_game_load}
}
proc in_game_load {} {
    require [expr {[view 4]==$::joy_stock}] "Load shell changed stock"
    snap in_game_load {pulse 7 4 {phase 3 {keymatrixdown 6 2;keymatrixdown 3 16;after time 0.15 {keymatrixup 3 16;keymatrixup 6 2};phase 6 in_game_save}}}
}
proc in_game_save {} {
    require [expr {[view 4]==$::joy_stock}] "Save shell changed stock"
    snap in_game_save {pulse 7 128 {phase 3 prepare_approach}}
}
proc head_right {} {
    # The gun, pause and joystick tests fly level for a long while: head
    # right so the plane stays inside the map.
    pilot 128 400
    wait_for {![world_byte 11] && ![world_byte 13] && abs([world_y]-400)<8 && [climb]==0} {pilot_off;after time 1 {pulse 7 128 enter_in_flight}} "head right" 20
}
proc prepare_approach {} {
    # Recover the dive from the inverted joystick test and fly back left.
    # Cannon tests fly low (the flash is drawn only in the near view, below
    # 186 px) over open sea: islands end at x 3928 and the gear comes down
    # past 5752.
    pilot 16 1060
    wait_for {[world_x]<5600 && [world_byte 11] && ![world_byte 13] && abs([world_y]-1060)<9 && abs([climb])<=600} {pilot_off;cannon 41 cannon_climb_left} "recover for cannon tests" 40
}
# Fire in a climb (pitch 1), level and in a dive (pitch 7), each heading.
proc cannon {pose name} {
    set heading [expr {[world_byte 11] ? 16 : 128}]
    set attitude [lindex [split $name _] 1]
    # A held dive steps 600 a tick, two ticks a frame on PAL, so a single
    # dive pose can be skipped: accept the middle three (the flash art is
    # checked for whichever is drawn).
    if {$attitude eq "climb"} {fly [expr {$heading|32|1}]} elseif {$attitude eq "level"} {fly 1} else {fly [expr {$heading|64|1}]}
    set ::wanted_frame $pose
    snap $name [list cannon_next $name]
}
proc cannon_next {name} {
    switch $name {
        cannon_climb_left {cannon 16 cannon_level_left}
        cannon_level_left {cannon {45 46 47} cannon_dive_left}
        cannon_dive_left {cannon_settle 16 {pilot 128 1060;wait_for {![world_byte 11] && ![world_byte 13] && abs([world_y]-1060)<9 && abs([climb])<=600} {pilot_off;cannon 1 cannon_climb_right} "turn for cannon tests" 15}}
        cannon_climb_right {cannon 4 cannon_level_right}
        cannon_level_right {cannon {6 7 8} cannon_dive_right}
        cannon_dive_right {cannon_settle 128 island_run}
    }
}
proc cannon_settle {heading then} {
    pilot $heading 1060
    wait_for {abs([world_y]-1060)<9 && abs([climb])<=600} "pilot_off;$then" "level after firing" 15
}
# P3 island targets: fly left over island A low and carpet-bomb until the
# hut at x 2392 is wrecked (g_Island: hut records of 8 bytes, wrecked +3).
proc island_wrecked {hut} {debug read memory [expr {$::addr(g_Island)+8*$hut+3}]}
# Soldiers drawn: a walker, a dying soldier and a corpse (facing left) put
# in front of the camera (g_Island soldiers at +162, 7 bytes: x, dir, frame,
# delay, state, base; out +304, alive +305, tick +306, wait +307).
proc island_soldiers {} {
    set base [expr {$::addr(g_Island)+162}]
    set cam [word g_DisplayCamera]
    set tick [debug read memory [expr {$::addr(g_Island)+306}]]
    set i 15
    foreach {dx dir frame delay state} {70 1 0 200 1  120 1 6 2 2  170 -1 8 0 3} {
        debug write_block memory [expr {$base+7*$i}] [binary format sccccc [expr {$cam+$dx}] $dir $frame $delay $state $tick]
        incr i
    }
    # out += 3, alive += 2, nothing waiting.
    debug write memory [expr {$::addr(g_Island)+304}] [expr {[debug read memory [expr {$::addr(g_Island)+304}]]+3}]
    debug write memory [expr {$::addr(g_Island)+305}] [expr {[debug read memory [expr {$::addr(g_Island)+305}]]+2}]
    debug write memory [expr {$::addr(g_Island)+307}] 0
    after time 0.3 {snap island_soldiers island_clear}
}
# Island cleared (0x3f5e): island A's last soldier dies with no gun left
# (soldiers[0] = 1 at +128, guns[0] = 0 at +132): bonus, flag down, and
# the message ticker at the top (src/msx/message.c). Capture it running,
# then fly on with it through the pan descent over the carrier.
proc island_clear {} {
    set base [expr {$::addr(g_Island)+162}]
    set tick [debug read memory [expr {$::addr(g_Island)+306}]]
    debug write_block memory [expr {$base+7*18}] [binary format sccccc [expr {[word g_DisplayCamera]+100}] 1 5 2 2 $tick]
    foreach {offset value} {128 1 132 0 307 0} {debug write memory [expr {$::addr(g_Island)+$offset}] $value}
    foreach offset {304 305} {debug write memory [expr {$::addr(g_Island)+$offset}] [expr {[debug read memory [expr {$::addr(g_Island)+$offset}]]+1}]}
    wait_for {[value g_DisplayBand] && [word g_DisplayTicker]>=300} {snap island_cleared {wait_for {[world_x]>5000} pan_climb "fly back from the island" 90}} "the island-cleared ticker" 10
}
proc island_run {} {
    game_byte 13 30;game_byte 15 192
    set ::score_before [expr {[value g_DisplayScore]}]
    pilot 16 1100
    wait_for {[world_x]<4300 && [world_byte 11] && abs([world_y]-1100)<9} island_coast "fly to the island" 90
}
proc island_coast {} {
    # Coast to speed 1000 (10 px a tick; x moves 17-20 px a frame): about
    # 1200 px from full speed.
    pilot 0 1100
    wait_for {[speed]<=1000 && abs([world_y]-1100)<9 && [climb]==0} island_bomb "coast over the island" 30
}
# Where a bomb released now bursts, relative to the plane: Combat_Advance's
# launch (Q2, plane velocity x 6 / 64, 4 px below) and Fall(), level flight.
proc bomb_offset {} {
    set v [world_vx];set vx [expr {$v<0 ? -((-$v*6)/64) : ($v*6)/64}]
    set x 0;set y [expr {([world_y]+4)*4}];set vy 0;set life 255
    while {$y<1188*4} {
        incr life -1;set age [expr {255-$life}]
        incr vy [expr {((($age+1)*3)>>3)-(($age*3)>>3)}]
        if {$age & 1} {
            set w [expr {$vx>>1}];set q [expr {abs($w)>=10 ? abs($w)/10 : 0}]
            if {$w<0} {incr vx [expr {2*$q}]} else {incr vx [expr {-2*$q}]}
        }
        incr x $vx;incr y $vy
    }
    return [expr {$x/4}]
}
proc island_bomb {} {
    # Bombs keep the plane's speed and fall for about 1.7 s from y 1100,
    # bursting well ahead, so a carpet of them can straddle a hut. Aim one
    # at the hut at 2392 ([2376, 2408)). The plane's x advances a frame at
    # a time (at most 20 px here); take the first sample inside the window.
    # Hold the simulation while the press is sampled so the bomb leaves at
    # the next weapon tick (5 px further on).
    require [expr {[world_x]>2600}] "Coasted past the aiming point: x=[world_x]"
    set ::bomb_dx [bomb_offset]
    puts $::report "bomb offset $::bomb_dx speed=[speed]"
    wait_for {[world_x]+$::bomb_dx<=2405} island_release "aim at the hut" 20
}
proc island_release {} {
    # The bomb's burst wrecks the hut: that frame renders in about 105 ms
    # on NTSC (the wrecked columns on both pages) and lands either side of
    # a VBlank (render 105 + sim ~75 against 10 VBlanks). One miss is
    # allowed from here until the turn back; docs/enemy-planes.md.
    set ::miss_budget 1
    debug write memory $::addr(g_HoldFlight) 1
    puts $::report "bomb release x=[world_x]"
    keymatrixdown 4 8
    after time 0.2 {keymatrixup 4 8}
    after time 0.4 {
        debug write memory $::addr(g_HoldFlight) 0
        after time 0.3 island_log_bombs
        wait_for {[island_wrecked 0]} island_hit "the bomb reaches the hut" 4
    }
}
proc island_log_bombs {} {
    for {set i 2} {$i<18} {incr i} {
        set b [expr {$::addr(g_Combat)+$i*8}]
        if {[debug read memory [expr {$b+7}]]} {
            puts $::report "bomb $i x=[expr {([debug read memory $b]+256*[debug read memory [expr {$b+1}]])/4}] y=[expr {([debug read memory [expr {$b+2}]]+256*[debug read memory [expr {$b+3}]])/4}] life=[debug read memory [expr {$b+6}]] plane=[world_x] stock=[view 4]"
        }
    }
}
proc island_hit {} {
    # The bomb bursts well behind the plane: turn back over the hut and
    # capture it wrecked and smoking.
    after time 1.0 {unset -nocomplain ::miss_budget}
    pilot 128 1060
    wait_for {![world_byte 11] && abs([world_x]-2400)<60} {set ::wanted_smoke 1;snap island_bombed island_soldiers} "turn back over the hut" 20
}
# The close-view pan (original 0x26e): between altitudes 131 and 186 the
# scene moves down with the plane. Climb into the distant view, then come
# down through the band over the carrier, dropping a bomb on the way.
proc pan_climb {} {
    pilot 128 990
    wait_for {[world_x]>6520 && [world_y]<1010} pan_descend "climb above the close view" 30
}
proc pan_descend {} {
    pilot 128 1062
    keymatrixdown 4 8;after time 0.05 {keymatrixup 4 8}
    # y 1014..1024: pan 45..55 (5..6 tile rows plus a fine scroll).
    set ::wanted_y {1014 1024}
    # The mid band (pan 14..32) is wider than a frame's descent here (up to
    # 17 px): a narrower one can fall between two published frames.
    snap pan_high {set ::wanted_y {1037 1055};snap pan_mid approach}
}
proc approach {} {
    # Gear comes down within 1280 px of the carrier, in either direction.
    pilot 128 1060
    wait_for {[world_x]>5900} {set ::wanted_frame 4;snap approach open_sea} "fly to the carrier" 60
}
proc open_sea {} {
    # Past the map's right end (7608) the ocean goes on and the camera keeps
    # the plane centred, as in the original.
    pilot 128 1060
    wait_for {[world_x]>7900} {snap open_sea_right {pilot_off;fly 1;keymatrixup 8 1;after time 0.3 mission_return}} "fly past the map end" 30
}
# P4: the island is cleared, so the mission is complete. Land, go down the
# lift, and the hold briefs the next mission instead of servicing the plane
# (0x0122); rank 0 has three, so no promotion yet. The loadout then starts a
# new sortie with the island restored. The landing reuses the circuit with
# the snapshots named return_*.
proc mission_return {} {
    require [expr {[debug read memory [expr {$::addr(g_Island)+314}]]==1}] "Mission not complete before the return"
    set ::mission_return 1
    set ::return_lives [view 2]
    # Head back over the carrier first: the circuit's outbound leg is timed
    # from a takeoff.
    pilot 16 1140
    wait_for {[world_x]<7000} {circuit land_flare} "fly back to the carrier" 20
}
proc sname {name} {expr {[info exists ::mission_return] ? "return_$name" : $name}}
proc mission_briefed {} {
    # g_Game: rank +6, lives +7, mission map +8, number +9.
    set rank [debug read memory [expr {$::addr(g_Game)+6}]]
    set map [debug read memory [expr {$::addr(g_Game)+8}]]
    set number [debug read memory [expr {$::addr(g_Game)+9}]]
    require [expr {$rank==0 && $number==2 && $map==1 && [view 2]==$::return_lives}] "Next mission: rank=$rank number=$number map=$map lives=[view 2] (was $::return_lives)"
    snap mission_briefing {pulse 7 128 {phase 2 {pulse 7 128 {phase 3 {wait_lift_up mission_two}}}}}
}
proc mission_two {} {
    require [expr {![island_wrecked 0] && [debug read memory [expr {$::addr(g_Island)+314}]]==0 && ![value g_MessageActive]}] "The next mission must restore the island"
    unset ::mission_return
    snap mission_two {after time 0.3 restart_game}
}
proc restart_game {} {
    fly 0
    keymatrixdown 6 2;keymatrixdown 4 136;after time 0.4 {keymatrixup 4 136;keymatrixup 6 2}
    after time 0.4 {after_game restarted}
}
proc restarted {} {
    require [expr {[view 2]==3 && [view 4]==30 && [view 5]==1 && [stat 30]==0 && [stat 32]==0}] "Ctrl-R game reset or setting retention"
    snap restart engine_new_game
}
# P2 engine: low fuel warning, dry tank, crash, next plane, game over.
# g_Game: lives at +7, fuel at +15. g_Engine: fuel_ticks +0, failed +3, lamps +8.
proc engine_new_game {} {
    pulse 7 128 {phase 1 {pulse 7 128 {phase 2 {pulse 7 128 {phase 3 {wait_lift_up {engine_takeoff engine_low_fuel}}}}}}}
}
proc engine_low_fuel {} {
    # The score field (no targets yet): the manual's example score, 20160.
    game_byte 0 [expr {20160 & 255}];game_byte 1 [expr {20160 >> 8}];game_byte 2 0;game_byte 3 0
    game_byte 15 60
    set ::lamps {}
    after time 1.4 engine_watch_lamp
}
proc engine_watch_lamp {} {
    lappend ::lamps [expr {[engine_byte 8] & 2}]
    if {[llength $::lamps] < 40} {after time 0.02 engine_watch_lamp;return}
    require [expr {[lsearch $::lamps 0]>=0 && [lsearch $::lamps 2]>=0}] "Fuel lamp did not blink: $::lamps"
    require [expr {[engine_byte 7]<=8}] "Fuel needle did not sweep down"
    snap engine_low_fuel engine_smoke
}
proc engine_smoke {} {
    # A damaged engine (oil 100 of 128) smokes: wait for a trail of puffs.
    game_byte 14 100
    set ::wanted_smoke 2
    snap engine_smoke {game_byte 14 128;after time 0.2 engine_dry}
}
proc engine_dry {} {
    game_byte 15 0
    debug write memory $::addr(g_Engine) 1
    after time 0.3 {require [expr {[engine_byte 3]==1}] "Dry tank did not fail the engine"; snap engine_failed engine_crash_wait}
}
proc engine_crash_wait {} {
    set ::crash_deadline [expr {[machine_info time]+12}]
    debug write memory $::addr(g_LastContact) 0
    engine_wait_splash
}
proc engine_wait_splash {} {
    require [expr {[machine_info time]<$::crash_deadline}] "Dead plane never reached the sea"
    if {[value g_LastContact]!=3} {after time 0.01 engine_wait_splash;return}
    after time 0.5 {
        require [expr {[value g_DisplayCrash]>=6 && [value g_DisplayCrash]!=255}] "Sea crash must show the splash art: frame=[value g_DisplayCrash]"
        snap engine_splash engine_wait_respawn
    }
}
# The next plane waits in the hold: the service arms it (the weapon is
# chosen again), then the lift brings it up.
proc engine_wait_respawn {} {
    require [expr {[machine_info time]<$::crash_deadline}] "Dead plane never crashed"
    if {[view 2]!=2 || [view 0]!=7} {after time 0.05 engine_wait_respawn;return}
    require [expr {[word g_DisplayWorld]==7032 && [value g_Carrier]==3}] "Next plane not in the hold: world=[word g_DisplayWorld] stage=[value g_Carrier]"
    require [expr {[view 6]==[view 3] && [view 4]==30}] "Service not offering the weapons: cursor=[view 6] weapon=[view 3] stock=[view 4]"
    require [expr {[debug read memory [expr {$::addr(g_Game)+15}]]==192 && [debug read memory [expr {$::addr(g_Game)+14}]]==128 && [engine_byte 3]==0}] "Next plane not refuelled and repaired"
    snap engine_next_plane {pulse 7 128 {phase 3 {wait_lift_up {engine_takeoff land_circuit}}}}
}
# Stopped on the elevator after a landing (tools/smoke_lib.tcl).
proc landed_on_lift {} {
    if {[info exists ::mission_return]} {pulse 8 1 {phase 1 mission_briefed};return}
    pulse 8 1 {phase 7 {snap landed_service {pulse 7 128 {phase 3 {wait_lift_up {engine_takeoff bounce_circuit}}}}}}
}
proc bounce_circuit {} {circuit bounce_dive}
proc bounce_dive {} {
    # Under power into the deck: no flare, so the plane bounces.
    debug write memory $::addr(g_LastContact) 0
    pilot 16 1166
    wait_for {[value g_LastContact]!=0} bounce_check "powered touchdown" 6
}
proc bounce_check {} {
    require [expr {[value g_LastContact]==2 && [world_byte 12]==1}] "Powered deck contact must bounce: contact=[value g_LastContact] x=[world_x] y=[world_y]"
    pilot 16 1120
    snap deck_bounce {after time 1.5 sea_dive}
}
proc sea_dive {} {
    pilot_off
    debug write memory $::addr(g_LastContact) 0
    set ::lives_before [view 2]
    wait_for {[world_x]<6560} {fly 80;wait_for {[value g_LastContact]==3} {after time 0.2 {snap sea_splash sea_wait}} "sea crash" 10} "clear the bow" 6
}
proc sea_wait {} {
    if {[view 2]==$::lives_before || [view 0]!=7} {after time 0.05 sea_wait;return}
    require [expr {[value g_LastContact]==3 && [view 2]==$::lives_before-1}] "Powered sea dive must crash and cost a plane"
    require [expr {[word g_DisplayWorld]==7032 && [value g_Carrier]==3}] "Next plane not in the hold"
    fly 0
    # The service arms the next plane; the lift brings it up.
    snap sea_crash_next {pulse 7 128 {phase 3 {wait_lift_up {engine_takeoff engine_last_plane}}}}
}
proc engine_last_plane {} {
    game_byte 7 1
    game_byte 15 0
    debug write memory $::addr(g_Engine) 1
    set ::crash_deadline [expr {[machine_info time]+12}]
    engine_wait_game_over
}
proc engine_wait_game_over {} {
    require [expr {[machine_info time]<$::crash_deadline}] "Last plane never crashed"
    if {[view 0]!=8} {after time 0.05 engine_wait_game_over;return}
    require [expr {[view 2]==0}] "Game over with planes remaining"
    snap game_over {after_game {require [expr {[view 2]==3}] "Game over did not reset"; done}}
}
after time 1 {guard ready}
after time 1500 {bgerror "P0 scenario timeout"}
