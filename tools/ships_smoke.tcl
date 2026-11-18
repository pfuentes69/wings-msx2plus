# Ship step 6 (docs/ships.md): the P4 gate scripted on map j's release ROM.
# Run by tools/verify_ships.py. Map j: a destroyer at its left end (x
# 8..655, 1 hit), the carrier at 3960, a battleship at its right end (x
# 7160..7935, 2 hits).
set extra_symbols {g_Ships g_ShipsGone g_Planes}
set cx 3960
set taxi_margin 5
# The run's settings. Screen y = 1200 - altitude.
set cruise_y 880      ;# rocket passes and the flights out
set lead 350          ;# a pass fires this far short of its gun ...
set dive_lead 700     ;# ... after diving from this far short
set dive_pose 7       ;# the dive (facing right: 4 level, 5..9 down)
set pullup 130        ;# altitude
set adjust 0;set dive_adjust 0;set passes 0
set fuel_home 110
set wave_y 1161       ;# altitude 39: the torpedo's release envelope is 41
set bs_release 6450   ;# battleship hull from 7160; the run is about 990 px
set ds_release 1300   ;# destroyer hull to 655
set late 60
set sink_watch 30     ;# sinking step of the snapshot (bonus at 10, gone at 120)
source [file join $env(WINGS_ROOT) tools smoke_lib.tcl]
# Enemy planes have their own checks (docs/enemy-planes.md).
no_enemy_planes

# g_Ships (src/core/ships.h, SDCC packs): down[40] +0, guns_down +121,
# splashes +212, hits +215, hull[5] +218, hull_hits +223, step[4] +225,
# sinking +237, left +238. g_Combat.torpedo at +517: live +14, life +15.
proc ships {offset} {debug read memory [expr {$::addr(g_Ships)+$offset}]}
proc gun_down {gun} {ships $gun}
proc guns_down {first last} {set n 0;for {set g $first} {$g<=$last} {incr g} {incr n [gun_down $g]};return $n}
proc hull {ship} {ships [expr {218+$ship}]}
proc sink_step {ship} {ships [expr {225+$ship}]}
proc ships_left {} {ships 238}
proc torpedo {offset} {debug read memory [expr {$::addr(g_Combat)+517+$offset}]}
proc score {} {expr {[debug read memory $::addr(g_Game)]+256*[debug read memory [expr {$::addr(g_Game)+1}]]+65536*[debug read memory [expr {$::addr(g_Game)+2}]]}}
# World x read as signed: past the map's left end it goes negative.
proc sx {} {set x [world_x];expr {$x>32767 ? $x-65536 : $x}}
proc oil {} {debug read memory [expr {$::addr(g_Game)+14}]}
proc fuel {} {debug read memory [expr {$::addr(g_Game)+15}]}
proc altitude {} {expr {1200-[world_y]}}
# The ticker's text (src/msx/message.c s_Text, a static: its offset from
# g_MessageActive in the module's symbols).
set f [open [file join [file dirname $env(WINGS_ROM)] message.sym] r];set sym [read $f];close $f
regexp {_g_MessageActive +([0-9A-F]+)} $sym -> base
regexp {_s_Text +([0-9A-F]+)} $sym -> text
set text_addr [expr {$addr(g_MessageActive)+[scan $text %x]-[scan $base %x]}]
proc snapshot_extra {name} {
    dump $name.text [debug read_block memory $::text_addr 205]
    dump $name.ships [debug read_block memory $::addr(g_Ships) 239]
    dump $name.gone [debug read_block memory $::addr(g_ShipsGone) 1]
    dump $name.torpedo [debug read_block memory [expr {$::addr(g_Combat)+517}] 18]
    dump $name.state [debug read_block memory $::addr(g_Game) 20]
}
proc log {text} {puts $::report $text;flush $::report}

proc ready {} {
    if {[value g_Ready]!=1 || [view 2]!=3 || [view 4]!=30} {after time 0.05 ready;return}
    set ::armed 1
    # Rank 0, the briefing, then rockets at the loadout.
    snap rank {pulse 7 128 {phase 1 {snap briefing {pulse 7 128 {phase 2 {pulse 8 64 {cursor 1 {pulse 7 128 {phase 3 {wait_lift_up sortie_rockets}}}}}}}}}}
}
proc sortie_rockets {} {
    require [expr {[view 3]==1 && [view 4]==15 && [word g_DisplayWorld]==$::cx}] "Rocket sortie: weapon=[view 3] stock=[view 4] world=[word g_DisplayWorld]"
    snap start {engine_takeoff to_battleship}
}
# Off the bow (leftwards), turn round and fly out to the battleship high.
proc to_battleship {} {
    pilot 16 1000
    wait_for {[world_x]<$::cx-400} {pilot 128 $::cruise_y;set ::tracing 1;rocket_trace;wait_for {[world_x]>6000} rocket_pass "fly to the battleship" 60} "climb out" 15
}
# Rockets (g_Combat +160, 23 bytes each): x whole +2, y +16, delay +18,
# angle +20, live +22.
proc rocket_trace {} {
    if {![info exists ::tracing]} return
    for {set i 0} {$i<15} {incr i} {
        set b [expr {$::addr(g_Combat)+160+23*$i}]
        set live [debug read memory [expr {$b+22}]]
        set key r$i
        if {$live} {
            set x [expr {[debug read memory [expr {$b+2}]]+256*[debug read memory [expr {$b+3}]]}]
            set y [expr {[debug read memory [expr {$b+16}]]+256*[debug read memory [expr {$b+17}]]}]
            if {$y>32767} {incr y -65536}
            set ::last($key) "$x/$y/$live"
        } elseif {[info exists ::last($key)]} {
            log "rocket $i ended $::last($key) guns=[guns_down 8 21] score=[score]"
            lappend ::bursts [lindex [split $::last($key) /] 0]
            unset ::last($key)
        }
    }
    after time 0.02 rocket_trace
}
# Gun x (mission_ships.h): the battleship's guns are 8..21.
set gun_x {86 96 116 126 566 576 596 606 7203 7213 7234 7244 7266 7276 7763 7773 7795 7805 7826 7836 7858 7868}
proc next_gun {first last} {
    for {set g $first} {$g<=$last} {incr g} {if {![gun_down $g]} {return $g}}
    return -1
}
# Up to three dive passes from the left at the battleship's first guns
# (8..13), each at the first live one. A burst kills a gun within 16 px:
# not every rocket does.
proc rocket_pass {} {
    set g [next_gun 8 13]
    # Enough fuel (192 full) and oil (a hit leaks it; the engine seizes
    # below 96) for the way back.
    if {$g<0 || [view 4]<4 || $::passes>=3 || [fuel]<$::fuel_home || [oil]<112} {unset -nocomplain ::tracing;rockets_done;return}
    set gx [lindex $::gun_x $g]
    # Closed loop on the last salvo: where it burst against its target
    # moves this pass's firing point (dive angles differ pass to pass).
    if {[info exists ::bursts] && [llength $::bursts]} {
        set sum 0;foreach b $::bursts {incr sum $b}
        set miss [expr {$sum/[llength $::bursts]-$::target}]
        set ::adjust [expr {max(-200,min(200,$::adjust-$miss))}]
        log "salvo missed by $miss: adjust $::adjust"
    }
    set ::bursts {};set ::target $gx
    set ::fire_x [expr {$gx-$::lead+$::adjust}]
    set ::dive_x [expr {$gx-$::dive_lead+$::dive_adjust}]
    incr ::passes
    log "pass gun=$g x=$gx plane=[world_x] y=[world_y] stock=[view 4] oil=[oil] fuel=[fuel]"
    # Back to the left of the dive point, then in from the left at cruise.
    if {[world_x]>$::dive_x-300} {
        pilot 16 $::cruise_y
        wait_for {[world_x]<$::dive_x-500} {pilot 128 $::cruise_y;wait_for {[world_x]>$::dive_x && abs([world_y]-$::cruise_y)<8 && ![world_byte 13]} rocket_dive "run in" 40} "turn back for a pass" 40
    } else {
        pilot 128 $::cruise_y
        wait_for {[world_x]>$::dive_x && abs([world_y]-$::cruise_y)<8 && ![world_byte 13]} rocket_dive "run in" 40
    }
}
proc rocket_dive {} {
    pilot_off
    set ::tapped -1
    unset -nocomplain ::salvo_end
    dive_tick
}
# Nose down with Down to the dive pose, fire from fire_x while above the
# pull-up altitude, then climb away.
proc dive_tick {} {
    set pose [value g_SelectedFrame]
    # Steeper than pose 7 the pull-up takes longer: start it higher.
    if {[altitude]<$::pullup+max(0,$pose-7)*40} {
        keymatrixup 4 8
        log "pullup x=[world_x] y=[world_y] pose=$pose guns=[guns_down 8 13] stock=[view 4]"
        # Down before the firing point (a steeper dive): dive later.
        if {[world_x]<$::fire_x+30} {set ::dive_adjust [expr {$::dive_adjust+$::fire_x+60-[world_x]}];log "dive later: $::dive_adjust"}
        if {![info exists ::rockets_seen]} {set ::rockets_seen 1;snap rockets_fired {}}
        pilot 128 $::cruise_y
        wait_for {[world_y]<$::cruise_y+40} rocket_pass "climb out" 20
        return
    }
    # One Down tap per pose: held, Down repeats every 4 ticks and a PAL
    # frame's ticks run past the wanted pose.
    if {$pose<$::dive_pose && $pose!=$::tapped} {
        set ::tapped $pose
        fly 192;after time 0.03 {fly 128}
    } elseif {$pose>=$::dive_pose} {fly 128}
    # A salvo: held for a second (4 rockets) from the firing point.
    if {$pose>=$::dive_pose && [world_x]>=$::fire_x} {
        if {![info exists ::salvo_end]} {set ::salvo_end [expr {[machine_info time]+1.0}]}
        if {[machine_info time]<$::salvo_end} {keymatrixdown 4 8} else {keymatrixup 4 8}
    }
    after time 0.02 dive_tick
}
proc rockets_done {} {
    log "rockets done fuel=[fuel] guns=[guns_down 8 13] score=[score] stock=[view 4] hull=[hull 1]"
    require [expr {[guns_down 8 13]>=2 && [hull 1]==2 && [ships_left]==2}] "Rockets: guns=[guns_down 8 13] hull=[hull 1] left=[ships_left]"
    snap guns_down {go_land landed_rearm}
}
# Back to the carrier (from the right, flying left) and the lib's circuit:
# land, stop on the elevator, then landed_on_lift.
proc go_land {then} {
    incr ::landing_n
    set ::after_landing $then
    trace_on
    # From the east, already heading the landing way (right to left):
    # straight in, without the circuit (a leaking engine seizes below oil
    # 96). High until near the carrier, then down in steps: a long descent
    # overshoots into the sea. Then the lib's final approach and flare.
    if {[sx]<$::cx} {
        # West of the carrier: east past it first.
        pilot 128 1000
        wait_for {[world_x]>$::cx+2700} [list go_land_east] "east past the carrier" 60
        return
    }
    go_land_east
}
proc go_land_east {} {
    pilot 16 1000
    wait_for {[world_x]<$::cx+2600 && [world_x]>$::cx} {
        pilot 16 1100
        wait_for {abs([world_y]-1100)<8} {
            pilot 16 1140
            wait_for {[world_x]<$::cx+1100} {set ::circuit_then land_flare;circuit_turn_final} "in to the carrier" 30
        } "down to 1100" 30
    } "fly back to the carrier" 90
}
proc sname {name} {return "landing$::landing_n\_$name"}
proc landed_on_lift {} {
    log "landed fuel=[fuel]"
    unset -nocomplain ::ftrace
    uplevel #0 $::after_landing
}
# Down the lift; the service offers the weapons: the torpedo (1).
proc landed_rearm {} {
    pulse 8 1 {phase 7 {pulse 8 64 {cursor 2 {snap service_torpedo {pulse 7 128 {phase 3 {wait_lift_up sortie_torpedo}}}}}}}
}
# The service offers the weapon carried first: the torpedo again.
proc landed_rearm_destroyer {} {
    pulse 8 1 {phase 7 {cursor 2 {snap service_torpedo_again {pulse 7 128 {phase 3 {wait_lift_up sortie_destroyer}}}}}}
}
proc sortie_destroyer {} {
    require [expr {[view 3]==2 && [view 4]==1}] "Torpedo sortie: weapon=[view 3] stock=[view 4]"
    engine_takeoff {set ::release_x 2600;set ::late 400;set ::release_then torpedo_expired_check;pilot 16 1100;wait_for {abs([world_y]-1100)<10} {pilot 16 $::wave_y} "down to 1100" 20;wait_for {[world_x]<=$::release_x+40 && abs([world_y]-$::wave_y)<=2 && [climb]==0} torpedo_release_left "level at wave height" 30}
}
# Then on to the destroyer at cruise height.
proc destroyer_turn {} {
    log "destroyer turn x=[world_x] facing_left=[world_byte 11]"
    set ::turn_x [expr {$::ds_release+1700}]
    pilot 128 1000
    wait_for {[world_x]>$::turn_x && [world_x]<20000} destroyer_run "come round for the destroyer" 30
}
proc sortie_torpedo {} {
    require [expr {[view 3]==2 && [view 4]==1}] "Torpedo sortie: weapon=[view 3] stock=[view 4]"
    engine_takeoff {pilot 16 1000;wait_for {[world_x]<$::cx-400} {pilot 128 1000;wait_for {[world_x]>4800} battleship_first "out to sea" 40} "climb out" 15}
}
# Down to wave height heading right and release in level flight at x
# (torpedo envelope: altitude 41 or lower, docs/torpedo.md).
proc torpedo_run {x then} {
    set ::release_x $x;set ::release_then $then
    pilot 128 $::wave_y
    wait_for {[world_x]>=$::release_x-40 && abs([world_y]-$::wave_y)<=2 && [climb]==0} torpedo_release "level at wave height" 30
}
proc torpedo_release {} {
    require [expr {[world_x]<$::release_x+60}] "Torpedo run too late: x=[world_x] wanted $::release_x"
    set ::hull_hits [expr {[ships 223]+256*[ships 224]}]
    log "torpedo release x=[world_x] y=[world_y] altitude=[altitude] speed=[speed]"
    keymatrixdown 4 8
    after time 0.1 {keymatrixup 4 8}
    wait_for {[torpedo 14]==2} {
        log "torpedo running x=[torpedo_x] stock=[view 4]"
        require [expr {[view 4]==0}] "Stock after release: [view 4]"
        pilot 128 $::cruise_y
        uplevel #0 $::release_then
    } "torpedo in the water" 3
}
proc torpedo_x {} {expr {[torpedo 2]+256*[torpedo 3]}}
# Released where its 199 moves end over open sea: it vanishes, no hull hit.
proc torpedo_expired_check {} {
    # The plane has turned back (torpedo_release_left): meet it, its wake
    # in view.
    wait_for {[torpedo 14]==2 && abs([torpedo_x]-[world_x])<60} {snap torpedo_running torpedo_expiry} "meet the running torpedo" 15
}
proc torpedo_expiry {} {
    wait_for {[torpedo 14]==0} {
        log "torpedo gone x=[torpedo_x] hulls=[hull 0]/[hull 1]"
        require [expr {[hull 0]==1 && [ships 223]+256*[ships 224]==$::hull_hits}] "Distant torpedo damaged a hull"
        snap torpedo_expired {refill destroyer_turn}
    } "torpedo runs out" 25
}
# F1 (the refill cheat, not in the original) gives back the torpedo.
proc refill {then} {
    keymatrixdown 6 32;after time 0.1 {keymatrixup 6 32}
    wait_for {[view 4]==1} $then "F1 refill" 2
}
# Come round from the left and release in range of the battleship's hull
# (7160), more than 512 px from its first guns: no shell splash can fall
# near the torpedo.
proc approach_right {x then} {
    if {[world_x]>$x-1300} {
        pilot 16 $::cruise_y
        set ::turn_x [expr {$x-1600}]
        wait_for {[world_x]<$::turn_x} [list approach_right $x $then] "come round" 40
        return
    }
    torpedo_run $x $then
}
proc battleship_first {} {approach_right $::bs_release battleship_hit1}
proc battleship_hit1 {} {
    wait_for {[hull 1]<2} {
        log "battleship hit 1 score=[score]"
        require [expr {[hull 1]==1 && ![ships 237] && [ships_left]==2}] "Battleship after one hit: hull=[hull 1] sinking=[ships 237]"
        snap battleship_hit {refill {approach_right $::bs_release battleship_hit2}}
    } "battleship hit" 30
}
proc battleship_hit2 {} {
    wait_for {[hull 1]==0} {
        set ::score_hit [score]
        log "battleship hit 2 score=[score]"
        snap battleship_struck {watch_sinking 1 battleship 7050 7350 1070}
    } "battleship second hit" 30
}
# Over the sinking ship: low through the close view, then wait for the
# bonus and the "sunk" ticker, then for the sea to take it.
proc watch_sinking {ship name x1 x2 y} {
    set ::sink_ship $ship
    loiter $x1 $x2 $y
    set ::sink_scale [expr {$ship==1 ? 1 : 8}]
    wait_for {[sink_step $::sink_ship]>=$::sink_watch && [value g_DisplayScale]==$::sink_scale} [list sinking_low $ship $name] "sinking" 40
}
# Fly back and forth between x1 and x2 at screen y.
proc loiter {x1 x2 y} {
    set ::loiter [list $x1 $x2 $y]
    loiter_tick
}
proc loiter_tick {} {
    if {![info exists ::loiter]} return
    lassign $::loiter x1 x2 y
    set x [sx]
    if {$x<$x1} {pilot 128 $y} elseif {$x>$x2} {pilot 16 $y} elseif {![info exists ::pilot]} {pilot 128 $y}
    after time 0.05 loiter_tick
}
proc sinking_low {ship name} {
    log "$name step=[sink_step $ship] band=[value g_DisplayBand] score=[score] x=[world_x] y=[world_y]"
    require [expr {[score]>=$::score_hit+[lindex {2500 4500} $ship]}] "No sinking bonus: [score]"
    snap ${name}_sinking [list sinking_gone $ship $name]
}
proc sinking_gone {ship name} {
    if {$name eq "battleship"} {unset ::loiter;battleship_leave;return}
    wait_for {[value g_ShipsGone] & (1<<$::sink_ship)} "unset ::loiter;${name}_gone" "$name goes under" 40
}
# Back to the carrier while it sinks; the sea takes it on the way.
proc battleship_leave {} {
    pilot 16 1000
    wait_for {[value g_ShipsGone] & 2} {
        require [expr {[ships_left]==1 && [score]-$::score_hit==4500}] "Battleship sunk: left=[ships_left] bonus=[expr {[score]-$::score_hit}]"
        snap battleship_gone {go_land landed_rearm_destroyer}
    } "battleship goes under" 40
}
# The flight, logged every 0.25 s from the run to the landing.
proc trace_on {} {if {![info exists ::ftrace]} {set ::ftrace 1;flight_trace}}
proc flight_trace {} {
    if {![info exists ::ftrace]} return
    log "flight x=[world_x] y=[world_y] climb=[climb] pose=[value g_SelectedFrame] mode=[world_byte 12] speed=[speed] lives=[view 2] oil=[oil] fuel=[fuel] engine=[engine_byte 3]"
    after time 0.25 flight_trace
}
# The destroyer at the map's left end, its guns live: released more than
# 512 px from them (stern guns 566..606), then away.
proc destroyer_run {} {
    trace_on
    set ::release_x $::ds_release;set ::release_then destroyer_hit
    # Round onto the run at 1000 first: a turn loses height, and with the
    # descent on top of it the plane meets the sea.
    pilot 16 1000
    wait_for {[world_byte 11] && ![world_byte 13] && abs([world_y]-1000)<15} destroyer_descent "turn onto the run" 30
}
proc destroyer_descent {} {
    pilot 16 1100
    wait_for {abs([world_y]-1100)<10} {pilot 16 $::wave_y} "down to 1100" 20
    wait_for {[world_x]<=$::ds_release+40 && abs([world_y]-$::wave_y)<=2 && [climb]==0} torpedo_release_left "level at wave height" 30
}
proc torpedo_release_left {} {
    # Late by up to ::late px (60, or 400 for the run that must only end in
    # open sea: from 2200 on it runs out short of the destroyer).
    require [expr {[world_x]>$::release_x-$::late}] "Torpedo run too late: x=[world_x] wanted $::release_x"
    set ::late 60
    log "torpedo release x=[world_x] y=[world_y] altitude=[altitude] speed=[speed]"
    keymatrixdown 4 8
    after time 0.1 {keymatrixup 4 8}
    set ::hull_hits [expr {[ships 223]+256*[ships 224]}]
    # Climb a second, then turn back east: away from the guns ahead (a
    # hit starts an oil leak, and the engine seizes below 96).
    wait_for {[torpedo 14]==2} {pilot 16 1060;after time 1.0 {pilot 128 1000};uplevel #0 $::release_then} "torpedo in the water" 3
}
proc destroyer_hit {} {
    wait_for {[hull 0]==0} {
        set ::score_hit [score]
        log "destroyer hit score=[score]"
        snap destroyer_struck {watch_sinking 0 destroyer 1300 1900 880}
    } "destroyer hit" 30
}
proc destroyer_gone {} {
    require [expr {[ships_left]==0 && [score]-$::score_hit==2500}] "Destroyer sunk: left=[ships_left] bonus=[expr {[score]-$::score_hit}]"
    snap destroyer_gone {go_land mission_briefed}
}
# The mission is complete: down the lift to the next mission's briefing.
proc mission_briefed {} {
    pulse 8 1 {phase 1 {snap mission_briefing {pulse 7 128 {phase 2 {pulse 7 128 {phase 3 {wait_lift_up {snap mission_two done}}}}}}}}
}
after time 1 {guard ready}
after time 900 {bgerror "Ships scenario timeout"}
