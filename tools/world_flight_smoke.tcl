set save_settings_on_exit false
source [file join $env(WINGS_ROOT) tools pixel_display.tcl]
set mute true
set throttle true
set pause false
set power on
after realtime 0.1 {set power on; set pause false}
# Only the scripted matrix inputs should reach the test machine.
bind -layer codex_verification "keyb SPACE" {set ::ignored_host_input 1}
activate_input_layer -blocking codex_verification
catch {unplug joyporta}
keymatrixup 8 255
keymatrixup 5 2
keymatrixup 4 136
keymatrixup 8 1
set headless [expr {[info exists env(WINGS_HEADLESS)] && $env(WINGS_HEADLESS) eq "1"}]
if {$headless} {set throttle false} else {set renderer SDLGL-PP}
set maxframeskip 0
set root $env(WINGS_ROOT)
set output $env(WINGS_TEST_OUT)
set project [expr {[info exists env(WINGS_PROJECT)] ? $env(WINGS_PROJECT) : "mission-flight"}]
set report [open [file join $output emulator-report.txt] w]
proc bgerror {message} {
    puts $::report "FAIL $message\n$::errorInfo"
    flush $::report
    close $::report
    exit
}
set rom_project [expr {[info exists env(WINGS_ROM_PROJECT)] ? $env(WINGS_ROM_PROJECT) : $project}]
set f [open [file join $root out $rom_project $rom_project.noi] r]
set symbols [read $f]
close $f
foreach name {g_Ready g_Rendering g_FramePublished g_DisplayCamera g_DisplayWorld g_DisplayPage g_DisplayX g_DisplayY g_SelectedFrame g_Turning g_MissedFrames g_HoldFlight g_RenderPage} {
    if {![regexp "DEF _$name (0x\[0-9A-Fa-f\]+)" $symbols -> address]} { error "Missing $name" }
    set addr($name) $address
}
if {$project eq "mission-flight"} {
    if {![regexp {DEF _g_DisplaySurfaceWord (0x[0-9A-Fa-f]+)} $symbols -> address]} { error "Missing surface diagnostic" }
    set addr(g_DisplaySurfaceWord) $address
    foreach name {g_DisplayScale g_DisplayWave g_DisplayPilot g_ViewChange g_DisplayHeave g_DisplayShipFrame g_Combat g_GameView} {
        if {![regexp "DEF _$name (0x\[0-9A-Fa-f\]+)" $symbols -> address]} { error "Missing $name" }
        set addr($name) $address
    }

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
    if {[value g_Rendering]} {
        set ::start [machine_info time]
        if {[info exists ::last_publish]} {
            puts $::report "pre_render_ms [expr {1000*($::start-$::last_publish)}]"
        }
        set ::visible_base [expr {[value g_DisplayPage] * 32768}]
        if {[value g_RenderPage] == [value g_DisplayPage]} { error "Rendering into visible page" }
        set ::visible_pixels [debug read_block VRAM $::visible_base 27136]
    } elseif {[info exists ::start]} {
        if {$::visible_pixels ne [debug read_block VRAM $::visible_base 27136]} {
            error "Rendering changed the visible bitmap"
        }
        incr ::hidden_checks
        set kind render_ms
        if {$::project eq "mission-flight" && [value g_ViewChange]} { set kind transition_ms }
        puts $::report "$kind [expr {1000*([machine_info time]-$::start)}]"
    }
}
proc snapshot {name} {
    if {[info exists ::capturing] || [info exists ::suppress_captures]} { return 0 }
    set ::capturing 1
    file delete -force [file join $::output $name.png]
    dump $name.vram [debug read_block VRAM 0 131072]
    dump $name.regs [debug read_block {VDP regs} 0 32]
    if {$::project eq "mission-flight"} {
        dump $name.combat [debug read_block memory $::addr(g_Combat) 158]
        dump $name.game [debug read_block memory $::addr(g_GameView) 8]
    }
    dump $name.palette [debug read_block {VDP palette} 0 32]
    if {$::project eq "mission-flight"} {
        foreach symbol {g_Bank0Segment g_Bank1Segment g_Bank2Segment g_Bank3Segment} expected {0 1 2 3} {
            if {[debug read memory $::addr($symbol)] != $expected} { error "Mapper bank not restored: $symbol" }
        }
        # Compare actual cartridge visibility, not only the SDK's bank shadows.
        dump $name.rom [debug read_block memory 16384 32768]
    }
    puts $::report "snapshot $name [word g_DisplayCamera] [word g_DisplayWorld] [value g_DisplayX] [word g_DisplayY] [value g_SelectedFrame] [value g_DisplayPage] [value g_Turning]"
    if {$::project eq "mission-flight"} { puts $::report "surface $name [word g_DisplaySurfaceWord]"; puts $::report "view $name [value g_DisplayScale] [value g_DisplayWave] [value g_DisplayPilot]" }
    if {$::project eq "mission-flight"} { puts $::report "ship $name [value g_DisplayHeave] [value g_DisplayShipFrame]" }
    debug write memory $::addr(g_HoldFlight) 1
    if {!$::headless} { set ::throttle true }
    after time 0.1 [list finish_snapshot $name]
    return 1
}
if {$project eq "mission-flight"} {
    foreach name {g_Bank0Segment g_Bank1Segment g_Bank2Segment g_Bank3Segment} {
        if {![regexp "DEF _$name (0x\[0-9A-Fa-f\]+)" $symbols -> address]} { error "Missing $name" }
        set addr($name) $address
    }
}
proc finish_snapshot {name} {
    if {!$::headless} {
        screenshot -raw [file join $::output $name.png]
        if {$name in {initial fine_3 fine_2}} {
            screenshot [file join $::output $name-display.png]
        }
    }
    debug write memory $::addr(g_HoldFlight) 0
    set ::throttle false
    unset ::capturing
}
proc publication {} {
    if {![info exists ::measuring]} { return }
    if {[word g_MissedFrames]} { error "Missed frame deadline: [word g_MissedFrames], world [word g_DisplayWorld]" }
    if {!([debug read {VDP status regs} 2] & 64)} { error "Published outside VBlank" }
    set camera [word g_DisplayCamera]
    if {[info exists ::last_publish] && !($::project eq "mission-flight" && [value g_ViewChange])} {
        puts $::report "interval_ms [expr {1000*([machine_info time]-$::last_publish)}]"
    }
    set ::last_publish [machine_info time]
    incr ::count
    # Startup must be captured before opportunistic weapon/fine-phase images.
    if {[info exists ::capture] && $::capture eq "initial"} {
        if {[snapshot initial]} { unset ::capture }
    }
    if {$::project eq "mission-flight" && [info exists ::env(WINGS_WEAPONS)] && $::env(WINGS_WEAPONS) eq "1"} {
        set bombs 0
        for {set i 0} {$i < 18} {incr i} {
            set kind [debug read memory [expr {$::addr(g_Combat)+$i*8+7}]]
            if {$kind == 2} {incr bombs}
            if {$kind > 0} {
                set name weapon_$kind
                if {[value g_DisplayScale] == 8} { append name _far }
                if {![info exists ::weapon($name)] && [snapshot $name]} { set ::weapon($name) 1 }
                if {$kind == 2 && [value g_DisplayScale] == 1} {
                    set life [debug read memory [expr {$::addr(g_Combat)+$i*8+6}]]
                    set pose [expr {$life>95 ? 0 : $life>92 ? 1 : 2}]
                    set name bomb_pose_$pose
                    if {![info exists ::weapon($name)] && [snapshot $name]} { set ::weapon($name) 1 }
                }
            }
        }
    }
    if {[info exists bombs] && $bombs>=8 && ![info exists ::weapon(salvo)]} {
        if {[snapshot bomb_salvo]} {set ::weapon(salvo) 1}
    }
    if {$::count % 100 == 1} { snapshot sample_$::count }
    set phase [expr {$camera & 7}]
    if {![info exists ::fine($phase)] && $camera > 0} {
        if {[snapshot fine_$phase]} { set ::fine($phase) 1 }
    }
    set world [word g_DisplayWorld]
    if {$::project eq "mission-flight"} {
        foreach {name location} {carrier_tower 6912 dugout_1 1736 hut_1 2392 hut_2 2712 dugout_2 3224 island_coast 3944} {
            if {abs($world-$location) <= 12 && ![info exists ::landmark($name)]} {
                if {[snapshot $name]} { set ::landmark($name) 1 }
            }
        }
    }
    if {$::project eq "mission-flight" && [value g_DisplayScale]==8 && $world>=3880 && $world<=4100 && ![info exists ::landmark(distant_island)]} {
        if {[snapshot distant_island]} {set ::landmark(distant_island) 1}
    }
    set view_world $world
    if {$::project eq "mission-flight"} { set view_world [expr {$world / [value g_DisplayScale]}] }
    if {$view_world > 240 && $view_world < 256 && ![info exists ::seam(page)]} {
        if {[snapshot aircraft_page_seam]} { set ::seam(page) 1 }
    }
    if {$view_world > 496 && $view_world < 512 && ![info exists ::seam(ring)]} {
        if {[snapshot aircraft_ring_seam]} { set ::seam(ring) 1 }
    }
    if {[value g_Turning] && ![info exists ::turn([value g_SelectedFrame])]} {
        set frame [value g_SelectedFrame]
        if {[snapshot turn_$frame]} { set ::turn($frame) 1 }
    }
    if {[info exists ::capture]} {
        if {[snapshot $::capture]} { unset ::capture }
    }
    if {[info exists ::finishing] && ![info exists ::capturing]} {
        puts $::report "hidden_checks $::hidden_checks"
        puts $::report PASS
        unset ::measuring
        close $::report
        exit
    }
}
debug watchpoint create -type write_mem -address $addr(g_Rendering) -command {guard rendering}
debug watchpoint create -type write_mem -address $addr(g_FramePublished) -command {guard publication}
proc capture {name} { set ::capture $name }
proc terrain_turn {} {
    if {[info exists ::capturing]} { after time 0.12 terrain_turn; return }
    # Let the edge reach the simulation before another diagnostic capture hold.
    set ::suppress_captures 1
    keymatrixdown 5 2
    after time 0.25 {keymatrixup 5 2; unset ::suppress_captures}
}
proc begin {} {
    set ::count 0
    set ::hidden_checks 0
    set ::measuring 1
    capture initial
    if {$::project eq "mission-flight"} {
        if {[info exists ::env(WINGS_WEAPONS)] && $::env(WINGS_WEAPONS) eq "1"} {
            after time 0.15 {keymatrixdown 8 1; keymatrixdown 4 8}
            after time 1.5 {keymatrixup 4 8}
            after time 1.8 {keymatrixup 8 1}
            after time 72.2 {keymatrixdown 4 8}
            after time 72.7 {keymatrixup 4 8}
            after time 74.5 {keymatrixdown 8 1}
            after time 82 {keymatrixdown 4 8}
            after time 87 {keymatrixup 4 8}
            after time 147.4 {keymatrixdown 4 8}
            after time 147.65 {keymatrixup 4 8}
            after time 76 {keymatrixup 8 1}
        }
        after time 0.3 {keymatrixdown 8 80}
        after time 0.4 {capture ship_1}
        after time 0.7 {capture ship_2}
        after time 1.0 {capture ship_3}
        after time 1.3 {capture ship_4}
        after time 1.6 {capture ship_5}
        after time 6 {keymatrixup 8 64}
        after time 7 {capture terrain_flight}
        after time 70 {keymatrixup 8 16; capture left_bound}
        after time 71 {keymatrixdown 8 160}
        after time 74.4 {capture distant_climb}
        after time 88 {keymatrixup 8 32}
        after time 89 {capture top_clipped}
        after time 90 {capture left_climb}
        after time 100 {keymatrixup 8 128; keymatrixdown 8 16}
        after time 100.5 {capture distant_bank_1}
        after time 101 {capture distant_bank_2}
        after time 102 {keymatrixup 8 16; keymatrixdown 8 128}
        after time 102.5 {capture distant_bank_3}
        after time 143 {keymatrixup 8 128; capture right_bound}
        # A 150 ms pulse can fall entirely between PAL input polls. Hold
        # across multiple presentations and both close-view page rebuilds.
        after time 144 {set ::suppress_captures 1; keymatrixdown 4 128}
        after time 144.6 {keymatrixup 4 128; unset ::suppress_captures}
        after time 145.4 {capture reset}
        after time 146 terrain_turn
        after time 149 {capture stationary_turn}
        after time 150 {set ::finishing 1}
        return
    }
    after time 0.3 {keymatrixdown 8 192}
    after time 2.5 {keymatrixup 8 64}
    after time 4 {capture terrain_flight}
    set extra 0
    after time [expr {38 + $extra}] {keymatrixup 8 128; capture right_bound}
    after time [expr {39 + $extra}] {keymatrixdown 8 48}
    after time [expr {42 + $extra}] {capture left_climb}
    after time [expr {47 + $extra}] {keymatrixup 8 32}
    after time [expr {48 + $extra}] {capture top_clipped}
    after time [expr {80 + $extra}] {keymatrixup 8 16; capture left_bound}
    after time [expr {81 + $extra}] {keymatrixdown 8 1}
    after time [expr {81.15 + $extra}] {keymatrixup 8 1}
    after time [expr {81.4 + $extra}] {capture reset}
    after time [expr {82 + $extra}] terrain_turn
    after time [expr {83 + $extra}] {capture stationary_turn}
    after time [expr {83.3 + $extra}] {set ::finishing 1}
}
proc ready {} {
    if {[value g_Ready] == 1} { after time 0.1 begin
    } elseif {[machine_info time] > 20} { bgerror "Startup timeout"
    } else { after time 0.1 ready }
}
after time 0.1 ready
after time 200 {bgerror "Benchmark timeout"}
