# Invoked by verify_screen5.py; uses the generated linker symbols, never fixed RAM addresses.
set save_settings_on_exit false
set mute true
set maxframeskip 0
set root $env(WINGS_ROOT)
set output $env(WINGS_TEST_OUT)
set report [open [file join $output emulator-report.txt] w]
set f [open [file join $root out wings.noi] r]
set symbols [read $f]
close $f
foreach name {g_SelectedFrame g_DisplayPage g_Rendering g_RenderCount} {
    if {![regexp "DEF _$name (0x\[0-9A-Fa-f\]+)" $symbols -> address]} {
        error "Missing linker symbol $name"
    }
    set addr($name) $address
}

proc save_binary {name bytes} {
    set f [open [file join $::output $name] wb]
    puts -nonewline $f $bytes
    close $f
}

proc count_renders {} {
    expr {[debug read memory $::addr(g_RenderCount)] + 256 * [debug read memory [expr {$::addr(g_RenderCount) + 1}]]}
}

proc profile_render {} {
    # Ignore RAM initialization and boot; profile the three interactive redraws.
    if {![info exists ::measure_ready]} { return }
    if {[debug read memory $::addr(g_Rendering)] == 1} {
        set ::render_start [machine_info time]
    } elseif {[info exists ::render_start]} {
        puts $::report "render_ms [expr {1000 * ([machine_info time] - $::render_start)}]"
        unset ::render_start
    }
}

debug watchpoint create -type write_mem -address $addr(g_Rendering) -command {profile_render}

proc snapshot {name expected_frame expected_page expected_count} {
    set selected [debug read memory $::addr(g_SelectedFrame)]
    set page [debug read memory $::addr(g_DisplayPage)]
    set count [count_renders]
    set reg2 [debug read {VDP regs} 2]
    if {$selected != $expected_frame || $page != $expected_page || $count != $expected_count || (($reg2 >> 5) & 3) != $page} {
        error "Unexpected $name state: selected=$selected page=$page count=$count reg2=$reg2"
    }
    save_binary $name.vram [debug read_block VRAM 0 65536]
    save_binary $name.palette [debug read_block {VDP palette} 0 32]
    save_binary $name.regs [debug read_block {VDP regs} 0 32]
    screenshot -raw [file join $::output $name.png]
    puts $::report "snapshot $name $selected $page $count"
    flush $::report
}

proc press_key {mask} {
    keymatrixup 0 14
    keymatrixdown 0 $mask
    set ::key_time [machine_info time]
}

proc stage_two {} {
    snapshot key2 1 1 2
    after time 0.2 {stage_hold}
}
proc stage_hold {} {
    snapshot held2 1 1 2
    press_key 8
    after time 0.2 {stage_three}
}
proc stage_three {} {
    snapshot key3 2 0 3
    press_key 2
    after time 0.2 {stage_one}
}
proc stage_one {} {
    snapshot return1 0 1 4
    keymatrixup 0 14
    puts $::report PASS
    close $::report
    exit
}

proc selection_changed {} {
    if {[info exists ::key_time]} {
        if {!([debug read {VDP status regs} 2] & 64)} {
            error "Display page was published outside VBlank"
        }
        puts $::report "flip_in_vblank 1"
        puts $::report "selection_latency_ms [expr {1000 * ([machine_info time] - $::key_time)}]"
        unset ::key_time
    }
}
debug watchpoint create -type write_mem -address $addr(g_SelectedFrame) -command {selection_changed}

proc await_ready {} {
    if {[count_renders] == 1 && ![debug read memory $::addr(g_Rendering)] && ([debug read {VDP regs} 1] & 64)} {
        # Give the renderer a complete visible frame after startup.
        after time 0.1 {
            snapshot initial 0 0 1
            set ::measure_ready 1
            press_key 4
            after time 0.2 {stage_two}
        }
    } elseif {[machine_info time] > 15} {
        error "ROM did not become ready in 15 emulated seconds"
    } else {
        after time 0.1 {await_ready}
    }
}
after time 1 {await_ready}
