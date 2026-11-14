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
foreach n {Input_JoySample g_DisplayGauges g_Engine g_Game g_Controls g_Ready g_GameView g_Combat g_FramePublished g_DisplayPage g_DisplayCamera g_DisplayWorld g_DisplayY g_SelectedFrame g_DisplayWave g_DisplayHeave g_DisplayShipFrame g_DisplayScale g_ViewChange g_VBlankTicks g_Carrier g_DisplayElevator g_CrewFrame g_TaxiTurn g_HoldFlight g_MissedFrames g_InputOverflow g_Turning g_Rendering g_RenderPage} {
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
    if {[string match "taxi_pose *" $then] || [string match "lift_pose *" $then]} {
        uplevel #0 $then
        debug write memory $::addr(g_HoldFlight) 0
    } else {
        debug write memory $::addr(g_HoldFlight) 0
        after time 0.06 $then
    }
}
proc publishing {} {
    if {![info exists ::armed]} {return}
    if {[word g_MissedFrames]} {error "Frame deadline missed: stage=[value g_Carrier] depth=[value g_DisplayElevator] pose=[value g_SelectedFrame] render=$::last_render"}
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
    if {[info exists ::wanted_pose]} {
        if {![value g_Turning] || [value g_SelectedFrame]!=$::wanted_pose} {return}
        unset ::wanted_pose
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
        require [expr {[value g_RenderPage]!=[value g_DisplayPage]}] "Rendering visible page"
        set ::pixels [debug read_block VRAM $::visible_base 27136]
    } elseif {[info exists ::pixels]} {
        set ::last_render [expr {1000*([machine_info time]-$::render_start)}]
        require [expr {$::pixels eq [debug read_block VRAM $::visible_base 27136]}] "Visible page changed during redraw"
        unset ::pixels
    }
}
proc missed_frame {} {
    if {![info exists ::last_publish]} {return}
    puts $::report "deadline elapsed=[expr {1000*([machine_info time]-$::last_publish)}] render=$::last_render stage=[value g_Carrier] world=[word g_DisplayWorld] vblank=[value g_VBlankTicks]"
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
    keymatrixdown 8 128
    taxi_pose right 0
}
proc taxi_pose {direction index} {
    set ::wanted_pose [debug read memory [expr {$::addr(g_TaxiTurn)+$index}]]
    if {$direction eq "right"} {
        set then [expr {$index<9 ? "taxi_pose right [expr {$index+1}]" : "taxi_right_end"}]
    } else {
        set then [expr {$index>1 ? "taxi_pose left [expr {$index-1}]" : "taxi_left_end"}]
    }
    snap taxi_${direction}_$index $then
}
proc taxi_right_end {} {
    if {[word g_DisplayWorld]!=7336 || [value g_Turning]} {after time 0.025 taxi_right_end;return}
    require [expr {[word g_DisplayY]==1160}] "Ground turn changed height"
    snap taxi_right_stop {after time 0.8 {snap taxi_right_hold {keymatrixup 8 128;keymatrixdown 8 16;taxi_pose left 10}}}
}
proc taxi_left_end {} {
    if {[word g_DisplayWorld]!=6617 || [value g_Turning]} {after time 0.025 taxi_left_end;return}
    require [expr {[word g_DisplayY]==1160}] "Ground roll changed height"
    snap taxi_left_stop {after time 0.8 {snap taxi_left_hold taxi_restart}}
}
proc taxi_restart {} {
    keymatrixup 8 16
    keymatrixdown 6 2;keymatrixdown 4 128
    after time 0.15 {keymatrixup 4 128;keymatrixup 6 2}
    phase 0 {pulse 7 128 {phase 1 {pulse 7 128 {phase 2 {pulse 7 128 {phase 3 {wait_lift_up launch_roll}}}}}}}
}
proc launch_roll {} {
    require [expr {[word g_DisplayWorld]==7032 && [word g_DisplayY]==1160}] "Deck start placement"
    keymatrixdown 8 16
    snap slow_roll {after time 4.1 accelerating_roll}
}
proc accelerating_roll {} {
    require [expr {[value g_SelectedFrame]==52}] "Tail lifted before five-second acceleration"
    snap accelerating_roll {after time 1.3 launch_climb}
}
proc launch_climb {} {
    require [expr {[word g_DisplayWorld]<7032 && [word g_DisplayWorld]>6657 && [word g_DisplayY]==1160}] "Ground roll left"
    snap ground_roll {keymatrixdown 8 32;after time 3.5 airborne}
}
proc airborne {} {
    require [expr {[word g_DisplayWorld]<6593 && [word g_DisplayY]<1160}] "Normal leftward takeoff"
    keymatrixup 8 48
    after time 0.6 {snap takeoff {set ::turn_y [word g_DisplayY];keymatrixdown 8 128;after time 0.3 turning}}
}
proc turning {} {
    require [expr {[value g_Turning]}] "Reversal did not bank"
    snap turn {after time 1.2 turn_end}
}
proc turn_end {} {
    require [expr {![value g_Turning] && [word g_DisplayY]>$::turn_y}] "Turn clock or altitude loss"
    keymatrixup 8 128
    snap turn_complete {set ::compensate_y [word g_DisplayY];keymatrixdown 8 48;after time 1.3 compensated_turn}
}
proc compensated_turn {} {
    require [expr {![value g_Turning] && [word g_DisplayY]<$::compensate_y}] "Climb did not compensate turn loss"
    keymatrixup 8 48
    after time 0.5 {snap compensated_turn {keymatrixdown 8 32;after time 0.8 held_stall}}
}
proc held_stall {} {
    require [expr {[value g_SelectedFrame]==43 && ![value g_Turning]}] "Stall must raise the nose"
    set ::stall_y [word g_DisplayY]
    snap stall_held {after time 0.4 stall_sink}
}
proc stall_sink {} {
    require [expr {[word g_DisplayY]>$::stall_y}] "Held stall must descend smoothly"
    keymatrixup 8 32
    after time 0.4 {snap stall_released {
        require [expr {[value g_SelectedFrame]==16}] "Releasing Up must level the plane"
        # A complete tap while the foreground is held must still latch a dive.
        debug write memory $::addr(g_HoldFlight) 1
        keymatrixdown 8 64
        after time 0.06 {keymatrixup 8 64}
        after time 0.12 {debug write memory $::addr(g_HoldFlight) 0}
        after time 0.7 dive_latched
    }}
}
proc dive_latched {} {
    require [expr {[value g_SelectedFrame]==45}] "Brief Down must retain nose-down art"
    set ::dive_y [word g_DisplayY]
    snap dive_released {after time 0.5 dive_persists}
}
proc dive_persists {} {
    require [expr {[value g_SelectedFrame]==45 && [word g_DisplayY]>$::dive_y}] "Dive did not persist after release"
    snap dive_persistent {keymatrixdown 8 32;after time 0.3 {keymatrixup 8 32};after time 0.7 dive_recover}
}
proc dive_recover {} {
    require [expr {[value g_SelectedFrame]==16}] "Up then release must recover level attitude"
    snap dive_recovered {keymatrixdown 8 48;after time 2 {keymatrixup 8 48};after time 2.5 {pulse 7 128 enter_in_flight}}
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
    snap resumed {keymatrixdown 8 48; after time 0.45 {keymatrixup 8 48};after time 1.1 debug_keys}
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
proc prepare_approach {} {
    # Recover the dive entered by the inverted joystick test, then descend
    # toward the carrier with the rightward turn already complete.
    keymatrixdown 8 160
    after time 2.5 {keymatrixup 8 32;keymatrixdown 8 64;approach_height}
}
proc approach_height {} {
    if {[word g_DisplayY]<1090} {after time 0.025 approach_height;return}
    keymatrixup 8 64
    approach_right
}
proc approach_right {} {
    if {[word g_DisplayWorld]<7500} {after time 0.025 approach_right;return}
    keymatrixup 8 128;keymatrixdown 8 16
    approach_left
}
proc approach_left {} {
    if {[word g_DisplayWorld]>7440 || [value g_Turning]} {after time 0.025 approach_left;return}
    require [expr {[value g_SelectedFrame]==50}] "Gear did not extend on inbound approach: x=[word g_DisplayWorld] y=[word g_DisplayY] pose=[value g_SelectedFrame]"
    snap approach {keymatrixdown 8 32;after time 1 retract_climb}
}
proc retract_climb {} {
    require [expr {[value g_SelectedFrame]!=50}] "Gear did not retract when climbing away"
    keymatrixup 8 48
    snap climb_gear_up {keymatrixdown 8 48;after time 1 {keymatrixup 8 16;keymatrixdown 8 1};after time 1.7 cannon_stall_left}
}
proc cannon_stall_left {} {
    snap cannon_stall_left {keymatrixup 8 32;after time 0.5 cannon_level_left}
}
proc cannon_level_left {} {
    snap cannon_level_left {keymatrixdown 8 64;after time 0.08 {keymatrixup 8 64};after time 0.7 cannon_dive_left}
}
proc cannon_dive_left {} {
    snap cannon_dive_left {keymatrixdown 8 160;after time 1.1 cannon_right}
}
proc cannon_right {} {
    keymatrixup 8 128
    after time 0.7 {snap cannon_stall_right {keymatrixup 8 32;after time 0.5 cannon_level_right}}
}
proc cannon_level_right {} {
    snap cannon_level_right {keymatrixdown 8 64;after time 0.08 {keymatrixup 8 64};after time 0.7 cannon_dive_right}
}
proc cannon_dive_right {} {
    snap cannon_dive_right {keymatrixup 8 1;keymatrixdown 6 2;keymatrixdown 4 136;after time 0.4 {keymatrixup 4 136;keymatrixup 6 2};phase 0 restarted}
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
    keymatrixdown 8 16
    after time 5.4 [list keymatrixdown 8 32]
    after time 8.9 [list engine_airborne $then]
}
proc engine_airborne {then} {
    keymatrixup 8 48
    require [expr {[word g_DisplayY]<1160 && [engine_byte 3]==0}] "Engine scenario takeoff"
    uplevel #0 $then
}
proc engine_low_fuel {} {
    game_byte 15 60
    set ::lamps {}
    after time 1.4 engine_watch_lamp
}
proc engine_watch_lamp {} {
    lappend ::lamps [expr {[engine_byte 8] & 2}]
    if {[llength $::lamps] < 40} {after time 0.02 engine_watch_lamp;return}
    require [expr {[lsearch $::lamps 0]>=0 && [lsearch $::lamps 2]>=0}] "Fuel lamp did not blink: $::lamps"
    require [expr {[engine_byte 7]<=8}] "Fuel needle did not sweep down"
    snap engine_low_fuel engine_dry
}
proc engine_dry {} {
    game_byte 15 0
    debug write memory $::addr(g_Engine) 1
    after time 0.3 {require [expr {[engine_byte 3]==1}] "Dry tank did not fail the engine"; snap engine_failed engine_crash_wait}
}
proc engine_crash_wait {} {
    set ::crash_deadline [expr {[machine_info time]+12}]
    engine_wait_respawn
}
proc engine_wait_respawn {} {
    require [expr {[machine_info time]<$::crash_deadline}] "Dead plane never crashed"
    if {[view 2]!=2 || [word g_DisplayWorld]!=7032 || [word g_DisplayY]!=1160} {after time 0.05 engine_wait_respawn;return}
    require [expr {[debug read memory [expr {$::addr(g_Game)+15}]]==192 && [debug read memory [expr {$::addr(g_Game)+14}]]==128 && [engine_byte 3]==0}] "Next plane not refuelled and repaired"
    snap engine_next_plane {wait_lift_up {engine_takeoff engine_last_plane}}
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
after time 330 {bgerror "P0 scenario timeout"}
