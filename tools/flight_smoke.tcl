# Deterministic input and display validation, invoked by verify_flight.py.
set save_settings_on_exit false
set mute true
set maxframeskip 0
set root $env(WINGS_ROOT)
set output $env(WINGS_TEST_OUT)
set report [open [file join $output emulator-report.txt] w]
set f [open [file join $root out wings.noi] r]
set symbols [read $f]
close $f
foreach name {g_Ready g_SelectedFrame g_DisplayPage g_DisplayX g_DisplayY g_FacingLeft g_Rendering g_RenderCount g_MissedFrames g_FramePublished} {
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
    if {![info exists ::measuring]} { return }
    if {[value g_Rendering]} { set ::start [machine_info time] } elseif {[info exists ::start]} {
        puts $::report "render_ms [expr {1000*([machine_info time]-$::start)}]"
        unset ::start
    }
}
proc publication {} {
    if {![info exists ::measuring]} { return }
    if {!([debug read {VDP status regs} 2] & 64)} { error "Publication outside VBlank" }
    if {[info exists ::last_publish]} {
        puts $::report "interval_ms [expr {1000*([machine_info time]-$::last_publish)}]"
    }
    set ::last_publish [machine_info time]
}
debug watchpoint create -type write_mem -address $addr(g_Rendering) -command {rendering}
debug watchpoint create -type write_mem -address $addr(g_FramePublished) -command {publication}
proc snapshot {name} {
    set x [value g_DisplayX]
    set y [value g_DisplayY]
    set frame [value g_SelectedFrame]
    set left [value g_FacingLeft]
    set page [value g_DisplayPage]
    if {[word g_MissedFrames] != 0} { error "Missed 25/30 Hz deadlines" }
    if {(([debug read {VDP regs} 2] >> 5) & 3) != $page} { error "Display page differs from state" }
    dump $name.vram [debug read_block VRAM 0 65536]
    dump $name.palette [debug read_block {VDP palette} 0 32]
    dump $name.regs [debug read_block {VDP regs} 0 32]
    screenshot -raw [file join $::output $name.png]
    puts $::report "snapshot $name $x $y $frame $left $page [word g_RenderCount]"
    flush $::report
}
proc keys {mask} {
    keymatrixup 8 241
    if {$mask} { keymatrixdown 8 $mask }
}
proc stage1 {} { snapshot up_right; keys 0; after time 0.6 stage2 }
proc stage2 {} { snapshot coast; keys 80; after time 0.4 stage3 }
proc stage3 {} { snapshot down_left; keys 1; after time 0.12 stage4 }
proc stage4 {} { snapshot reset; keys 128; after time 3 stage5 }
proc stage5 {} { snapshot right_bound; keys 32; after time 3 stage6 }
proc stage6 {} { snapshot top_bound; keys 16; after time 3 stage7 }
proc stage7 {} { snapshot left_bound; keys 64; after time 3 stage8 }
proc stage8 {} { snapshot bottom_bound; keys 1; after time 0.12 finish }
proc finish {} {
    snapshot final_reset
    keys 0
    puts $::report PASS
    close $::report
    exit
}
proc ready {} {
    if {[value g_Ready] == 1} {
        after time 0.1 {
            snapshot initial
            set ::measuring 1
            keys 160
            after time 0.35 stage1
        }
    } elseif {[machine_info time] > 15} { error "Startup timeout" } else { after time 0.1 ready }
}
after time 1 ready
