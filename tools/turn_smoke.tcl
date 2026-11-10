# Capture every distinct shape during two stationary turns, including a held T key.
set save_settings_on_exit false
set mute true
set maxframeskip 0
set throttle true
set root $env(WINGS_ROOT)
set output $env(WINGS_TEST_OUT)
set report [open [file join $output emulator-report.txt] w]
proc bgerror {message} {
    puts $::report "FAIL $message\n$::errorInfo"
    close $::report
    exit
}
set f [open [file join $root out wings.noi] r]
set symbols [read $f]
close $f
foreach name {g_Ready g_SelectedFrame g_DisplayPage g_DisplayX g_DisplayY g_FacingLeft g_Turning g_FramePublished g_MissedFrames} {
    if {![regexp "DEF _$name (0x\[0-9A-Fa-f\]+)" $symbols -> address]} { error "Missing $name" }
    set addr($name) $address
}
proc value {name} { debug read memory $::addr($name) }
proc dump {name data} {
    set f [open [file join $::output $name] wb]
    puts -nonewline $f $data
    close $f
}
proc record {} {
    if {![info exists ::recording]} { return }
    if {!([debug read {VDP status regs} 2] & 64)} { error "Publication outside VBlank" }
    set frame [value g_SelectedFrame]
    set page [value g_DisplayPage]
    set turning [value g_Turning]
    set facing [value g_FacingLeft]
    set x [value g_DisplayX]
    set y [value g_DisplayY]
    set prefix [expr {[info exists ::edge] ? "edge-" : ""}]
    puts $::report "${prefix}frame [machine_info time] $frame $turning $facing"
    set key $prefix$frame
    if {![info exists ::seen($key)]} {
        set ::seen($key) 1
        dump ${prefix}shape-$frame.vram [debug read_block VRAM 0 65536]
        puts $::report "capture $frame $page $x $y"
        # Wait until the newly published page has actually been scanned out.
        after frame [list screenshot -raw [file join $::output ${prefix}shape-$frame.png]]
    }
}
debug watchpoint create -type write_mem -address $addr(g_FramePublished) -command record
proc complete_left {} {
    if {[value g_Turning] || ![value g_FacingLeft]} { error "Held T repeated or first turn failed to finish" }
    keymatrixup 5 2
    after time 0.1 {
        keymatrixdown 5 2
        after time 0.1 { keymatrixup 5 2 }
        after time 1.2 complete_right
    }
}
proc complete_right {} {
    if {[value g_Turning] || [value g_FacingLeft]} { error "Second turn failed to finish" }
    unset ::recording
    keymatrixdown 8 192
    after time 3.2 {
        keymatrixup 8 192
        if {[value g_DisplayX] != 208 || [value g_DisplayY] != 180} { error "Failed to reach edge-test position" }
        set ::edge 1
        set ::recording 1
        keymatrixdown 5 2
        after time 0.1 { keymatrixup 5 2 }
        after time 1.2 complete_edge
    }
}
proc complete_edge {} {
    if {[value g_Turning] || ![value g_FacingLeft]} { error "Edge turn failed to finish" }
    if {[debug read memory $::addr(g_MissedFrames)] || [debug read memory [expr {$::addr(g_MissedFrames)+1}]]} { error "Missed deadlines" }
    puts $::report PASS
    close $::report
    exit
}
proc ready {} {
    if {[value g_Ready] == 1} {
        puts $::report "video_hz [expr {([debug read {VDP regs} 9] & 2) ? 50 : 60}]"
        set ::recording 1
        after time 0.1 {
            keymatrixdown 5 2
            after time 1.2 complete_left
        }
    } elseif {[machine_info time] > 15} { error "Startup timeout" } else { after time 0.1 ready }
}
after time 1 ready
