# Shared openMSX harness for the emulator smoke runs (tools/p0_smoke.tcl,
# tools/ships_smoke.tcl): the boot settings, symbol lookup, snapshot
# capture at frame publication, the visible-page and split checks, the
# closed-loop autopilot and the carrier circuit. Each script defines
# `ready` (and `landed_on_lift`) and starts with `after time 1 {guard ready}`.
set save_settings_on_exit false
set mute true
if {$env(WINGS_HEADLESS) eq "0"} {set renderer SDLGL-PP}
set throttle false
set pause false
set power on
after realtime 0.1 {set power on; set pause false}
source [file join $env(WINGS_ROOT) tools pixel_display.tcl]
catch {unplug joyporta}
bind -layer codex_verification "keyb SPACE" {set ::ignored_host_input 1}
activate_input_layer -blocking codex_verification
foreach {r m} {3 24 4 138 5 2 6 6 7 132 8 255} {keymatrixup $r $m}
set out $env(WINGS_TEST_OUT)
# WINGS_RECORD=file.wav: the whole run's sound, for listening.
if {[info exists env(WINGS_RECORD)] && $env(WINGS_RECORD) ne ""} {set mute false;record start -audioonly $env(WINGS_RECORD)}
set report [open [file join $out emulator-report.txt] w]
# WINGS_ROM: the ROM under test (default: map a's release ROM); its .noi
# gives the symbols. ::extra_symbols, set before sourcing, adds more.
if {![info exists env(WINGS_ROM)] || $env(WINGS_ROM) eq ""} {set env(WINGS_ROM) [file join $env(WINGS_ROOT) out mission-flight mission-flight.rom]}
set sf [open [file rootname $env(WINGS_ROM)].noi r]
set symbols [read $sf];close $sf
foreach n [concat [list Input_JoySample g_SoundPlaying g_SoundFM g_TerrainSlotStrip g_DisplayBand g_DisplayTicker g_MessageActive g_HudScore g_DisplayScore g_SmokeDrawn g_SmokeDrawnCount g_Smoke g_Island g_DisplayFine g_PanOverruns g_DisplayRope g_DisplayWheel g_DisplayGear g_DisplayCrash s_World g_LastContact g_DisplayGauges g_Engine g_Game g_Controls g_Ready g_GameView g_Combat g_FramePublished g_DisplayPage g_DisplayCamera g_DisplayWorld g_DisplayY g_SelectedFrame g_DisplayWave g_DisplayHeave g_DisplayShipFrame g_DisplayScale g_ViewChange g_VBlankTicks g_Carrier g_DisplayElevator g_CrewFrame g_TaxiTurn g_HoldFlight g_MissedFrames g_InputOverflow g_Turning g_Rendering g_RenderPage] {*}[expr {[info exists extra_symbols] ? $extra_symbols : {}}]] {
    if {![regexp "DEF _$n (0x\[0-9A-Fa-f\]+)" $symbols -> a]} {error "Missing $n"}
    set addr($n) $a
}
# Inject digital levels at the PSG read boundary; exercises both native trigger
# bits through the actual ISR, OR mapping and queue, without a physical pad.
set joy 63
debug set_bp $addr(Input_JoySample) {} {reg A $::joy}
proc value {n} {debug read memory $::addr($n)}
proc word {n} {expr {[value $n]+256*[debug read memory [expr {$::addr($n)+1}]]}}
proc view {i} {debug read memory [expr {$::addr(g_GameView)+$i}]}
proc stat {offset} {incr offset 122;expr {[debug read memory [expr {$::addr(g_Combat)+$offset}]]+256*[debug read memory [expr {$::addr(g_Combat)+$offset+1}]]}}
proc require {ok message} {if {!$ok} {error $message}}
proc bgerror {m} {puts $::report "FAIL $m\n$::errorInfo";flush $::report;close $::report;catch {record stop};exit}
proc guard {code} {if {[catch {uplevel #0 $code} m]} {bgerror $m}}
proc dump {name bytes} {set f [open [file join $::out $name] wb];puts -nonewline $f $bytes;close $f}
proc phase {wanted then} {
    if {[view 0]==$wanted} {after time 0.05 $then} else {after time 0.025 [list phase $wanted $then]}
}
proc cursor {wanted then} {
    if {[view 6]==$wanted} {after time 0.05 $then} else {after time 0.025 [list cursor $wanted $then]}
}
proc pulse {row mask then} {
    keymatrixdown $row $mask
    after time 0.05 [list keymatrixup $row $mask]
    after time 0.8 $then
}
proc snap {name then} {set ::pending [list $name $then]}
proc finish {name then} {
    if {$::env(WINGS_HEADLESS) eq "0"} {
        screenshot -raw [file join $::out $name.png]
        if {$name in {rank loadout start paused}} {screenshot [file join $::out $name-display.png]}
        set ::throttle false
    }
    unset ::capturing
    if {[string match "taxi_more *" $then] || [string match "lift_pose *" $then]} {
        uplevel #0 $then
        debug write memory $::addr(g_HoldFlight) 0
    } else {
        debug write memory $::addr(g_HoldFlight) 0
        after time 0.06 $then
    }
}
# The close-view pan's top lines (above line heave + fine) show VRAM rows
# -heave .. fine - 1 of the displayed page at the heave-only scroll. Terrain
# starts at row 24, so they must be plain sky: anything else (smoke, the
# plane) shows there in the wrong place.
# More state per snapshot: a script may redefine this.
proc snapshot_extra {name} {}
proc smoke_count {} {debug read memory [expr {$::addr(g_SmokeDrawnCount)+[value g_DisplayPage]}]}
proc top_split_check {} {
    set band [value g_DisplayBand]
    if {$band} {
        # The message band (src/msx/message.c): VRAM rows 0 .. band + 1
        # show unscrolled (a late split included): sky, text rows 1..12 in
        # ink 11 only. Scenery starts at row 24.
        set base [expr {[value g_DisplayPage]*32768}]
        for {set r 0} {$r<$band+2 && $r<24} {incr r} {
            binary scan [debug read_block VRAM [expr {$base+$r*128}] 128] cu* bytes
            set x 0
            foreach b $bytes {
                if {$r>=1 && $r<=12 ? ($b & 15) ni {0 11} || ($b >> 4) ni {0 11} : $b} {error "Band row $r not sky/text: world=[word g_DisplayWorld] y=[word g_DisplayY] band=$band x=[expr {$x*2}] byte=$b"}
                incr x
            }
        }
        return
    }
    if {[value g_DisplayScale]!=1} {return}
    set fine [value g_DisplayFine];set heave [value g_DisplayHeave]
    if {$fine>127} {set fine [expr {$fine-256}]}
    set base [expr {[value g_DisplayPage]*32768}]
    # The split comes up to 2 lines early: rows 254..255 show too.
    set first [expr {$fine>0 && $heave<2 ? -2 : -$heave}]
    for {set r $first} {$r<$fine} {incr r} {
        binary scan [debug read_block VRAM [expr {$base+(($r+256)%256)*128}] 128] cu* bytes
        set x 0
        foreach b $bytes {
            if {$b} {error "Overlay in the top split rows: world=[word g_DisplayWorld] y=[word g_DisplayY] fine=$fine heave=$heave row=$r x=[expr {$x*2}] byte=$b"}
            incr x
        }
    }
}
proc publishing {} {
    if {![info exists ::armed]} {return}
    if {[word g_MissedFrames]} {
        # Profiling aid (WINGS_ALLOW_MISSED=1): log misses instead of failing.
        if {[info exists ::env(WINGS_ALLOW_MISSED)]} {
            puts $::report "missed world=[word g_DisplayWorld] y=[word g_DisplayY] render=$::last_render"
            debug write memory $::addr(g_MissedFrames) 0
            debug write memory [expr {$::addr(g_MissedFrames)+1}] 0
        } else {error "Frame deadline missed: stage=[value g_Carrier] depth=[value g_DisplayElevator] pose=[value g_SelectedFrame] render=$::last_render"}
    }
    top_split_check
    set now [machine_info time]
    set ::last_publish $now
    set stage [value g_Carrier]
    if {[view 0]==3 && $stage in {0 2}} {
        if {[info exists ::lift_last] && $::lift_stage==$stage && !$::lift_rebuild && ![value g_ViewChange]} {
            puts $::report "lift_cadence [expr {1000*($now-$::lift_last)}] $::last_render"
        }
        set ::lift_last $now;set ::lift_stage $stage;set ::lift_rebuild [value g_ViewChange]
    } else {unset -nocomplain ::lift_last}
    if {![info exists ::pending] || [info exists ::capturing]} {return}
    if {[info exists ::wanted_height]} {
        if {[value g_DisplayHeave]!=$::wanted_height} {return}
        unset ::wanted_height
    }
    if {[info exists ::wanted_frame]} {
        if {[value g_SelectedFrame] ni $::wanted_frame} {return}
        unset ::wanted_frame
    }
    if {[info exists ::wanted_smoke]} {
        if {[smoke_count]<$::wanted_smoke} {return}
        unset ::wanted_smoke
    }
    if {[info exists ::wanted_y]} {
        # A published close-view altitude band (the close-view pan).
        lassign $::wanted_y low high
        set yy [word g_DisplayY]
        if {[value g_DisplayScale]!=1 || $yy<$low || $yy>$high} {return}
        unset ::wanted_y
    }
    if {[info exists ::wanted_rope]} {
        # Mid-arrest, so the rope is well stretched.
        if {[value g_DisplayRope]==255 || [speed]>700} {return}
        unset ::wanted_rope
    }
    if {[info exists ::wanted_turn]} {
        # Capture each new deck-turn pose; when the turn ends, drop the
        # pending capture and continue.
        if {![value g_Turning]} {
            if {$::turn_seen} {unset ::pending ::wanted_turn;after time 0.05 $::turn_done}
            return
        }
        if {[value g_SelectedFrame]==$::last_turn_pose} {return}
        set ::last_turn_pose [value g_SelectedFrame];set ::turn_seen 1
    }
    if {[info exists ::wanted_depth]} {
        if {[value g_DisplayElevator]!=$::wanted_depth || [value g_Carrier]!=$::wanted_stage} {return}
        unset ::wanted_depth;unset ::wanted_stage
    }
    lassign $::pending name then;unset ::pending;set ::capturing 1
    foreach {suffix device address size} {vram VRAM 0 131072 regs {VDP regs} 0 32} {
        dump $name.$suffix [debug read_block $device $address $size]
    }
    dump $name.lift [debug read_block memory $::addr(g_Carrier) 3]
    dump $name.view [debug read_block memory $::addr(g_DisplayScale) 3]
    dump $name.crew [debug read_block memory $::addr(g_CrewFrame) 1]
    dump $name.gauges [debug read_block memory $::addr(g_DisplayGauges) 3]
    dump $name.flight [debug read_block memory $::addr(s_World) 37]
    dump $name.crash [debug read_block memory $::addr(g_DisplayCrash) 1]
    dump $name.wheel [binary format ccc [value g_DisplayWheel] [value g_DisplayGear] [value g_DisplayRope]]
    # What the shown page drew (src/msx/smoke_draw.h): count, then x (2),
    # row (2), frame per shape; 27 entries per page.
    set page [value g_DisplayPage]
    dump $name.smoke [binary format c [smoke_count]][debug read_block memory [expr {$::addr(g_SmokeDrawn)+$page*66*5}] [expr {66*5}]]
    dump $name.score [debug read_block memory $::addr(g_DisplayScore) 4]
    dump $name.island [debug read_block memory $::addr(g_Island) 315]
    dump $name.band [binary format cs [value g_DisplayBand] [word g_DisplayTicker]]
    dump $name.psg [debug read_block {PSG regs} 0 16]
    # The tile cache (src/msx/mission_streamer.c): each slot's strip.
    dump $name.slots [debug read_block memory $::addr(g_TerrainSlotStrip) 52]
    # MSX-MUSIC (src/msx/sound_fm.c): whether the driver runs, its registers.
    dump $name.fm [binary format c [value g_SoundFM]][expr {$::fm_regs eq "" ? "" : [debug read_block $::fm_regs 0 0x39]}]
    dump $name.palette [debug read_block {VDP palette} 0 32]
    dump $name.fine [debug read_block memory $::addr(g_DisplayFine) 1]
    dump $name.game [debug read_block memory $::addr(g_GameView) 8]
    dump $name.combat [debug read_block memory $::addr(g_Combat) 160]
    dump $name.rom [debug read_block memory 16384 32768]
    snapshot_extra $name
    puts $::report "snapshot $name [value g_DisplayPage] [word g_DisplayWorld] [word g_DisplayY] [value g_SelectedFrame] [value g_DisplayWave] [value g_DisplayHeave] [value g_DisplayShipFrame] [word g_DisplayCamera]"
    debug write memory $::addr(g_HoldFlight) 1
    # Unthrottled openMSX skips rendering; let real frames render before the
    # raster screenshot (emulated timing is unaffected).
    if {$::env(WINGS_HEADLESS) eq "0"} {set ::throttle true}
    after time 0.08 [list finish $name $then]
}
proc rendering {} {
    if {![info exists ::armed]} {return}
    if {[value g_Rendering]} {
        set ::render_start [machine_info time]
        if {[info exists ::last_publish] && [stat 30]>0} {puts $::report "pre_render [expr {1000*($::render_start-$::last_publish)}]"}
        set ::visible_base [expr {[value g_DisplayPage]*32768}]
        require [expr {[value g_RenderPage]!=[value g_DisplayPage]}] "Rendering visible page: render=[value g_RenderPage] display=[value g_DisplayPage] phase=[view 0] pc=[format %04x [reg pc]] sp=[format %04x [reg sp]] ret=[format %04x [expr {[debug read memory [reg sp]]+256*[debug read memory [expr {[reg sp]+1}]]}]]"
        set ::pixels [debug read_block VRAM $::visible_base 27136]
    } elseif {[info exists ::pixels]} {
        set ::last_render [expr {1000*([machine_info time]-$::render_start)}]
        set now [debug read_block VRAM $::visible_base 27136]
        if {$::pixels ne $now} {
            set rows {}
            for {set r 0} {$r<212} {incr r} {
                if {[string range $::pixels [expr {$r*128}] [expr {$r*128+127}]] ne [string range $now [expr {$r*128}] [expr {$r*128+127}]]} {lappend rows $r}
            }
            set r [lindex $rows 0];set diff {}
            binary scan [string range $::pixels [expr {$r*128}] [expr {$r*128+127}]] cu* before
            binary scan [string range $now [expr {$r*128}] [expr {$r*128+127}]] cu* after
            for {set i 0} {$i<128} {incr i} {if {[lindex $before $i]!=[lindex $after $i]} {lappend diff "x[expr {$i*2}]:[lindex $before $i]>[lindex $after $i]"}}
            error "Visible page changed during redraw: rows [lrange $rows 0 20] page=[value g_DisplayPage] render=[value g_RenderPage] y=[word g_DisplayY] world=[word g_DisplayWorld] camera=[word g_DisplayCamera] diff=[lrange $diff 0 30]"
        }
        unset ::pixels
    }
}
proc missed_frame {} {
    if {![info exists ::last_publish]} {return}
    set puffs 0
    for {set i 0} {$i < 8} {incr i} {if {[debug read memory [expr {$::addr(g_Smoke)+$i*10+8}]]} {incr puffs}}
    puts $::report "deadline elapsed=[expr {1000*([machine_info time]-$::last_publish)}] render=$::last_render puffs=$puffs shapes=[smoke_count] oil=[debug read memory [expr {$::addr(g_Game)+14}]] stage=[value g_Carrier] world=[word g_DisplayWorld] vblank=[value g_VBlankTicks] viewchange=[value g_ViewChange] camera=[word g_DisplayCamera] scale=[value g_DisplayScale] y=[word g_DisplayY] hudscore=[debug read_block memory $::addr(g_HudScore) 8] score=[debug read_block memory $::addr(g_Game) 4]"
    flush $::report
}
debug watchpoint create -type write_mem -address $addr(g_FramePublished) -command {guard publishing}
# The machine's MSX-MUSIC registers, if any. WINGS_NO_FM=1 turns the FM
# driver off as it loads, to test the PSG-only sound.
set fm_regs [lsearch -inline -nocase [debug list] "*music regs"]
if {[info exists env(WINGS_NO_FM)] && $env(WINGS_NO_FM) eq "1"} {
    debug watchpoint create -type write_mem -address $addr(g_SoundFM) -command {
        if {[value g_SoundFM]} {debug write memory $::addr(g_SoundFM) 0}
    }
}
# Each effect the PSG driver starts (src/msx/sound.c).
debug watchpoint create -type write_mem -address $addr(g_SoundPlaying) -command {
    if {[info exists ::armed] && [value g_SoundPlaying]} {puts $::report "sound [value g_SoundPlaying] world=[word g_DisplayWorld] stage=[value g_Carrier]"}
}
debug watchpoint create -type write_mem -address $addr(g_Rendering) -command {guard rendering}

proc game_byte {offset value} {debug write memory [expr {$::addr(g_Game)+$offset}] $value}
proc engine_byte {offset} {debug read memory [expr {$::addr(g_Engine)+$offset}]}
proc lift_pose {name stage depth then} {
    set ::wanted_stage $stage;set ::wanted_depth $depth
    snap $name $then
}
proc wait_lift_up {then} {
    if {[value g_Carrier]!=1 || [value g_DisplayElevator]!=0} {after time 0.025 [list wait_lift_up $then];return}
    after time 0.05 $then
}
proc engine_takeoff {then} {
    # Roll off the bow, then climb away.
    fly 16
    wait_for {[world_byte 12]==1} [list engine_climb $then] "engine takeoff roll" 15
}
proc engine_climb {then} {
    fly 48
    wait_for {[world_y]<1100} [list engine_airborne $then] "engine takeoff climb" 10
}
proc engine_airborne {then} {
    fly 16
    require [expr {[engine_byte 3]==0}] "Engine scenario takeoff"
    uplevel #0 $then
}

# Closed-loop flying from the real flight state (s_World, SDCC layout):
# y (Q8 u32) +2, vx +6, facing_left +11, mode +12 (0 deck, 1 air, 2 arrest),
# turn +13, fast_roll +17, speed +21, climb +23; world x (Q8 u32) +31.
proc world_byte {offset} {debug read memory [expr {$::addr(s_World)+$offset}]}
proc world_s16 {offset} {set v [expr {[world_byte $offset]+256*[world_byte [expr {$offset+1}]]}]; expr {$v>=32768 ? $v-65536 : $v}}
proc world_x {} {expr {[world_byte 32]+256*[world_byte 33]}}
proc world_y {} {expr {[world_byte 3]+256*[world_byte 4]+65536*[world_byte 5]}}
proc world_vx {} {world_s16 6}
proc speed {} {world_s16 21}
proc climb {} {world_s16 23}
proc turn_shapes {} {set l {};for {set i 10} {$i<40} {incr i} {lappend l $i};return $l}
proc fly {mask} {keymatrixup 8 [expr {241 & ~$mask}]; if {$mask} {keymatrixdown 8 $mask}}
proc wait_for {cond then what {limit 30}} {
    set ::wait_deadline [expr {[machine_info time]+$limit}]
    wait_poll $cond $then $what
}
proc wait_poll {cond then what} {
    if {[uplevel #0 [list expr $cond]]} {after time 0.02 $then;return}
    require [expr {[machine_info time]<$::wait_deadline}] "Timeout: $what x=[world_x] y=[world_y] mode=[world_byte 12] speed=[speed] climb=[climb] turn=[world_byte 13]"
    after time 0.01 [list wait_poll $cond $then $what]
}
# Autopilot: hold a horizontal direction (which also turns the plane round)
# and trim the commanded climb toward a target altitude (screen y).
proc pilot {heading target} {
    set running [info exists ::pilot]
    set ::pilot [list $heading $target]
    if {!$running} {pilot_tick}
}
proc pilot_off {} {unset -nocomplain ::pilot;fly 0}
proc pilot_tick {} {
    if {![info exists ::pilot]} {return}
    lassign $::pilot heading target
    # Input is sampled once per frame (1.7 ticks NTSC, 2 PAL) and Up/Down
    # move the climb 600 per tick (300 diving in a turn), so trim within a
    # band of one step around the wanted climb. Without Up or Down a climb
    # decays to level but a dive holds. Heading 0 coasts (no power, airspeed
    # bleeds toward 1000); corrections then use the facing key.
    set error [expr {[world_y]-$target}]
    set want [expr {$error>40 ? 2400 : $error>2 ? 1200 : $error<-150 ? -3600 : $error<-40 ? -2400 : $error<-2 ? -1200 : 0}]
    set key [expr {$heading ? $heading : [world_byte 11] ? 16 : 128}]
    set c [climb]
    set mask $heading
    if {$want==0} {
        if {$c<0} {set mask [expr {$key|32}]}
    } elseif {$c<$want-600} {set mask [expr {$key|32}]} elseif {$c>$want+600} {set mask [expr {$key|64}]}
    fly $mask
    after time 0.02 pilot_tick
}
# The carrier's reset x (the elevator): 7032 on map a; a script sets it
# for other maps. The circuit and the landing are relative to it.
if {![info exists ::cx]} {set ::cx 7032}
# Pixels short of the braking distance the taxi stops powering.
if {![info exists ::taxi_margin]} {set ::taxi_margin 2}
# A snapshot's name in the landing; a script may redefine it.
proc sname {name} {return $name}
proc circuit {then} {
    # From takeoff (flying left off the bow): out to the left and back past
    # the carrier, low (y 1140, 60 px up); coast downwind to bleed speed so
    # the cable arrest is short; turn onto final out over the open sea past
    # the map's end, settle 5 px above deck contact, and flare near the stern.
    set ::circuit_then $then
    pilot 16 1140
    wait_for {[world_x]<$::cx-1032} {pilot 128 1140;wait_for {![world_byte 11] && ![world_byte 13]} circuit_downwind "turn downwind" 10} "outbound" 15
}
proc circuit_downwind {} {
    pilot 128 1140
    wait_for {(abs([world_y]-1140)<=4 && [climb]==0) || [world_x]>$::cx-632} {pilot 0 1140;wait_for {[world_x]>=$::cx+768} circuit_turn_final "downwind" 30} "settle downwind" 15
}
proc circuit_turn_final {} {
    pilot 16 1155
    wait_for {[world_byte 11] && ![world_byte 13]} circuit_on_final "turn onto final" 10
}
proc circuit_on_final {} {
    # Level or descending at the flare: from a climb the flight path takes
    # several ticks to turn down and the touchdown comes too late.
    wait_for {[world_x]<=$::cx+398 && (abs([world_y]-1155)<=2 && [climb]<=0 || [world_x]<$::cx+348)} circuit_final "final approach" 10
}
proc circuit_final {} {
    puts $::report "final x=[world_x] y=[world_y] speed=[speed] climb=[climb]"
    require [expr {[world_x]>$::cx+298 && [world_y]>=1150 && [world_y]<=1158}] "Final approach not set up: x=[world_x] y=[world_y]"
    pilot_off
    uplevel #0 $::circuit_then
}
proc land_circuit {} {circuit land_flare}
proc land_flare {} {
    # The stall flare (Up alone, facing left) onto the deck; keep Up held so
    # the hook catches a cable.
    debug write memory $::addr(g_LastContact) 0
    fly 32
    wait_for {[value g_LastContact]!=0} land_touch "touchdown" 6
}
proc land_touch {} {
    require [expr {[value g_LastContact]==1 && [world_byte 12]!=1 && [world_y]==1160 && [world_byte 11]}] "Stall onto the deck must land: contact=[value g_LastContact] mode=[world_byte 12] y=[world_y]"
    puts $::report "touchdown x=[world_x] speed=[speed]"
    # Caught: the original draws the stretched rope while the cable holds.
    wait_for {[world_byte 12]==2} {set ::wanted_rope 1;snap [sname arrest] {wait_for {[world_byte 12]==0 && [speed]==0} land_stopped "arrest" 3}} "cable catch" 2
}
proc land_stopped {} {
    fly 0
    require [expr {[world_x]>$::cx+6 && [world_y]==1160}] "Arrested past the elevator: x=[world_x]"
    snap [sname landed] land_taxi
}
proc land_taxi {} {
    set ::wait_deadline [expr {[machine_info time]+30}]
    land_taxi_wait
}
# Distance rolled while braking from a deck speed: 8 per tick, (speed + 50) / 100 px.
proc braking_distance {speed} {
    set d 0
    while {$speed>0} {incr speed -8;if {$speed<0} {set speed 0};incr d [expr {($speed+50)/100}]}
    return $d
}
proc land_taxi_wait {} {
    # Power while the distance left exceeds the braking distance plus one
    # tick of input latency; creep the last pixels.
    set d [expr {[world_x]-$::cx}]
    if {[speed]==0 && abs($d)<=6} {
        fly 0
        require [expr {abs([world_x]-$::cx)<=6}] "Taxi did not stop on the elevator: x=[world_x]"
        landed_on_lift
        return
    }
    require [expr {$d>-6 && [machine_info time]<$::wait_deadline}] "Taxi overshot or timed out: x=[world_x]"
    set v [expr {[speed]+8}]
    # Below speed 50 the plane does not move (whole pixels per tick).
    if {$d>6 && [braking_distance $v]+($v+50)/100 < $d-$::taxi_margin} {fly 16} else {fly 0}
    after time 0.01 land_taxi_wait
}

proc done {} {
    require [expr {[value g_InputOverflow]==0}] "Input queue overflow in normal scenarios"
    puts $::report "pan_overruns [word g_PanOverruns]"
    puts $::report "PASS";flush $::report;close $::report;catch {record stop};exit
}
debug watchpoint create -type write_mem -address $addr(g_MissedFrames) -command {guard missed_frame}
