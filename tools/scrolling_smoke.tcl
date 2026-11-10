# Synthetic scenery benchmark, invoked by verify_scrolling.py.
set save_settings_on_exit false
set mute true
set throttle true
set maxframeskip 0
set root $env(WINGS_ROOT)
set output $env(WINGS_TEST_OUT)
set report [open [file join $output emulator-report.txt] w]
proc bgerror {message} {
    puts $::report "FAIL $message"
    puts $::report $::errorInfo
    flush $::report
    close $::report
    exit
}
set f [open [file join $root out wings.noi] r]
set symbols [read $f]
close $f
foreach name {g_Ready g_SelectedFrame g_DisplayPage g_DisplayX g_DisplayY g_Rendering g_MissedFrames g_FramePublished g_DisplayCamera g_DisplayScenery g_ScrollPaused g_ScrollReverse g_VBlankTicks} {
    if {![regexp "DEF _$name (0x\[0-9A-Fa-f\]+)" $symbols -> address]} { error "Missing $name" }
    set addr($name) $address
}
proc value {name} { debug read memory $::addr($name) }
proc word {name} { expr {[value $name] + 256 * [debug read memory [expr {$::addr($name)+1}]]} }
proc dump {name data} {
    set f [open [file join $::output $name] wb]
    puts -nonewline $f $data
    close $f
}
proc rendering {} {
    if {[info exists ::inject_overrun] && ![value g_Rendering]} {
        debug write memory $::addr(g_VBlankTicks) [expr {([value g_VBlankTicks] + 2) & 255}]
        unset ::inject_overrun
        set ::recovering 1
    }
    if {![info exists ::measuring]} { return }
    if {[value g_Rendering]} { set ::start [machine_info time] } elseif {[info exists ::start]} {
        puts $::report "render_ms [expr {1000*([machine_info time]-$::start)}]"
        unset ::start
    }
}
proc publication {} {
    if {[info exists ::recovering]} {
        if {[word g_MissedFrames] != 1} { error "Forced overrun was not counted" }
        if {!([debug read {VDP status regs} 2] & 64)} { error "Overrun published outside VBlank" }
        puts $::report "forced_overrun PASS"
        puts $::report PASS
        close $::report
        exit
    }
    if {![info exists ::measuring]} { return }
    if {!([debug read {VDP status regs} 2] & 64)} { error "Publication outside VBlank" }
    if {[info exists ::last_publish]} {
        puts $::report "interval_ms [expr {1000*([machine_info time]-$::last_publish)}]"
    }
    set ::last_publish [machine_info time]
    if {[info exists ::capture]} {
        snapshot $::capture
        unset ::capture
    }
    if {[value g_DisplayScenery] && ![value g_ScrollReverse]} {
        set camera [word g_DisplayCamera]
        foreach {label lo hi} {seam_before 250 254 seam_after 256 260 wrap_before 506 510} {
            if {$camera >= $lo && $camera <= $hi && ![info exists ::seen($label)]} {
                set ::seen($label) 1
                snapshot $label
            }
        }
        if {[info exists ::previous_camera] && $camera < $::previous_camera && ![info exists ::seen(wrapped)]} {
            set ::seen(wrapped) 1
            snapshot wrapped
        }
        set ::previous_camera $camera
    }
}
proc guard {body} {
    if {[catch {uplevel #0 $body} message]} { bgerror $message }
}
debug watchpoint create -type write_mem -address $addr(g_Rendering) -command {guard rendering}
debug watchpoint create -type write_mem -address $addr(g_FramePublished) -command {guard publication}
proc snapshot {name} {
    set x [value g_DisplayX]
    set y [value g_DisplayY]
    set frame [value g_SelectedFrame]
    set page [value g_DisplayPage]
    if {[word g_MissedFrames] != 0} { error "Missed 25/30 Hz deadlines" }
    if {(([debug read {VDP regs} 2] >> 5) & 3) != $page} { error "Display page differs from state" }
    dump $name.vram [debug read_block VRAM 0 131072]
    dump $name.palette [debug read_block {VDP palette} 0 32]
    dump $name.regs [debug read_block {VDP regs} 0 32]
    after frame [list screenshot -raw [file join $::output $name.png]]
    puts $::report "snapshot $name $x $y $frame $page [word g_DisplayCamera] [value g_DisplayScenery] [value g_ScrollPaused] [value g_ScrollReverse]"
    flush $::report
}

proc capture {name} { set ::capture $name }
proc release {} { keymatrixup 4 160; keymatrixup 5 3; keymatrixup 8 241 }
proc press {row mask} { keymatrixdown $row $mask; after time 0.12 release }
proc begin {} {
    set ::measuring 1
    capture baseline
    after time 0.1 {press 5 1}
    after time 0.4 {capture enabled}
    after time 0.6 {keymatrixdown 8 64}
    after time 3.6 {keymatrixup 8 64; capture overlap}
    after time 4.0 {press 5 2}
    after time 4.8 {capture turned}
    after time 9.2 {press 4 32}
    after time 9.5 {capture paused}
    after time 10.0 {capture still_paused}
    after time 10.2 {press 4 128}
    after time 10.5 {press 4 32}
    after time 11.0 {capture reversed}
    after time 12.0 {press 5 1}
    after time 12.3 {capture disabled}
    after time 12.5 {keymatrixdown 8 32}
    after time 15.5 {keymatrixup 8 32; capture sky_restored}
    after time 15.8 {press 5 1}
    after time 16.1 {capture reenabled}
    after time 16.4 finish
}
proc finish {} {
    foreach name {seam_before seam_after wrap_before wrapped} {
        if {![info exists ::seen($name)]} { error "Missing boundary $name" }
    }
    if {[word g_MissedFrames]} { error "Missed deadlines" }
    # Separately force a late frame; it must be counted and wait for VBlank.
    unset ::measuring
    set ::inject_overrun 1
}
proc ready {} {
    if {[value g_Ready] == 1} {
        after time 0.1 begin
    } elseif {[machine_info time] > 15} { error "Startup timeout" } else { after time 0.1 ready }
}
after time 1 ready
