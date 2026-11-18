# Enemy fighters on map j (docs/enemy-planes.md, step 5), run by
# tools/verify_fighters.py: the destroyer's launches and parked planes, a
# fighter's attack (fire, flash, sound, damage), and one shot down. (The
# battleship's list launches its "ghost" first, which holds rank 1 on the
# player's tail and keeps the real fighter from attacking, as in the
# original: tests/test_planes.py checks that order.)
set extra_symbols {g_Planes g_Ships g_SoundGun}
set cx 3960
source [file join $env(WINGS_ROOT) tools smoke_lib.tcl]
# Not about torpedo planes or the ships' guns: neither interferes.
no_torpedo_planes

# g_Planes (src/core/planes.h, SDCC packs): Plane 40 bytes: state +0, beh +1,
# rel +2, health +4, firing +12, facing +13, frame +14, t10 +10, t18 +16,
# x +24, talt +28, alt +30; then timer +160, fighters +162, live +164 ...
# cooldown, left[4], parked (see planes_offsets below).
set PLANE 40
proc log {t} {puts $::report $t;flush $::report}
proc pb {i off} {debug read memory [expr {$::addr(g_Planes)+$::PLANE*$i+$off}]}
proc pw {i off} {set v [expr {[pb $i $off]+256*[pb $i [expr {$off+1}]]}]; expr {$v>32767?$v-65536:$v}}
proc setw {i off v} {
    debug write memory [expr {$::addr(g_Planes)+$::PLANE*$i+$off}] [expr {$v&255}]
    debug write memory [expr {$::addr(g_Planes)+$::PLANE*$i+$off+1}] [expr {($v>>8)&255}]
}
proc fighters {} {debug read memory [expr {$::addr(g_Planes)+162}]}
proc live {} {debug read memory [expr {$::addr(g_Planes)+164}]}
# PlanesState after live (+164): drop +165, drop_x/alt/speed +166..171,
# drop_facing +172, wreck[8] +173, wrecks +189, cooldown +190, left[4] +192,
# parked +196.
proc sxw {} {set x [world_x];expr {$x>32767 ? $x-65536 : $x}}
proc parked {} {debug read memory [expr {$::addr(g_Planes)+196}]}
proc firing_any {} {for {set i 0} {$i<4} {incr i} {if {[pb $i 0]==2 && [pb $i 12]} {return 1}}; return 0}
# A muzzle flash (smoke-path frames 121..124) in the shown page's drawn list
# (g_SmokeDrawn: 80 entries of 5 bytes a page, the frame at +4).
proc flash_shown {} {
    set page [value g_DisplayPage]
    for {set k 0} {$k < [smoke_count]} {incr k} {
        set f [debug read memory [expr {$::addr(g_SmokeDrawn)+($page*80+$k)*5+4}]]
        if {$f >= 121 && $f <= 124} {return 1}
    }
    return 0
}
proc oil {} {debug read memory [expr {$::addr(g_Game)+14}]}
proc kills {} {expr {[debug read memory [expr {$::addr(g_Game)+4}]]+256*[debug read memory [expr {$::addr(g_Game)+5}]]}}
# The real fighter: a fighter slot at a sane altitude (not the ghost).
proc real_fighter {} {
    for {set i 0} {$i<4} {incr i} {if {[pb $i 0]==2 && ([pb $i 1]&3) && [pw $i 30]>0} {return $i}}
    return -1
}
proc snapshot_extra {name} {
    dump $name.planes [debug read_block memory $::addr(g_Planes) 230]
    dump $name.ships [debug read_block memory $::addr(g_Ships) 239]
    dump $name.state [debug read_block memory $::addr(g_Game) 20]
    dump $name.soundgun [debug read_block memory $::addr(g_SoundGun) 1]
}
proc trace_on {} {if {![info exists ::ftrace]} {set ::ftrace 1;flight_trace}}
proc flight_trace {} {
    if {![info exists ::ftrace]} return
    set i [real_fighter]
    log "flight x=[world_x] y=[world_y] oil=[oil] fighters=[fighters] parked=[parked] plane=[expr {$i<0 ? {-} : "[pw $i 24]/[pw $i 30]/[pb $i 1]/[pb $i 2]/[pb $i 12]"}] kills=[kills]"
    after time 0.5 flight_trace
}

proc ready {} {
    if {[value g_Ready]!=1 || [view 2]!=3 || [view 4]!=30} {after time 0.05 ready;return}
    set ::armed 1
    # The ships' guns as destroyed: the damage measured is the fighters'.
    for {set g 0} {$g<22} {incr g} {debug write memory [expr {$::addr(g_Ships)+$g}] 1}
    snap start {pulse 7 128 {phase 1 {pulse 7 128 {phase 2 {pulse 7 128 {phase 3 {wait_lift_up {engine_takeoff to_battleship}}}}}}}}
}
# Off the bow, west into the destroyer's window (-192..628).
proc to_battleship {} {
    trace_on
    for {set g 0} {$g<22} {incr g} {debug write memory [expr {$::addr(g_Ships)+$g}] 1}
    pilot 16 1050
    wait_for {[world_x]<640} launches "west to the destroyer" 60
}
# 1. Launches: two fighters 100 ticks apart (entries 3 and 2), the parked
# planes 10 -> 8. Turn about in the window.
proc launches {} {
    # The window opens at 628: the first launch may already be out.
    require [expr {[parked]+[fighters]==10 && [fighters]<=1}] "Before the launches: parked=[parked] fighters=[fighters]"
    loiter_window
    wait_for {[fighters]>=2} {
        unset -nocomplain ::window
        log "launched: fighters=[fighters] parked=[parked]"
        set ::wanted_frame {}; unset ::wanted_frame
        pilot 128 1050
        wait_for {[sxw]>150 && [sxw]<450} {snap launched attack} "over the deck" 30
    } "two launches" 40
}
proc loiter_window {} {
    set ::window 1
    loiter_tick
}
proc loiter_tick {} {
    if {![info exists ::window]} return
    if {[sxw]>560} {pilot 16 1050} elseif {[sxw]<60} {pilot 128 1050}
    after time 0.1 loiter_tick
}
# 2. The attack: flying straight east, level, the fighter closes from behind,
# fires (the flash), and its hits cost oil.
proc attack {} {
    pilot 128 1050
    set ::oil0 [oil]
    wait_for {[firing_any]} {
        log "firing: oil=[oil] soundgun=[value g_SoundGun]"
        snap attacked {wait_for {[oil] < $::oil0} {log "hit: oil $::oil0 -> [oil]";snap damaged {pilot 16 1050;wait_for {[world_byte 11] && ![world_byte 13] && abs([world_y]-1050)<4} shoot "turn west" 20}} "the fighter's hits" 40}
    } "the fighter attacks" 60
}
# 3. Shot down, westward over the open sea (east lies the carrier's tower):
# the attacker put 150 px ahead, same heading, at the player's altitude; its evasions (weaving, breaking after hits) are pinned as in
# tools/planes_smoke.tcl; the gun fires until it falls; the kill counts.
proc shoot {} {
    set ::target [real_fighter]
    place_target
}
proc place_target {} {
    set i $::target
    setw $i 24 [expr {[sxw]-150}]
    debug write memory [expr {$::addr(g_Planes)+$::PLANE*$i+13}] 255
    setw $i 30 [expr {1200-[world_y]}]
    setw $i 28 [expr {1200-[world_y]}]
    after time 0.2 {guard placed_target}
}
proc placed_target {} {
        set i $::target
        if {abs([pw $i 24]-([sxw]-150)) > 80 || [pb $i 13] != 255} {log "placement lost (x=[pw $i 24]); again";place_target;return}
        log "target x=[pw $i 24] alt=[pw $i 30] player=[world_x]"
        set ::joy 47
        chase
}
proc chase {} {
    set i $::target
    require [expr {[sxw] > -6000}] "The chase ran on: health=[pw $i 4]"
    if {[pb $i 0]!=2} {
        set ::joy 63
        log "shot down x=[pw $i 24]"
        wait_for {[pb $::target 0]==0} {snap fighter_down done} "the fighter at rest" 30
        return
    }
    setw $i 30 [expr {1200-[world_y]}]
    setw $i 28 [expr {1200-[world_y]}]
    setw $i 16 0
    setw $i 10 100
    # Its attack turn (behaviour 9/10) is cancelled: a plain fighter, level,
    # facing west, fleeing ahead of the player.
    if {[pb $i 0]==2} {
        debug write memory [expr {$::addr(g_Planes)+$::PLANE*$i+1}] 1
        setw $i 14 0
        debug write memory [expr {$::addr(g_Planes)+$::PLANE*$i+13}] 255
    }
    # The other fighter attacks from behind meanwhile: the oil is kept full
    # (its damage was checked in phase 2), or the engine seizes below 96.
    debug write memory [expr {$::addr(g_Game)+14}] 128
    pilot [expr {[sxw] > [pw $i 24]+120 ? 16 : 0}] 1050
    after time 0.02 {guard chase}
}
after time 1 {guard ready}
after time 600 {bgerror "Fighters scenario timeout"}
