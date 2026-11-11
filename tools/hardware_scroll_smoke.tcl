set save_settings_on_exit false
set mute true
set throttle true
set maxframeskip 0
set root $env(WINGS_ROOT)
set output $env(WINGS_TEST_OUT)
set report [open [file join $output emulator-report.txt] w]
proc bgerror {message} {
    puts $::report "FAIL $message\n$::errorInfo"
    flush $::report
    close $::report
    exit
}
set f [open [file join $root out hardware-scroll hardware-scroll.noi] r]
set symbols [read $f]
close $f
foreach name {g_Ready g_Rendering g_FramePublished g_DisplayCamera g_MissedFrames g_StreamedColumns g_Paused g_Reverse g_StreamWorld g_HoldCamera} {
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
proc guard {body} { if {[catch {uplevel #0 $body} message]} { bgerror $message } }
proc rendering {} {
    if {![info exists ::measuring]} { return }
    if {[value g_Rendering]} { set ::start [machine_info time] } elseif {[info exists ::start]} {
        puts $::report "render_ms [expr {1000*([machine_info time]-$::start)}]"
    }
}
proc snapshot {name} {
    if {[info exists ::capturing]} { return 0 }
    set ::capturing 1
    file delete -force [file join $::output $name.png]
    dump $name.vram [debug read_block VRAM 0 131072]
    dump $name.regs [debug read_block {VDP regs} 0 32]
    dump $name.palette [debug read_block {VDP palette} 0 32]
    puts $::report "snapshot $name [word g_DisplayCamera] [value g_Paused] [value g_Reverse]"
    # A raw screenshot is the most recently completed raster, which still
    # precedes this VBlank's register writes. Hold the camera for a full raster.
    debug write memory $::addr(g_HoldCamera) 1
    set ::throttle true
    after time 0.1 [list finish_snapshot $name]
    return 1
}
proc finish_snapshot {name} {
    screenshot -raw [file join $::output $name.png]
    debug write memory $::addr(g_HoldCamera) 0
    set ::throttle false
    unset ::capturing
}
proc publication {} {
    if {![info exists ::measuring]} { return }
    if {[word g_MissedFrames]} { error "Missed frame deadline: [word g_MissedFrames], camera [word g_DisplayCamera], time [machine_info time]" }
    if {!([debug read {VDP status regs} 2] & 64)} { error "Published outside VBlank" }
    set camera [word g_DisplayCamera]
    if {[info exists ::last_publish]} {
        puts $::report "interval_ms [expr {1000*([machine_info time]-$::last_publish)}]"
    }
    set ::last_publish [machine_info time]
    incr ::count
    if {$::count % 100 == 1} { snapshot sample_$::count }
    set phase [expr {$camera & 7}]
    if {![info exists ::fine($phase)]} {
        if {[snapshot fine_$phase]} { set ::fine($phase) 1 }
    }
    foreach {label lo hi direction} {
        page_before 252 255 0 page_after 256 260 0
        ring_before 508 511 0 ring_after 512 516 0
        reverse_page_before 3840 3844 1 reverse_page_after 3835 3839 1
    } {
        if {$camera >= $lo && $camera <= $hi && [value g_Reverse] == $direction && ![info exists ::seam($label)]} {
            if {[snapshot $label]} { set ::seam($label) 1 }
        }
    }
    if {$::stage == 0 && $camera > 4080} { set ::stage 1 }
    if {$::stage == 1 && $camera < 8} {
        snapshot forward_wrap
        # Pause via the actual P key, then reverse using R.
        keymatrixdown 4 32
        after time 0.12 {keymatrixup 4 32}
        after time 0.3 {snapshot paused}
        after time 0.8 {snapshot still_paused; keymatrixdown 4 128}
        after time 0.95 {keymatrixup 4 128; keymatrixdown 4 32}
        after time 1.1 {keymatrixup 4 32}
        set ::stage 2
    }
    if {$::stage == 2 && [value g_Reverse] && ![value g_Paused] && $camera > 4080} {
        snapshot reverse_wrap
        set ::stage 3
    }
    if {$::stage == 3 && $camera < 3600 && ![info exists ::capturing]} {
        snapshot reversed
        puts $::report "columns [word g_StreamedColumns]"
        puts $::report "offscreen_checks $::stream_checks"
        puts $::report PASS
        unset ::measuring
        close $::report
        after time 0.2 exit
    }
}
proc streaming {} {
    if {![info exists ::measuring]} { return }
    set column [expr {[word g_StreamWorld] & 511}]
    set camera [word g_DisplayCamera]
    for {set x 0} {$x < 256} {incr x} {
        set ring [expr {($camera + $x) & 511}]
        if {$ring >= $column && $ring < $column + 8} {
            error "Streaming into displayed pixels: column $column, camera $camera"
        }
    }
    incr ::stream_checks
}
debug watchpoint create -type write_mem -address $addr(g_Rendering) -command {guard rendering}
debug watchpoint create -type write_mem -address $addr(g_FramePublished) -command {guard publication}
debug watchpoint create -type write_mem -address [expr {$addr(g_StreamWorld) + 1}] -command {guard streaming}
proc ready {} {
    if {[value g_Ready] == 1} {
        set ::count 0
        set ::stream_checks 0
        set ::stage 0
        set ::measuring 1
    } elseif {[machine_info time] > 15} { error "Startup timeout" } else { after time 0.1 ready }
}
after time 0.1 ready
after time 80 {bgerror "Benchmark timeout"}
