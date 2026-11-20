# The player's crash (tools/verify_crash.py, map a; docs/crash.md): a dive
# into the sea, waited out (the plane slides, sinks behind the waves, the
# next plane comes 12 s later); a dive into the island (it slides, wrecking
# what it strikes, and burns), ended early with fire held; an engine dying
# over the deck (the wreck burns on the deck); then the last plane lost:
# the game is over. The plane and the crash are logged every 0.1 s.
set cx 7032
set extra_symbols {g_Planes g_Crash}
source [file join $env(WINGS_ROOT) tools smoke_lib.tcl]
no_enemy_planes
# The sinking plane's depth (g_Crash +7, src/core/crash.h): drawn lower.
proc snapshot_extra {name} {dump $name.sink [debug read_block memory [expr {$::addr(g_Crash)+7}] 1]}
proc log {text} {puts $::report $text;flush $::report}
proc crash_byte {offset} {debug read memory [expr {$::addr(g_Crash)+$offset}]}
proc crash_log {} {
    if {![info exists ::logging]} return
    log "plane t=[format %.2f [machine_info time]] x=[world_x] y=[world_y] mode=[world_byte 12] speed=[speed] climb=[climb] turn=[world_byte 13] clock=[crash_byte 4] depth=[crash_byte 7] lives=[view 2] phase=[view 0] crash=[value g_DisplayCrash] pose=[value g_SelectedFrame] smoke=[smoke_count] score=[expr {[debug read memory $::addr(g_DisplayScore)]+256*[debug read memory [expr {$::addr(g_DisplayScore)+1}]]+65536*[debug read memory [expr {$::addr(g_DisplayScore)+2}]]}] oil=[debug read memory [expr {$::addr(g_Game)+14}]]"
    after time 0.1 crash_log
}
proc mark {what} {log "mark $what t=[format %.2f [machine_info time]] x=[world_x] y=[world_y] mode=[world_byte 12] lives=[view 2] phase=[view 0]"}
proc ready {} {
    if {[value g_Ready]!=1 || [view 2]!=3 || [view 4]!=30} {after time 0.05 ready;return}
    set ::armed 1
    set ::logging 1;crash_log
    pulse 7 128 {phase 1 {pulse 7 128 {phase 2 {pulse 7 128 {phase 3 {wait_lift_up {engine_takeoff sea_dive}}}}}}}
}
# 1. Into the sea west of the bow, powered: no burst, the slide splashes,
# then the plane sinks; nothing pressed, the next plane comes after 12 s.
proc sea_dive {} {
    mark sea_dive
    wait_for {[world_x]<6400} {fly 80;wait_for {[world_byte 12]==3} sea_slide "sea contact" 15} "clear the bow" 10
}
proc sea_slide {} {
    mark sea_contact;fly 0
    wait_for {[world_y]>=1198} {snap sea_slide {wait_for {[world_byte 12]==4} sea_sinking "sea at rest" 5}} "sea surface" 3
}
proc sea_sinking {} {
    mark sea_sinking
    wait_for {[crash_byte 4]>=10} {snap sea_sink_1 {wait_for {[crash_byte 4]>=40} {snap sea_sink_2 {wait_for {[crash_byte 4]>=100} {snap sea_sunk sea_next}  "sinking 100" 10}} "sinking 40" 5}} "sinking 10" 3
}
proc sea_next {} {
    wait_for {[view 2]==2 && [view 0]==7} {mark sea_next_plane;pulse 7 128 {phase 3 {wait_lift_up {engine_takeoff island_west}}}} "the next plane after the sea" 8
}
# 2. West at altitude 60, then down into the island: bursts, booms, white
# flashes and wrecked targets along the slide, then the wreck burns. Fire
# held after 2.4 s ends it.
proc island_west {} {
    mark island_west
    pilot 16 1140
    wait_for {[world_x]<3300} {pilot_off;fly 80;wait_for {[world_byte 12]==3} island_slide "island contact" 10} "over the island" 60
}
proc island_slide {} {
    mark island_contact;fly 0
    wait_for {[world_y]>=1196} {snap island_slide {wait_for {[world_byte 12]==5} island_wreck "island at rest" 5}} "island ground" 5
}
proc island_wreck {} {
    mark island_wreck
    wait_for {[crash_byte 4]>=12} {snap wreck_1 {wait_for {[crash_byte 4]>=28} {snap wreck_2 island_skip} "burning 28" 5}} "burning 12" 3
}
proc island_skip {} {
    mark fire_held;fly 1
    wait_for {[view 2]==1 && [view 0]==7} {fly 0;mark island_next_plane;pulse 7 128 {phase 3 {wait_lift_up {engine_takeoff last_plane}}}} "fire ends the wreck" 4
}
# 3. The last plane: the engine dies over the deck; it falls onto it, burns
# there, and the game is over at the end.
proc last_plane {} {
    mark last_plane
    pilot 128 1100
    wait_for {[world_x]>=6700 && [world_x]<=6900 && [world_byte 11]==0} deck_engine "over the deck heading east" 60
}
proc deck_engine {} {
    pilot_off;fly 0
    game_byte 15 0
    debug write memory $::addr(g_Engine) 1
    mark engine_dry
    wait_for {[world_byte 12]==5} {mark deck_wreck;wait_for {[crash_byte 4]>=20} {snap deck_wreck game_over_wait} "deck burning 20" 5} "the deck wreck" 20
}
proc game_over_wait {} {
    wait_for {[view 0]==8} {mark game_over;unset ::logging;after time 0.5 done} "game over after the last wreck" 14
}
after time 1 {guard ready}
after time 600 {bgerror "crash scenario timeout"}
