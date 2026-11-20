# The music as the game plays it (docs/music.md), recorded to WINGS_RECORD:
# from the end of loading, the title and credits (subsong 1) and, at about
# 20 s, the story (subsong 2); at WINGS_RANK_AT seconds Escape goes to rank
# selection (subsong 4); recording stops at WINGS_STOP_AT seconds.
# WINGS_NO_FM=1 turns MSX-MUSIC off as it loads (the PSG alone).
# Run by tools/preview_music.py.
set save_settings_on_exit false
set throttle false
set power on
set pause false
set sf [open [file join $env(WINGS_ROOT) out mission-flight mission-flight.noi] r]
set symbols [read $sf];close $sf
foreach n {g_Ready g_SoundFM g_Music} {
    if {![regexp "DEF _$n (0x\[0-9A-Fa-f\]+)" $symbols -> a]} {error "Missing $n"}
    set addr($n) $a
}
if {$env(WINGS_NO_FM) eq "1"} {
    debug watchpoint create -type write_mem -address $addr(g_SoundFM) -command {
        if {[debug read memory $::addr(g_SoundFM)]} {debug write memory $::addr(g_SoundFM) 0}
    }
}
set log [open $env(WINGS_RECORD).log w]
debug watchpoint create -type write_mem -address $addr(g_Music) -command {
    if {[info exists ::start]} {puts $::log "music [debug read memory $::addr(g_Music)] at [format %.2f [expr {[machine_info time]-$::start}]]";flush $::log}
}
proc ready {} {
    if {[debug read memory $::addr(g_Ready)]!=1} {after time 0.05 ready;return}
    set ::start [machine_info time]
    set mute false
    record start -audioonly $::env(WINGS_RECORD)
    after time $::env(WINGS_RANK_AT) {keymatrixdown 7 4; after time 0.1 {keymatrixup 7 4}}
    after time $::env(WINGS_STOP_AT) {record stop;close $::log;exit}
}
after time 1 ready
