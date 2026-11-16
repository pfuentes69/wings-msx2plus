# Each one-shot effect alone, through the game's own drivers (the PSG and,
# when the machine has it, MSX-MUSIC), recorded to WINGS_RECORD:
#   boom, splash, clang, screech, scream, 1.5 s apart.
# WINGS_NO_FM=1 turns the FM driver off as it loads (the PSG-only sound).
# Run by tools/preview_effects.py.
set save_settings_on_exit false
set throttle false
set power on
set pause false
set sf [open [file join $env(WINGS_ROOT) out mission-flight mission-flight.noi] r]
set symbols [read $sf];close $sf
foreach n {g_Ready g_SoundFM g_SoundRequest g_SoundRequestAtten} {
    if {![regexp "DEF _$n (0x\[0-9A-Fa-f\]+)" $symbols -> a]} {error "Missing $n"}
    set addr($n) $a
}
if {$env(WINGS_NO_FM) eq "1"} {
    debug watchpoint create -type write_mem -address $addr(g_SoundFM) -command {
        if {[debug read memory $::addr(g_SoundFM)]} {debug write memory $::addr(g_SoundFM) 0}
    }
}
proc ready {} {
    if {[debug read memory $::addr(g_Ready)]!=1} {after time 0.1 ready;return}
    set mute false
    record start -audioonly $::env(WINGS_RECORD)
    after time 0.5 {play {5 4 3 2 1}}
}
proc play {effects} {
    if {![llength $effects]} {after time 0.5 {record stop;exit};return}
    debug write memory $::addr(g_SoundRequestAtten) 0
    debug write memory $::addr(g_SoundRequest) [lindex $effects 0]
    after time 1.5 [list play [lrange $effects 1 end]]
}
after time 1 ready
