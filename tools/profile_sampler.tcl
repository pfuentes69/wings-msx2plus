# Statistical PC sampler loaded after a smoke script (see profile_p0.py).
# Every WINGS_PROFILE_PERIOD seconds of emulated time it records the program
# counter, the window-3 code segment, whether the renderer owns the frame,
# whether guns are active and the word at SP (caller of leaf helpers).
# Emulated time is frozen while Tcl runs, so sampling does not perturb timing.
set prof_period $env(WINGS_PROFILE_PERIOD)
set prof_file [file join $env(WINGS_TEST_OUT) profile.txt]
set prof_noi [open [file join $env(WINGS_ROOT) out mission-flight mission-flight.noi] r]
set prof_syms [read $prof_noi];close $prof_noi
foreach n {g_Bank3Segment g_Rendering g_GameView g_Combat g_FramePublished} {
    if {![regexp "DEF _$n (0x\[0-9A-Fa-f\]+)" $prof_syms -> a]} {error "Missing $n"}
    set prof_addr($n) [expr {$a}]
}
array set prof_hist {}
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
debug watchpoint create -type write_mem -address $prof_addr(g_FramePublished) -command {prof_count frame}
proc prof_sample {} {
    if {[debug read memory $::prof_addr(g_GameView)]==3} {
        set pc [reg pc]
        set sp [reg sp]
        set ret [expr {[debug read memory $sp]+256*[debug read memory [expr {($sp+1)&65535}]]}]
        set bank [debug read memory $::prof_addr(g_Bank3Segment)]
        set render [debug read memory $::prof_addr(g_Rendering)]
        # CombatState: cooldown at +145, flash_ticks at +159.
        set guns [prof_guns]
        incr ::prof_hist([list $pc $bank $render $guns $ret])
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
