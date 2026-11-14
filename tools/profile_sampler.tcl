# Statistical PC sampler loaded after a smoke script (see profile_p0.py).
# Every WINGS_PROFILE_PERIOD seconds of emulated time it records the program
# counter, the window-3 code segment, whether the renderer owns the frame,
# whether guns are active and the word at SP (caller of leaf helpers).
# Emulated time is frozen while Tcl runs, so sampling does not perturb timing.
set prof_period $env(WINGS_PROFILE_PERIOD)
set prof_file [file join $env(WINGS_TEST_OUT) profile.txt]
set prof_noi [open [file join $env(WINGS_ROOT) out mission-flight mission-flight.noi] r]
set prof_syms [read $prof_noi];close $prof_noi
foreach n {g_Bank3Segment g_Rendering g_GameView g_Combat g_FramePublished VDP_InterruptHandler g_ViewChange g_DisplayWorld g_DisplayY} {
    if {![regexp "DEF _$n (0x\[0-9A-Fa-f\]+)" $prof_syms -> a]} {error "Missing $n"}
    set prof_addr($n) [expr {$a}]
}
array set prof_hist {}
set prof_render_samples {}
array set prof_calls {}
proc prof_guns {} {
    expr {[debug read memory [expr {$::prof_addr(g_Combat)+145}]] || [debug read memory [expr {$::prof_addr(g_Combat)+159}]]}
}
proc prof_count {name} {
    if {[debug read memory $::prof_addr(g_GameView)]==3} {incr ::prof_calls([list $name [prof_guns]])}
}
# Optional entry counters: WINGS_PROFILE_CALLS="name:address ..." (resident code only).
if {[info exists env(WINGS_PROFILE_CALLS)]} {
    foreach item $env(WINGS_PROFILE_CALLS) {
        lassign [split $item :] name address
        debug set_bp $address {} [list prof_count $name]
    }
}
# Publication latency: T-states from VBlank ISR entry to the publish write,
# which must land while the VDP still reports vertical retrace.
set prof_vblank 0
debug set_bp $prof_addr(VDP_InterruptHandler) {} {set ::prof_vblank [machine_info time]}
proc prof_publish {} {
    prof_count frame
    if {[debug read memory $::prof_addr(g_GameView)]!=3} return
    set t [expr {int(([machine_info time]-$::prof_vblank)*3579545.0/250)*250}]
    incr ::prof_calls([list publish_tstates_$t [prof_guns]])
}
debug watchpoint create -type write_mem -address $prof_addr(g_FramePublished) -command prof_publish
# Per-frame cost: simulation (publish -> render start) and render duration, ms.
set prof_last_publish 0
proc prof_publish_time {} {set ::prof_last_publish [machine_info time]}
debug watchpoint create -type write_mem -address $prof_addr(g_FramePublished) -command prof_publish_time
proc prof_rendering {} {
    if {[debug read memory $::prof_addr(g_GameView)]!=3} return
    if {[debug read memory $::prof_addr(g_Rendering)]} {
        set ::prof_render_start [machine_info time]
    } elseif {[info exists ::prof_render_start] && $::prof_last_publish} {
        set end [machine_info time]
        set sim [expr {int(($::prof_render_start-$::prof_last_publish)*1000)}]
        set draw [expr {int(($end-$::prof_render_start)*1000)}]
        # View changes (altitude scale switch, full page rebuild) are exempt from deadlines.
        set kind [expr {[debug read memory $::prof_addr(g_ViewChange)] ? "rebuild" : "frame"}]
        set cwx [expr {[debug read memory $::prof_addr(g_DisplayWorld)]+256*[debug read memory [expr {$::prof_addr(g_DisplayWorld)+1}]]}]
        if {$kind eq "frame" && $cwx >= 6500 && $cwx <= 7450} {incr ::prof_calls([list carrier_frames 0])}
        incr ::prof_calls([list ${kind}_cost_${sim}_${draw} [prof_guns]])
        # Where the heaviest gameplay frames happen (world x, y of the last publication).
        # Renders over 85 ms: file their samples as a separate group (carrier
        # tag 2) so the worst frames can be broken down.
        set heavy [expr {$kind eq "frame" && $draw > 85 && $sim > 10}]
        if {$heavy} {incr ::prof_calls([list heavyrender_frames 0])}
        foreach key $::prof_render_samples {
            if {$heavy} {lset key 6 2}
            incr ::prof_hist($key)
        }
        set ::prof_render_samples {}
        if {$kind eq "frame" && $sim + $draw > 110} {
            set wx [expr {[debug read memory $::prof_addr(g_DisplayWorld)]+256*[debug read memory [expr {$::prof_addr(g_DisplayWorld)+1}]]}]
            set wy [expr {[debug read memory $::prof_addr(g_DisplayY)]+256*[debug read memory [expr {$::prof_addr(g_DisplayY)+1}]]}]
            incr ::prof_calls([list heavy_${sim}_${draw}_x${wx}_y${wy} [prof_guns]])
        }
        unset ::prof_render_start
    }
}
debug watchpoint create -type write_mem -address $prof_addr(g_Rendering) -command prof_rendering
proc prof_sample {} {
    if {[debug read memory $::prof_addr(g_GameView)]==3} {
        set pc [reg pc]
        set sp [reg sp]
        set ret [expr {[debug read memory $sp]+256*[debug read memory [expr {($sp+1)&65535}]]}]
        set bank [debug read memory $::prof_addr(g_Bank3Segment)]
        set render [debug read memory $::prof_addr(g_Rendering)]
        # CombatState: cooldown at +145, flash_ticks at +159.
        set guns [prof_guns]
        # VDP command engine busy (S#2 bit 0): shows whether rendering is CPU- or VDP-bound.
        set vdp [expr {[debug read {VDP status regs} 2] & 1}]
        # Carrier scene: published world x inside the ship's span (heaviest render).
        set wx [expr {[debug read memory $::prof_addr(g_DisplayWorld)]+256*[debug read memory [expr {$::prof_addr(g_DisplayWorld)+1}]]}]
        set carrier [expr {$wx >= 6500 && $wx <= 7450}]
        if {$render} {lappend ::prof_render_samples [list $pc $bank $render $guns $ret $vdp $carrier]} else {
            incr ::prof_hist([list $pc $bank $render $guns $ret $vdp $carrier])
        }
    }
    after time $::prof_period prof_sample
}
proc prof_dump {} {
    set f [open $::prof_file w]
    foreach {k v} [array get ::prof_hist] {puts $f "$k $v"}
    foreach {k v} [array get ::prof_calls] {puts $f "call $k $v"}
    close $f
}
rename exit prof_real_exit
proc exit {args} {prof_dump; prof_real_exit {*}$args}
after time $prof_period prof_sample
