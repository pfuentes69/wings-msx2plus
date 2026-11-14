set save_settings_on_exit false
set mute true
if {$env(WINGS_HEADLESS) eq "0"} {set renderer SDLGL-PP}
set throttle false
set pause false
set power on
after realtime 0.1 {set power on; set pause false}
source [file join $env(WINGS_ROOT) tools pixel_display.tcl]
catch {unplug joyporta}
bind -layer codex_verification "keyb SPACE" {set ::ignored_host_input 1}
activate_input_layer -blocking codex_verification
foreach {r m} {3 24 4 138 5 2 6 6 7 132 8 255} {keymatrixup $r $m}
set out $env(WINGS_TEST_OUT)
set report [open [file join $out emulator-report.txt] w]
set sf [open [file join $env(WINGS_ROOT) out mission-flight mission-flight.noi] r]
set symbols [read $sf];close $sf
foreach n {Input_JoySample g_HudScore g_DisplayScore g_DisplaySmoke g_Island g_DisplayRope g_DisplayWheel g_DisplayGear g_DisplayCrash s_World g_LastContact g_DisplayGauges g_Engine g_Game g_Controls g_Ready g_GameView g_Combat g_FramePublished g_DisplayPage g_DisplayCamera g_DisplayWorld g_DisplayY g_SelectedFrame g_DisplayWave g_DisplayHeave g_DisplayShipFrame g_DisplayScale g_ViewChange g_VBlankTicks g_Carrier g_DisplayElevator g_CrewFrame g_TaxiTurn g_HoldFlight g_MissedFrames g_InputOverflow g_Turning g_Rendering g_RenderPage} {
    if {![regexp "DEF _$n (0x\[0-9A-Fa-f\]+)" $symbols -> a]} {error "Missing $n"}
    set addr($n) $a
}
# Inject digital levels at the PSG read boundary; exercises both native trigger
# bits through the actual ISR, OR mapping and queue, without a physical pad.
set joy 63
debug set_bp $addr(Input_JoySample) {} {reg A $::joy}
proc value {n} {debug read memory $::addr($n)}
proc word {n} {expr {[value $n]+256*[debug read memory [expr {$::addr($n)+1}]]}}
proc view {i} {debug read memory [expr {$::addr(g_GameView)+$i}]}
proc stat {offset} {incr offset 122;expr {[debug read memory [expr {$::addr(g_Combat)+$offset}]]+256*[debug read memory [expr {$::addr(g_Combat)+$offset+1}]]}}
proc require {ok message} {if {!$ok} {error $message}}
proc bgerror {m} {puts $::report "FAIL $m\n$::errorInfo";flush $::report;close $::report;exit}
proc guard {code} {if {[catch {uplevel #0 $code} m]} {bgerror $m}}
proc dump {name bytes} {set f [open [file join $::out $name] wb];puts -nonewline $f $bytes;close $f}
proc phase {wanted then} {
    if {[view 0]==$wanted} {after time 0.05 $then} else {after time 0.025 [list phase $wanted $then]}
}
proc cursor {wanted then} {
    if {[view 6]==$wanted} {after time 0.05 $then} else {after time 0.025 [list cursor $wanted $then]}
}
proc pulse {row mask then} {
    keymatrixdown $row $mask
    after time 0.05 [list keymatrixup $row $mask]
    after time 0.8 $then
}
proc snap {name then} {set ::pending [list $name $then]}
proc finish {name then} {
    if {$::env(WINGS_HEADLESS) eq "0"} {
        screenshot -raw [file join $::out $name.png]
        if {$name in {rank loadout start paused}} {screenshot [file join $::out $name-display.png]}
        set ::throttle false
    }
    unset ::capturing
    if {[string match "taxi_more *" $then] || [string match "lift_pose *" $then]} {
        uplevel #0 $then
        debug write memory $::addr(g_HoldFlight) 0
    } else {
        debug write memory $::addr(g_HoldFlight) 0
        after time 0.06 $then
    }
}
proc publishing {} {
    if {![info exists ::armed]} {return}
    if {[word g_MissedFrames]} {
        # Profiling aid (WINGS_ALLOW_MISSED=1): log misses instead of failing.
        if {[info exists ::env(WINGS_ALLOW_MISSED)]} {
            puts $::report "missed world=[word g_DisplayWorld] y=[word g_DisplayY] render=$::last_render"
            debug write memory $::addr(g_MissedFrames) 0
            debug write memory [expr {$::addr(g_MissedFrames)+1}] 0
        } else {error "Frame deadline missed: stage=[value g_Carrier] depth=[value g_DisplayElevator] pose=[value g_SelectedFrame] render=$::last_render"}
    }
    set now [machine_info time]
    set ::last_publish $now
    set stage [value g_Carrier]
    if {[view 0]==3 && $stage in {0 2}} {
        if {[info exists ::lift_last] && $::lift_stage==$stage && !$::lift_rebuild && ![value g_ViewChange]} {
            puts $::report "lift_cadence [expr {1000*($now-$::lift_last)}] $::last_render"
        }
        set ::lift_last $now;set ::lift_stage $stage;set ::lift_rebuild [value g_ViewChange]
    } else {unset -nocomplain ::lift_last}
    if {![info exists ::pending] || [info exists ::capturing]} {return}
    if {[info exists ::wanted_height]} {
        if {[value g_DisplayHeave]!=$::wanted_height} {return}
        unset ::wanted_height
    }
    if {[info exists ::wanted_frame]} {
        if {[value g_SelectedFrame] ni $::wanted_frame} {return}
        unset ::wanted_frame
    }
    if {[info exists ::wanted_smoke]} {
        if {[value g_DisplaySmoke]<$::wanted_smoke} {return}
        unset ::wanted_smoke
    }
    if {[info exists ::wanted_rope]} {
        # Mid-arrest, so the rope is well stretched.
        if {[value g_DisplayRope]==255 || [speed]>700} {return}
        unset ::wanted_rope
    }
    if {[info exists ::wanted_turn]} {
        # Capture each new deck-turn pose; when the turn ends, drop the
        # pending capture and continue.
        if {![value g_Turning]} {
            if {$::turn_seen} {unset ::pending ::wanted_turn;after time 0.05 $::turn_done}
            return
        }
        if {[value g_SelectedFrame]==$::last_turn_pose} {return}
        set ::last_turn_pose [value g_SelectedFrame];set ::turn_seen 1
    }
    if {[info exists ::wanted_depth]} {
        if {[value g_DisplayElevator]!=$::wanted_depth || [value g_Carrier]!=$::wanted_stage} {return}
        unset ::wanted_depth;unset ::wanted_stage
    }
    lassign $::pending name then;unset ::pending;set ::capturing 1
    foreach {suffix device address size} {vram VRAM 0 131072 regs {VDP regs} 0 32} {
        dump $name.$suffix [debug read_block $device $address $size]
    }
    dump $name.lift [debug read_block memory $::addr(g_Carrier) 3]
    dump $name.view [debug read_block memory $::addr(g_DisplayScale) 3]
    dump $name.crew [debug read_block memory $::addr(g_CrewFrame) 1]
    dump $name.gauges [debug read_block memory $::addr(g_DisplayGauges) 3]
    dump $name.flight [debug read_block memory $::addr(s_World) 37]
    dump $name.crash [debug read_block memory $::addr(g_DisplayCrash) 1]
    dump $name.wheel [binary format ccc [value g_DisplayWheel] [value g_DisplayGear] [value g_DisplayRope]]
    dump $name.smoke [debug read_block memory $::addr(g_DisplaySmoke) 41]
    dump $name.score [debug read_block memory $::addr(g_DisplayScore) 4]
    dump $name.island [debug read_block memory $::addr(g_Island) 136]
    dump $name.game [debug read_block memory $::addr(g_GameView) 8]
    dump $name.combat [debug read_block memory $::addr(g_Combat) 160]
    dump $name.rom [debug read_block memory 16384 32768]
    puts $::report "snapshot $name [value g_DisplayPage] [word g_DisplayWorld] [word g_DisplayY] [value g_SelectedFrame] [value g_DisplayWave] [value g_DisplayHeave] [value g_DisplayShipFrame] [word g_DisplayCamera]"
    debug write memory $::addr(g_HoldFlight) 1
    # Unthrottled openMSX skips rendering; let real frames render before the
    # raster screenshot (emulated timing is unaffected).
    if {$::env(WINGS_HEADLESS) eq "0"} {set ::throttle true}
    after time 0.08 [list finish $name $then]
}
proc rendering {} {
    if {![info exists ::armed]} {return}
    if {[value g_Rendering]} {
        set ::render_start [machine_info time]
        if {[info exists ::last_publish] && [stat 30]>0} {puts $::report "pre_render [expr {1000*($::render_start-$::last_publish)}]"}
        set ::visible_base [expr {[value g_DisplayPage]*32768}]
        require [expr {[value g_RenderPage]!=[value g_DisplayPage]}] "Rendering visible page: render=[value g_RenderPage] display=[value g_DisplayPage] phase=[view 0] pc=[format %04x [reg pc]] sp=[format %04x [reg sp]] ret=[format %04x [expr {[debug read memory [reg sp]]+256*[debug read memory [expr {[reg sp]+1}]]}]]"
        set ::pixels [debug read_block VRAM $::visible_base 27136]
    } elseif {[info exists ::pixels]} {
        set ::last_render [expr {1000*([machine_info time]-$::render_start)}]
        require [expr {$::pixels eq [debug read_block VRAM $::visible_base 27136]}] "Visible page changed during redraw"
        unset ::pixels
    }
}
proc missed_frame {} {
    if {![info exists ::last_publish]} {return}
    puts $::report "deadline elapsed=[expr {1000*([machine_info time]-$::last_publish)}] render=$::last_render stage=[value g_Carrier] world=[word g_DisplayWorld] vblank=[value g_VBlankTicks] viewchange=[value g_ViewChange] camera=[word g_DisplayCamera] scale=[value g_DisplayScale] y=[word g_DisplayY] hudscore=[debug read_block memory $::addr(g_HudScore) 8] score=[debug read_block memory $::addr(g_Game) 4]"
    flush $::report
}
debug watchpoint create -type write_mem -address $addr(g_FramePublished) -command {guard publishing}
debug watchpoint create -type write_mem -address $addr(g_Rendering) -command {guard rendering}
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
    after time 0.1 {pulse 8 64 {cursor 1 rockets}}
}
proc notice {then} {
    if {[view 7]==1} {after time 0.05 $then} else {after time 0.025 [list notice $then]}
}
proc rockets {} {
    require [expr {[view 3]==1 && [view 4]==15}] "Rocket inventory"
    snap rockets {pulse 7 128 {notice {require [expr {[view 0]==2 && [view 4]==15}] "Unavailable rocket consumed"; pulse 8 64 {cursor 2 torpedo}}}}
}
proc torpedo {} {
    require [expr {[view 3]==2 && [view 4]==1}] "Torpedo inventory"
    snap torpedo {pulse 7 128 {require [expr {[view 0]==2 && [view 4]==1}] "Unavailable torpedo consumed"; pulse 8 32 {pulse 8 32 {cursor 0 loadout}}}}
}
proc loadout {} {snap loadout {keymatrixdown 6 4; phase 3 held_start}}
proc held_start {} {
    if {[view 0]!=3} {after time 0.05 held_start;return}
    require [expr {[view 4]==30 && [stat 32]==0 && [stat 30]==0}] "Held GRAPH leaked into flight"
    keymatrixup 6 4
    lift_pose lift_start 0 31 {lift_pose lift_rise_24 0 24 {lift_pose lift_rise_16 0 16 {lift_pose lift_rise_8 0 8 {wait_lift_up {snap start {deck_height 0}}}}}}
}
# P1 release: use ordinary keyboard controls to roll from the parked position.
proc deck_height {height} {
    set ::wanted_height $height
    snap deck_$height [expr {$height<2 ? "deck_height [expr {$height+1}]" : "service_left_start"}]
}
proc lift_pose {name stage depth then} {
    set ::wanted_stage $stage;set ::wanted_depth $depth
    snap $name $then
}
proc wait_lift_up {then} {
    if {[value g_Carrier]!=1 || [value g_DisplayElevator]!=0} {after time 0.025 [list wait_lift_up $then];return}
    after time 0.05 $then
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
    snap service_left {pulse 8 64 {cursor 1 {pulse 7 128 {notice {require [expr {[view 0]==7 && [view 4]==15}] "Service rocket preview";pulse 8 32 {cursor 0 {pulse 7 128 {phase 3 {lift_pose lift_left_up_24 0 24 {lift_pose lift_left_up_8 0 8 {wait_lift_up service_left_return}}}}}}}}}}}
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
    phase 0 {pulse 7 128 {phase 1 {pulse 7 128 {phase 2 {pulse 7 128 {phase 3 {wait_lift_up launch_roll}}}}}}}
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
    pilot 128 1060
    wait_for {![world_byte 11] && abs([world_x]-2400)<60} {set ::wanted_smoke 1;snap island_bombed {wait_for {[world_x]>5000} approach "fly back from the island" 90}} "turn back over the hut" 20
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
    wait_for {[world_x]>7900} {snap open_sea_right {pilot_off;fly 1;keymatrixup 8 1;after time 0.3 restart_game}} "fly past the map end" 30
}
proc restart_game {} {
    fly 0
    keymatrixdown 6 2;keymatrixdown 4 136;after time 0.4 {keymatrixup 4 136;keymatrixup 6 2};phase 0 restarted
}
proc restarted {} {
    require [expr {[view 2]==3 && [view 4]==30 && [view 5]==1 && [stat 30]==0 && [stat 32]==0}] "Ctrl-R game reset or setting retention"
    snap restart engine_new_game
}
# P2 engine: low fuel warning, dry tank, crash, next plane, game over.
# g_Game: lives at +7, fuel at +15. g_Engine: fuel_ticks +0, failed +3, lamps +8.
proc game_byte {offset value} {debug write memory [expr {$::addr(g_Game)+$offset}] $value}
proc engine_byte {offset} {debug read memory [expr {$::addr(g_Engine)+$offset}]}
proc engine_new_game {} {
    pulse 7 128 {phase 1 {pulse 7 128 {phase 2 {pulse 7 128 {phase 3 {wait_lift_up {engine_takeoff engine_low_fuel}}}}}}}
}
proc engine_takeoff {then} {
    # Roll off the bow, then climb away.
    fly 16
    wait_for {[world_byte 12]==1} [list engine_climb $then] "engine takeoff roll" 15
}
proc engine_climb {then} {
    fly 48
    wait_for {[world_y]<1100} [list engine_airborne $then] "engine takeoff climb" 10
}
proc engine_airborne {then} {
    fly 16
    require [expr {[engine_byte 3]==0}] "Engine scenario takeoff"
    uplevel #0 $then
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
proc engine_wait_respawn {} {
    require [expr {[machine_info time]<$::crash_deadline}] "Dead plane never crashed"
    if {[view 2]!=2 || [word g_DisplayWorld]!=7032 || [word g_DisplayY]!=1160} {after time 0.05 engine_wait_respawn;return}
    require [expr {[debug read memory [expr {$::addr(g_Game)+15}]]==192 && [debug read memory [expr {$::addr(g_Game)+14}]]==128 && [engine_byte 3]==0}] "Next plane not refuelled and repaired"
    snap engine_next_plane {wait_lift_up {engine_takeoff land_circuit}}
}
# Closed-loop flying from the real flight state (s_World, SDCC layout):
# y (Q8 u32) +2, vx +6, facing_left +11, mode +12 (0 deck, 1 air, 2 arrest),
# turn +13, fast_roll +17, speed +21, climb +23; world x (Q8 u32) +31.
proc world_byte {offset} {debug read memory [expr {$::addr(s_World)+$offset}]}
proc world_s16 {offset} {set v [expr {[world_byte $offset]+256*[world_byte [expr {$offset+1}]]}]; expr {$v>=32768 ? $v-65536 : $v}}
proc world_x {} {expr {[world_byte 32]+256*[world_byte 33]}}
proc world_y {} {expr {[world_byte 3]+256*[world_byte 4]+65536*[world_byte 5]}}
proc world_vx {} {world_s16 6}
proc speed {} {world_s16 21}
proc climb {} {world_s16 23}
proc turn_shapes {} {set l {};for {set i 10} {$i<40} {incr i} {lappend l $i};return $l}
proc fly {mask} {keymatrixup 8 [expr {241 & ~$mask}]; if {$mask} {keymatrixdown 8 $mask}}
proc wait_for {cond then what {limit 30}} {
    set ::wait_deadline [expr {[machine_info time]+$limit}]
    wait_poll $cond $then $what
}
proc wait_poll {cond then what} {
    if {[uplevel #0 [list expr $cond]]} {after time 0.02 $then;return}
    require [expr {[machine_info time]<$::wait_deadline}] "Timeout: $what x=[world_x] y=[world_y] mode=[world_byte 12] speed=[speed] climb=[climb] turn=[world_byte 13]"
    after time 0.01 [list wait_poll $cond $then $what]
}
# Autopilot: hold a horizontal direction (which also turns the plane round)
# and trim the commanded climb toward a target altitude (screen y).
proc pilot {heading target} {
    set running [info exists ::pilot]
    set ::pilot [list $heading $target]
    if {!$running} {pilot_tick}
}
proc pilot_off {} {unset -nocomplain ::pilot;fly 0}
proc pilot_tick {} {
    if {![info exists ::pilot]} {return}
    lassign $::pilot heading target
    # Input is sampled once per frame (1.7 ticks NTSC, 2 PAL) and Up/Down
    # move the climb 600 per tick (300 diving in a turn), so trim within a
    # band of one step around the wanted climb. Without Up or Down a climb
    # decays to level but a dive holds. Heading 0 coasts (no power, airspeed
    # bleeds toward 1000); corrections then use the facing key.
    set error [expr {[world_y]-$target}]
    set want [expr {$error>40 ? 2400 : $error>2 ? 1200 : $error<-150 ? -3600 : $error<-40 ? -2400 : $error<-2 ? -1200 : 0}]
    set key [expr {$heading ? $heading : [world_byte 11] ? 16 : 128}]
    set c [climb]
    set mask $heading
    if {$want==0} {
        if {$c<0} {set mask [expr {$key|32}]}
    } elseif {$c<$want-600} {set mask [expr {$key|32}]} elseif {$c>$want+600} {set mask [expr {$key|64}]}
    fly $mask
    after time 0.02 pilot_tick
}
proc circuit {then} {
    # From takeoff (flying left off the bow): out to the left and back past
    # the carrier, low (y 1140, 60 px up); coast downwind to bleed speed so
    # the cable arrest is short; turn onto final out over the open sea past
    # the map's end, settle 5 px above deck contact, and flare near the stern.
    set ::circuit_then $then
    pilot 16 1140
    wait_for {[world_x]<6000} {pilot 128 1140;wait_for {![world_byte 11] && ![world_byte 13]} circuit_downwind "turn downwind" 10} "outbound" 15
}
proc circuit_downwind {} {
    pilot 128 1140
    wait_for {(abs([world_y]-1140)<=4 && [climb]==0) || [world_x]>6400} {pilot 0 1140;wait_for {[world_x]>=7800} circuit_turn_final "downwind" 30} "settle downwind" 15
}
proc circuit_turn_final {} {
    pilot 16 1155
    wait_for {[world_byte 11] && ![world_byte 13]} circuit_on_final "turn onto final" 10
}
proc circuit_on_final {} {
    # Level or descending at the flare: from a climb the flight path takes
    # several ticks to turn down and the touchdown comes too late.
    wait_for {[world_x]<=7430 && (abs([world_y]-1155)<=2 && [climb]<=0 || [world_x]<7380)} circuit_final "final approach" 10
}
proc circuit_final {} {
    puts $::report "final x=[world_x] y=[world_y] speed=[speed] climb=[climb]"
    require [expr {[world_x]>7330 && [world_y]>=1150 && [world_y]<=1158}] "Final approach not set up: x=[world_x] y=[world_y]"
    pilot_off
    uplevel #0 $::circuit_then
}
proc land_circuit {} {circuit land_flare}
proc land_flare {} {
    # The stall flare (Up alone, facing left) onto the deck; keep Up held so
    # the hook catches a cable.
    debug write memory $::addr(g_LastContact) 0
    fly 32
    wait_for {[value g_LastContact]!=0} land_touch "touchdown" 6
}
proc land_touch {} {
    require [expr {[value g_LastContact]==1 && [world_byte 12]!=1 && [world_y]==1160 && [world_byte 11]}] "Stall onto the deck must land: contact=[value g_LastContact] mode=[world_byte 12] y=[world_y]"
    puts $::report "touchdown x=[world_x] speed=[speed]"
    # Caught: the original draws the stretched rope while the cable holds.
    wait_for {[world_byte 12]==2} {set ::wanted_rope 1;snap arrest {wait_for {[world_byte 12]==0 && [speed]==0} land_stopped "arrest" 3}} "cable catch" 2
}
proc land_stopped {} {
    fly 0
    require [expr {[world_x]>7038 && [world_y]==1160}] "Arrested past the elevator: x=[world_x]"
    snap landed land_taxi
}
proc land_taxi {} {
    set ::wait_deadline [expr {[machine_info time]+30}]
    land_taxi_wait
}
# Distance rolled while braking from a deck speed: 8 per tick, (speed + 50) / 100 px.
proc braking_distance {speed} {
    set d 0
    while {$speed>0} {incr speed -8;if {$speed<0} {set speed 0};incr d [expr {($speed+50)/100}]}
    return $d
}
proc land_taxi_wait {} {
    # Power while the distance left exceeds the braking distance plus one
    # tick of input latency; creep the last pixels.
    set d [expr {[world_x]-7032}]
    if {[speed]==0 && abs($d)<=6} {
        fly 0
        require [expr {abs([world_x]-7032)<=6}] "Taxi did not stop on the elevator: x=[world_x]"
        pulse 8 1 {phase 7 {snap landed_service {pulse 7 128 {phase 3 {wait_lift_up {engine_takeoff bounce_circuit}}}}}}
        return
    }
    require [expr {$d>-6 && [machine_info time]<$::wait_deadline}] "Taxi overshot or timed out: x=[world_x]"
    set v [expr {[speed]+8}]
    # Below speed 50 the plane does not move (whole pixels per tick).
    if {$d>6 && [braking_distance $v]+($v+50)/100 < $d-2} {fly 16} else {fly 0}
    after time 0.01 land_taxi_wait
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
    if {[view 2]==$::lives_before || [word g_DisplayWorld]!=7032 || [word g_DisplayY]!=1160} {after time 0.05 sea_wait;return}
    require [expr {[value g_LastContact]==3 && [view 2]==$::lives_before-1}] "Powered sea dive must crash and cost a plane"
    fly 0
    snap sea_crash_next {wait_lift_up {engine_takeoff engine_last_plane}}
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
    snap game_over {pulse 7 128 {phase 0 {require [expr {[view 2]==3}] "Game over did not reset"; done}}}
}
proc done {} {
    require [expr {[value g_InputOverflow]==0}] "Input queue overflow in normal scenarios"
    puts $::report "PASS";flush $::report;close $::report;exit
}
debug watchpoint create -type write_mem -address $addr(g_MissedFrames) -command {guard missed_frame}
after time 1 {guard ready}
after time 1500 {bgerror "P0 scenario timeout"}
