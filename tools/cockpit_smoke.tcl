# The cockpit window over the island (tools/verify_cockpit.py, map a): a
# game ended at once (the wave frames after "THE END"), then a sortie low
# over the whole island, west at altitude 60 then back east at 40, logging
# the window (g_Cockpit) and the plane every 0.1 s, with a snapshot every
# 400 px for the pixel check.
set cx 7032
set extra_symbols {g_Planes}
source [file join $env(WINGS_ROOT) tools smoke_lib.tcl]
no_enemy_planes
proc log {text} {puts $::report $text;flush $::report}
proc cockpit_log {} {
    if {![info exists ::logging]} return
    set scene {}
    for {set i 0} {$i<30} {incr i} {lappend scene [debug read memory [expr {$::addr(g_Cockpit)+$i}]]}
    log "cockpit x=[world_x] y=[world_y] left=[world_byte 11] page=[value g_DisplayPage] scene=[join $scene ,]"
    after time 0.1 cockpit_log
}
proc ready {} {
    if {[value g_Ready]!=1 || [view 2]!=3 || [view 4]!=30} {after time 0.05 ready;return}
    set ::armed 1
    pulse 7 128 {phase 1 {pulse 7 128 {phase 2 {pulse 7 128 {phase 3 {wait_lift_up {engine_takeoff end_game}}}}}}}
}
# Off the bow, down to altitude 60 and west over the island; snapshots
# every 400 px from its east end.
proc west {} {
    set ::logging 1;cockpit_log
    pilot 16 1140
    set ::next_snap 4400
    if {[info exists ::env(WINGS_COCKPIT_BOMBS)]} bombing
    west_poll
}
# WINGS_COCKPIT_BOMBS: a bomb a second on the way west (heavier frames).
proc bombing {} {
    if {[world_x]<300 || [world_byte 11]==0} return
    keymatrixdown 4 8;after time 0.1 {keymatrixup 4 8}
    after time 1.0 bombing
}
proc west_poll {} {
    if {[world_x]<=$::next_snap} {
        set n $::next_snap;set ::next_snap [expr {$::next_snap-400}]
        snap west_$n west_poll;return
    }
    if {[world_x]<200} {pilot 128 1160;set ::next_snap 400;wait_for {![world_byte 11] && ![world_byte 13]} east_poll "turn east" 20;return}
    after time 0.02 west_poll
}
proc east_poll {} {
    if {[world_x]>=$::next_snap} {
        set n $::next_snap;set ::next_snap [expr {$::next_snap+400}]
        snap east_$n east_poll;return
    }
    if {[world_x]>4400} {unset ::logging;pilot_off;done;return}
    after time 0.02 east_poll
}
# First the game ends, the last plane lost in the sea (Ctrl-R would start
# a new game at once): "THE END" stages its plate over the wave frames
# (rows 212..); the next game must find them reloaded.
proc end_game {} {
    game_byte 7 1
    fly 80
    wait_for {[view 0]==8} {pilot_off;fly 0;after time 0.5 {snap the_end {after_game new_game}}} "game over after the crash" 30
}
proc new_game {} {
    pulse 7 128 {phase 1 {pulse 7 128 {phase 2 {pulse 7 128 {phase 3 {wait_lift_up {snap new_deck {engine_takeoff west}}}}}}}}
}
after time 1 {guard ready}
