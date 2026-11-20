# Enemy planes on map a (docs/enemy-planes.md), run by tools/verify_planes.py:
# a torpedo plane shot down by the gun, a torpedo hitting the carrier, a
# torpedo destroyed by bombs, and the carrier sunk ending the game.
set extra_symbols {g_Planes g_Ships}
source [file join $env(WINGS_ROOT) tools smoke_lib.tcl]

# g_Planes (src/core/planes.h, SDCC packs): Plane 40 bytes: state +0, beh +1,
# rel +2, health +4, facing +13, frame +14, speed +20, x +24, talt +28,
# alt +30, near +38; timer +160, fighters +162, live +164. g_Combat.enemy
# at +535: x whole +2, y +12, live +14. g_Ships.hull[4] (the carrier) +222.
set PLANE 40
set TIMER [expr {4*$PLANE}]
proc log {t} {puts $::report $t;flush $::report}
proc pb {i off} {debug read memory [expr {$::addr(g_Planes)+$::PLANE*$i+$off}]}
proc pw {i off} {set v [expr {[pb $i $off]+256*[pb $i [expr {$off+1}]]}]; expr {$v>32767?$v-65536:$v}}
proc setw {i off v} {
    debug write memory [expr {$::addr(g_Planes)+$::PLANE*$i+$off}] [expr {$v&255}]
    debug write memory [expr {$::addr(g_Planes)+$::PLANE*$i+$off+1}] [expr {($v>>8)&255}]
}
proc live {} {debug read memory [expr {$::addr(g_Planes)+$::TIMER+4}]}
proc set_timer {v} {
    debug write memory [expr {$::addr(g_Planes)+$::TIMER}] [expr {$v&255}]
    debug write memory [expr {$::addr(g_Planes)+$::TIMER+1}] [expr {$v>>8}]
}
proc hull {} {debug read memory [expr {$::addr(g_Ships)+222}]}
proc ew {off} {set v [expr {[debug read memory [expr {$::addr(g_Combat)+535+$off}]]+256*[debug read memory [expr {$::addr(g_Combat)+535+$off+1}]]}]; expr {$v>32767?$v-65536:$v}}
proc elive {} {debug read memory [expr {$::addr(g_Combat)+535+14}]}
proc kills {} {expr {[debug read memory [expr {$::addr(g_Game)+4}]]+256*[debug read memory [expr {$::addr(g_Game)+5}]]}}
proc slot {} {for {set i 0} {$i<4} {incr i} {if {[pb $i 0]} {return $i}}; return -1}
proc snapshot_extra {name} {
    dump $name.planes [debug read_block memory $::addr(g_Planes) 200]
    dump $name.ships [debug read_block memory $::addr(g_Ships) 239]
    dump $name.enemy [debug read_block memory [expr {$::addr(g_Combat)+535}] 18]
    dump $name.state [debug read_block memory $::addr(g_Game) 20]
}
# Spawn a torpedo plane now (the timer at 1) and wait for it.
proc spawn {then} {
    set ::before [live]
    set_timer 2
    wait_for {[live]>$::before} $then "torpedo plane spawn" 3
}
# The armed torpedo plane's slot (behaviour 4).
proc armed_slot {} {for {set i 0} {$i<4} {incr i} {if {[pb $i 0] && ([pb $i 1]&7)==4} {return $i}}; return -1}
proc trace_on {} {if {![info exists ::ftrace]} {set ::ftrace 1;flight_trace}}
proc flight_trace {} {
    if {![info exists ::ftrace]} return
    set i [slot]
    log "flight x=[world_x] y=[world_y] climb=[climb] lives=[view 2] plane=[expr {$i<0 ? {-} : "[pw $i 24]/[pw $i 30]/[pb $i 0]/[pb $i 1]/[pw $i 4]"}] torpedo=[elive]@[ew 2] hull=[hull] kills=[kills]"
    after time 0.5 flight_trace
}

proc ready {} {
    if {[value g_Ready]!=1 || [view 2]!=3 || [view 4]!=30} {after time 0.05 ready;return}
    set ::armed 1
    snap start {pulse 7 128 {phase 1 {pulse 7 128 {phase 2 {pulse 7 128 {phase 3 {wait_lift_up {engine_takeoff to_sea}}}}}}}}
}
# Off the bow, level at 1100 over the open sea west of the carrier.
proc to_sea {} {
    trace_on
    pilot 16 1120
    wait_for {[world_x]<6400 && abs([world_y]-1120)<4 && [climb]==0} gun_target "climb out" 30
}
# 1. The gun: a torpedo plane put 150 px ahead at the player's altitude,
# both flying west (away from the carrier: it turns back only after 550
# ticks chased), chased level until shot down; it falls into the sea and
# the kill counts.
proc gun_target {} {
    spawn {set ::target [armed_slot];place_target}
}
# Put it 150 px ahead (west) at the player's altitude; check it stuck (a
# write inside the game's own update of the record can be lost).
proc place_target {} {
    set i $::target
    setw $i 24 [expr {[world_x]-150}]
    debug write memory [expr {$::addr(g_Planes)+$::PLANE*$i+13}] 255
    setw $i 30 [expr {1200-[world_y]}]
    setw $i 28 [expr {1200-[world_y]}]
    after time 0.2 {
        set i $::target
        if {abs([pw $i 24]-([world_x]-150)) > 80 || [pb $i 13] != 255} {log "placement lost (x=[pw $i 24]); again";place_target;return}
        log "target x=[pw $i 24] alt=[pw $i 30] player=[world_x],[world_y]"
        # Fire with the joystick's trigger A: the autopilot owns keyboard row 8.
        set ::joy 47
        chase
    }
}
proc chase {} {
    set i $::target
    # Shot down first: the kill may come on the poll that crosses 3400.
    if {[pb $i 0]==2} {require [expr {[world_x] > 3400}] "The chase reached the island: health=[pw $i 4]"}
    if {[pb $i 0]!=2} {
        set ::joy 63
        log "shot down x=[pw $i 24] alt=[pw $i 30] score=[expr {[debug read memory $::addr(g_Game)]+256*[debug read memory [expr {$::addr(g_Game)+1}]]}]"
        snap shot_down {wait_for {[pb $::target 0]==0} gun_kill "the wreck at rest" 30}
        return
    }
    # A chased torpedo plane weaves (new altitudes 35..95) about 150 px
    # ahead, inside the 160 px box only just: the AI is unit-tested
    # (tests/test_planes.py); here its altitude is pinned to the player's
    # so the gun's hits, the kill, the fall and the count run end to end.
    # A hit also makes it break into a turn 8..13 ticks later (0xdea4):
    # its turn countdown (+16) is held at 0 too.
    setw $i 30 [expr {1200-[world_y]}]
    setw $i 28 [expr {1200-[world_y]}]
    setw $i 16 0
    # A pin lost inside the game's update can still let a turn start (beh
    # +1 bit 8), and a player who overtakes it makes it turn too: undo the
    # turn and face it west again.
    # Out of the gun's 160 px box (left behind or overtaken): back 120 px
    # ahead.
    set ahead [expr {[world_x]-[pw $i 24]}]
    if {([pb $i 1] & 8) || $ahead < 40 || $ahead > 150} {
        debug write memory [expr {$::addr(g_Planes)+$::PLANE*$i+1}] [expr {[pb $i 1] & ~8}]
        setw $i 14 0
        debug write memory [expr {$::addr(g_Planes)+$::PLANE*$i+13}] 255
        if {$ahead < 40 || $ahead > 150} {setw $i 24 [expr {[world_x]-120}]}
    }
    pilot [expr {[world_x] > [pw $i 24]+120 ? 16 : 0}] 1120
    after time 0.02 chase
}
proc gun_kill {} {
    require [expr {[kills]==1 && [live]==0}] "Kill not counted: kills=[kills] live=[live]"
    snap gun_kill {pilot 128 1100;wait_for {![world_byte 11] && ![world_byte 13]} attack "turn back east" 20}
}
# A torpedo plane 1300 px short of the carrier's near end (L = 6608),
# armed, flying east at 50 (as the timer's spawn would come from the west).
proc torpedo_plane {then} {
    spawn [list place_torpedo_plane $then]
}
proc place_torpedo_plane {then} {
    set i [armed_slot]
    set ::target $i
    # A write can land inside the game's own update of the record and be
    # overwritten when it stores x back: write, then check a moment later.
    setw $i 24 [expr {6608-1300}]
    debug write memory [expr {$::addr(g_Planes)+$::PLANE*$i+13}] 1
    after time 0.2 [list placed_check $then]
}
proc placed_check {then} {
    set i $::target
    if {abs([pw $i 24]-(6608-1300)) > 60 || [pb $i 13] != 1} {
        log "placement lost (x=[pw $i 24]); again"
        place_torpedo_plane $then
        return
    }
    log "torpedo plane x=[pw $i 24] facing=[pb $i 13] player=[world_x]"
    uplevel #0 $then
}
# 2. It drops and its torpedo hits the carrier (hull 4 -> 3); the arrow
# shows while it is armed.
proc attack {} {
    torpedo_plane {
        set ::wanted_frame {}
        unset ::wanted_frame
        after time 0.5 {snap armed {}}
        wait_for {[elive]==2} {log "running x=[ew 2]";wait_for {[hull]==3} carrier_hit "torpedo hits the carrier" 30} "the drop" 30
    }
}
proc carrier_hit {} {
    log "carrier hit hull=[hull] torpedo=[elive]"
    snap carrier_hit {wait_for {[live]==0 || [world_x]>7700} {pilot 16 1100;wait_for {[world_byte 11] && ![world_byte 13] && [world_x]<5300} destroy "back west" 40} "after the attack" 30}
}
# 3. Another: the player overtakes its torpedo low and carpet-bombs it
# before it reaches the carrier (the kill window 0x1ae2).
proc destroy {} {
    pilot 128 1100
    wait_for {![world_byte 11] && ![world_byte 13]} {torpedo_plane {wait_for {[elive]} bomb_run "the drop" 30}} "turn east" 20
}
proc bomb_run {} {
    set ::bombs_held 0
    bomb_tick
}
proc bomb_tick {} {
    if {![elive]} {
        keymatrixup 4 8
        require [expr {[hull]==3}] "The torpedo reached the carrier: hull=[hull]"
        log "torpedo destroyed: hull=[hull] stock=[view 4]"
        snap torpedo_destroyed {wait_for {[world_x]>7700} sink "clear of the carrier" 30}
        return
    }
    set tx [ew 2]
    if {[world_x] > $tx-350 && [world_x] < $tx+60} {keymatrixdown 4 8} else {keymatrixup 4 8}
    require [expr {[hull]==3}] "The torpedo reached the carrier: hull=[hull]"
    after time 0.02 bomb_tick
}
# 4. One hit left: the next torpedo sinks the carrier; losing the plane
# then ends the game.
proc sink {} {
    debug write memory [expr {$::addr(g_Ships)+222}] 1
    pilot 16 1100
    wait_for {[world_byte 11] && ![world_byte 13] && [world_x]<5300} {torpedo_plane {wait_for {[hull]==0} sunk "the last hit" 40}} "back west" 40
}
proc sunk {} {
    log "carrier sunk: lives=[view 2]"
    snap carrier_sunk {
        pilot_off
        debug write memory $::addr(g_LastContact) 0
        fly 80
        wait_for {[view 0]==8} {snap game_over done} "game over after the crash" 30
    }
}
after time 1 {guard ready}
after time 600 {bgerror "Planes scenario timeout"}
