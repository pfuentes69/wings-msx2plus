# Wings of Fury MSX2+ implementation plan

Updated 2026-11-12 after reviewing the supplied manuals and the English
Amiga/C64 manual transcription. The goal is the
manual's complete carrier-based game loop, using the recovered Amiga assets
on a standard-speed Panasonic FS-A1WX MSX2+ with V9958 and 128 KiB VRAM.

The [manual requirements and gap matrix](MANUAL_FUNCTIONAL_SPEC.md) is the
functional baseline and acceptance checklist. The [English Amiga/C64 transcription](AMIGA_ENGLISH_REFERENCE.md)
now supplies held-versus-short-click Fire, inventory and Amiga-only save/load
rules. It is transcribed manual text rather than a publisher scan. The
[French review](AMIGA_MANUAL_REVIEW.md) supplies keyboard and screen-right
approach instructions and records conflicting double-Fire wording. The
[Apple II guide](wingsoffurymanual.pdf) supplements omissions such as four cables.
Use Amiga executable/recordings to settle conflicts and numeric tuning; preserve
each source's edition and confidence.

P0 implementation and current validation are recorded in [the foundation report](p0-foundation.md).
[P1 flight and leftward takeoff](p1-flight.md) are implemented with provisional
tuning; timed Amiga fidelity and physical/raster acceptance remain open. The [carrier elevator/service subset](carrier-elevator.md) of P2 is now
implemented. Remaining P2 work includes actual landing, damage/fuel behavior and
life/crash handling. P0 corrects the input, inventory, HUD semantics and game-state
foundation. Complete a controllable carrier sortie and return loop before
expanding combat into a full mission. Further graphical glitches will be handled
when reported; this plan does not schedule another general dashboard art pass.

## Current implementation

| Area | Verified baseline | Remaining functional gap |
| --- | --- | --- |
| Build and platform | MSXgl/SDCC, 128 KiB ASCII8 ROM, native build/launcher, scripted openMSX | Physical hardware and final storage compatibility |
| Asset research | 73 recovered files, 12 unpacked archives/1,049 records; aircraft, terrain, dashboard and carrier effects decoded as needed | Complete enemy/weapon/ship animation exports and semantic gameplay tables |
| Mission data | All 15 map files parsed; a.map anchors, surface classes, depth and reset X recovered | Briefings, objectives, ranks, dynamic target/enemy initialization |
| Flight and views | P1 heading/throttle, stall modes, coupled turns, bidirectional deck taxi with ground-turn artwork/end stops, and leftward deck takeoff; scrolling and close/distant views | Timed Amiga tuning, landing and aircraft collisions |
| Scenery and dashboard | Original-art panels, waves, flag/radar/heave, altitude pilot profiles | Functional instruments, horizon/target distance, threat arrow, kill counter and damage/promotion semantics |
| Weapons | P0 primary/secondary controls, 30/15/1 stocks, three lives; two rounds plus sixteen bombs, held release at about four/second, and flat training impacts | Rockets/torpedoes, target damage, explosions and scoring |
| Audio | Original effects and music extracted/previewed | Runtime PSG/OPLL implementation and sound toggle |
| Validation | 124 host tests; release passes 89 NTSC/89 PAL snapshots, weapon renderer passes 64/71 full-VRAM checks including pitched cannon fire and bomb salvos | Fresh raster and physical FS-A1WX acceptance; later manual gameplay gates |

Current presentation is 7.5 fps NTSC / 6.25 fps PAL at eight VBlanks per frame.
Flight advances on a nominal 150 Hz clock; weapon simulation uses 25 Hz.
P0 headless regular weapon redraw maxima are approximately 88.65/94.22 ms with no
missed deadlines. Scale rebuilds still pause simulation for roughly 0.27–0.32 seconds
per page. Those transitions are a prototype limitation, not recovered behavior.
See [weapons measurements](combat-prototype.md) and [scenery notes](scenery-fidelity.md).

B1-B3 are completed rendering/control prototype milestones. The first B4 weapons
increment is validated, but the full B4 skirmish gate and B5 carrier gate are
not complete. Their former order is replaced by the dependency order below.

## Corrections established by the manual

| Prototype rule | Required direction |
| --- | --- |
| 30 gun rounds, four bombs | Loads are 30 bombs, 15 rockets or one torpedo; gun ammunition remains unspecified |
| Bomb icon with a gun-ammo counter | Icon and counter identify the selected secondary and its remaining stock |
| Static one-plane counter | Start with three Hellcats; promotion adds one |
| Trigger 1/Space resets, trigger 2 fires guns | User-selected MSX profile: trigger 1/Space fires guns; trigger 2/N/GRAPH releases the selected load; Ctrl-R restarts |
| Neutral stops the aircraft; pure up climbs | Neutral is 3/4 throttle; pure up stalls; pure down is a stall dive |
| Visual banking only | Reversing horizontal input turns and costs altitude |
| Airborne start and instant free replenishment | Start on deck, take off leftward, land by hook/cable, taxi to elevator and enter hold for service |
| No in-progress save/load | Named carrier saves with Ctrl-G, loading with Ctrl-L or the rank-menu Return from R & R command |
| Static oil, fuel and pilot reticle | Damage/oil/smoke, fuel exhaustion/warnings and a flashing white functional horizon |
| Impact flash treated as future scoring input | Distinct hit, destruction, aircraft kill, objective and mission events with once-only rewards |
| A map's visible scenery stands in for a mission | Explicit required islands/ships and dynamic soldiers/guns; fighters are not a kill-all requirement |

All references describe seven ranks; none maps them to the 15 recovered map
files. The English intro's two fighters are not a complete spawn script.
The Amiga transcription distinguishes held Fire from short clicks, gives a
one-torpedo load, and specifies Esc again to resume. French Space/Enter controls
and screen-right landing remain useful. Its double-Fire instruction conflicts
with the Amiga transcription. The user-selected MSX controls use two buttons
instead: trigger 2/N/GRAPH is secondary, while Enter stays in menus/text.
One-button source gestures are optional compatibility research, not P0 blockers.

Fifteen rockets, neutral 3/4 throttle, horizon flashing, mission bonuses,
bomber arrows and disk score saving now have Amiga-era corroboration. Four
cables remain an Apple-only count. Rocket target effectiveness, input timing
and other numeric behavior still need runtime checks. Named game saves add a
required writable-storage dependency; a volatile ROM-only table is insufficient.

## Implementation sequence and acceptance gates

### P0: rules, controls, inventory and state foundation

Requirements: FLOW-02/03 shell, LOAD-01/02/03/04, HUD-01/02, KEY-01/02/05, SAVE-01/02 foundation.

1. Introduce separate game, mission, sortie, control and render state. Move
   ammunition/loadout semantics out of the temporary projectile pool and HUD.
2. Implement the user's native MSX two-button profile: trigger 1/Space fires
   guns; trigger 2, N and GRAPH are simultaneous aliases of one logical
   secondary button. Aggregate aliases before edge detection to prevent duplicate
   releases. Route both logical buttons by context, including menus/elevator.
   Enter confirms menus/text only. Primary taps never release secondaries;
   do not delay gunfire for gesture recognition. Preserve short presses with
   frequent sampling and a bounded event queue, including during view rebuilds.
   Implement Esc-toggle pause, Ctrl-R rank restart and Ctrl-F inversion; consume
   input on context changes. Keep debug controls and any experimental Amiga
   one-button compatibility profile separate from this default.
3. Start a new game with three lives. Add rank/briefing/loadout state shells
   without inventing rank names, final briefing content or mission order. Include
   the Return from R & R load command without treating it as an eighth rank.
4. Make the HUD display selected secondary type/stock and lives. Bombs start
   at 30; reserve rocket stock of 15 for P3. Gunfire must not reduce the bomb
   counter. Remove the arbitrary 30-round gun limit; any interim unlimited-gun
   policy is marked provisional until checked in the Amiga version.
5. Encode the documented one-torpedo stock separately from the projectile pool;
   its release/energy model follows in P4. Add load/save UI state shells and a
   versioned session schema, with carrier-only save eligibility and loading from
   in-game or rank-menu contexts. Inventory, mission progress and life/score
   state must be serializable without renderer addresses.
6. Establish code/data bank boundaries and select a feasible writable storage
   profile now. Budget resident routines, banked tables, persistent state,
   event queues and effect pools before adding targets/AI. Standard ASCII8 ROM
   has no writable save facility; verify a cartridge save device or plan a
   disk/MSX-DOS deployment profile rather than assuming files can be written.

Gate: a host-tested context/action/state model; 30 bombs and three lives appear
correctly; primary fire leaves secondary stock unchanged; secondary fire consumes
one appropriate item; no negative inventory or charge on a failed allocation;
each secondary alias works independently across redraw boundaries; simultaneous
N/GRAPH/trigger-2 inputs generate one action, and switching between held aliases
cannot create another release. Holding the logical secondary never queues
repeated releases. Primary presses/holds fire only guns. Menus/elevator route the
same logical button without firing weapons. Enter never acts as an airborne
secondary. Pause freezes clocks and only Esc resumes; context changes clear
pending actions. Ctrl-R returns to rank selection. Verify keyboard and both
joystick buttons in NTSC/PAL and a data-level 30/15/1 inventory round trip.
Existing prototype shortcuts do not count as faithful restart.

### P1: flight semantics and leftward takeoff

Requirements: FLY-01 through FLY-04, CARR-01.

Implement heading-relative throttle/energy and flight modes instead of independent
free-axis motion. Neutral maintains 3/4 throttle, horizontal input gives full
throttle, diagonals climb/dive, pure up stalls and pure down stall-dives.
Horizontal reversal starts a turn with an altitude penalty; climb input can
compensate. Keep animation derived from simulation and heading state.

Start on the actual deck in a ground/taxi mode, then accelerate leftward and
climb near the edge. Recovered reset X=7032 is evidence about the original loader,
not sufficient evidence of the elevator position, deck-start height or heading.
Resolve the deck/cable/elevator geometry through source data and observation.

Gate: deterministic input traces cover all nine stick positions, left/right
symmetry, inversion, turn altitude loss and compensation. A normal launch leaves
the deck to the left without a debug teleport. PAL/NTSC traces agree in game time;
exact speeds, stall thresholds and penalties remain evidence-labeled tuning data.

### P2: landing, service, fuel, damage and lives

Requirements: CARR-02/03/04, HUD-03/04/05 carrier subset, HUD-06.

Implement airborne, approach, hook capture, landed, taxi, elevator transit,
hold/service and return-to-deck states. Add four arresting cables and hook-based
capture conditions. Approach from screen right toward the carrier moving left,
as stated in FR PDF 8; recover valid speed/height envelopes. Four cables remain
an English-edition fallback pending Amiga corroboration. A missed cable and a crash must be
different outcomes; the flat projectile training floor is not a landing solver.

Make the white horizon indicator blink and align meaningfully with the deck.
Use forward distance/altitude and carrier geometry for the pilot approach cue.
Add fuel consumption, health/oil state, progressive smoke, critical warning
lights, engine-seizure/fuel-empty crash paths and life/game-over handling.
Health changes can be injected by tests before enemy guns exist.

After landing, taxi over the elevator and activate it with either logical
button (trigger 1/Space or trigger 2/N/GRAPH). The hold
restores oil and fuel and offers a new loadout. Preserve mission progress across
service visits. Death retention, service duration and exact landing tolerances
require Amiga evidence; do not infer them from the static scene.

Gate: take off, fly, approach from screen right, stall onto a cable, stop, taxi,
activate the elevator with the logical button aliases, lower into the hold,
repair/refuel/rearm and launch again twice without resetting the mission. Cover
overshooting the elevator, missed-hook/go-around behavior, damage and fuel
warnings, seizure/exhaustion, one life decrement per crash and game over at zero.
The HUD must reflect state throughout. Validate landing controls at the actual
frame/input budget, not only in a host simulation.

### P3: island combat, soldiers, rockets and score events

Requirements: WPN-01/02/03, OBJ-01, HUD-07 score, PROG-01 event subset.

Recover target types, origins/hitboxes, dynamic soldiers and objective groups
for one island. Add barracks, machine-gun dugouts and large AA guns with intact,
damaged/destroyed states as supported by evidence. Do not assume the draw flag
list includes every target or invent soldier-spawn rules from barracks art.

Implement gun/bomb/rocket interactions and the documented 15-rocket loadout. Include air/ground rocket hit interactions
per the French description, with effectiveness checked against Amiga behavior.
Use swept collision
or an equivalent approach so projectiles cannot jump over small targets between
weapon ticks. Couple target fire to aircraft health/oil/smoke. Replace primitive
impact markers with source-backed effects where available and within budget.

Score only on explicit events; a repeated overlap or surface impact cannot award
repeated destruction points. Track required barracks, soldiers and guns by
identity and persist their destruction across service sorties.

Gate: a playable one-island skirmish. The island stays active while any required
soldier, barracks or gun survives, neutralizes once all are destroyed, and awards
its objective bonus once. Test weapon effectiveness, pool exhaustion, tunneling,
repeated hits, ground threats, service-return persistence and score consistency.
Unrecovered point values/durabilities stay visibly provisional in development.

### P4: enemy ships, gun suppression and torpedo runs

Requirements: WPN-04, OBJ-02, HUD-05 ship distance.

Separate ship gun state from hull/sinking state. The Amiga transcription requires
gun suppression before a torpedo run and gives one torpedo per load. Implement
that documented sequence and add low-water torpedo release, finite running energy/range and ship
collision. Retain one selected secondary per sortie, including a return to the
carrier for torpedo re-arming after suppressing guns with another load.

Gate: an armed ship cannot be counted as neutralized by a gun impact. Suppress
its guns, return/rearm as necessary, release the single torpedo within the
supported low/close envelope, and sink it. Stock reaches zero after release;
carrier rearming restores one. Distant releases expire without damage; a ship
objective completes only on sinking. Exact tolerances and hull/energy values
still need evidence before this phase is called faithful.

### P5: fighters, torpedo bombers and carrier defense

Requirements: WPN-01 aircraft, DEF-01/02/03, OBJ-03, HUD-07 kills.

Add bounded enemy aircraft state/AI, player/enemy hitboxes, kill events and oil
loss from incoming fire. Add torpedo bombers threatening Wasp, their dropped
torpedoes and the pilot-window relative-direction arrow. The English Amiga
transcription explicitly identifies the torpedo plane as the arrow's target;
recover visibility and update rules from gameplay. Bullets, bombs and
rockets must be able to destroy enemy torpedoes. Recover carrier damage and
failure rules instead of assuming one hit destroys it.

Gate: defeat a torpedo threat either by downing the bomber or intercepting its
weapon. Both routes protect the carrier. Kill icons and the numeric kill counter
agree with actual aircraft destruction; ground/ship kills do not increment them.
Mission completion does not require killing every incidental fighter. Combat
must remain playable during carrier approach/landing, with bounded CPU/VRAM use.

### P6: campaign, named save games and high scores

Requirements: FLOW-02/03 complete, OBJ-03, PROG-01/02, SCORE-01, KEY-04, SAVE-01/02.

Recover Amiga rank names/order, mission sets, briefings, objective bonuses and
completion timing. Build declarative mission records referencing the decoded
maps and dynamic entity templates; filenames do not determine difficulty.
Promotion grants exactly one life. Define and test death/retry/progression state
retention from evidence.

Implement named in-progress saves: Ctrl-G is available on the carrier and
returns to the current game after naming/saving. Ctrl-L opens the load menu
from in-game contexts; Return from R & R does so from rank selection. Determine
exact eligibility during deck/taxi/hold/elevator states from Amiga evidence.
Save all gameplay state needed for faithful continuation, including mission
progress and sortie/game values; recover any ambiguous timer/enemy retention
rules. Rebuild visual caches after load rather than serializing VDP data.

Add top-ten name entry with automatic rank recording, Ctrl-D display and Ctrl-C
clearing only from that view. Implement both score and game persistence on the
storage profile chosen in P0. ROM-only volatile development builds remain useful,
but do not satisfy the full manual persistence gate.

Gate: all seven ranks reach their configured missions; objective/mission bonuses
award once; promotion grants one plane; optional fighters cannot block progress.
A named save made on the carrier survives a restart. Both load entry points
restore the saved rank, lives, score, fuel/oil, selected load/stock and mission
state as required for continuation. Airborne Ctrl-G cannot create a save.
Invalid/incompatible saves leave the live game unchanged; failed writes preserve
the previous valid checkpoint. Qualifying high scores retain name/score/rank;
clearing is context-restricted. The load command is never counted as a rank.

### P7: startup/demo, audio and complete-game validation

Requirements: FLOW-01/04, KEY-03 and all earlier gates.

Add title and interruptible attract play, final menu/briefing presentation,
engine/weapons/damage effects and music adapted to PSG/optional MSX-MUSIC.
Ctrl-S must mute/unmute consistently. Add optional MSX mouse menu navigation,
matching the French menu's third input method; keyboard/joystick remain the
standard-machine baseline. Preserve the carrier narrative and game
flow without emulating Apple disk swapping. Finish original asset groups needed
for enemy/weapon/explosion states.

Gate: boot through demo/rank/briefing/loadout, complete a sortie and service
cycle under combat, finish an island and ship mission, defend against torpedoes,
advance rank, lose the remaining planes and save a qualifying score. Include
Esc-toggle pause/restart/inversion/mute, named save/load and persistence
failure/recovery checks. Run both
video standards and physical FS-A1WX hardware before release compatibility claims.

## Architecture and performance constraints

Keep portable C simulation independent of VDP/ROM access. Separate game, mission
and sortie lifetimes; feed all HUD values from those states. The MSX layer owns
input sampling, safe bank calls, draw budgets, VBlank publication and sound.
The Python pipeline owns source decoding, manifests and reproducible conversion.

The pre-P0 ROM used 31,529 of 32,768 resident bytes and 9,306 static RAM
bytes before IM2, stack and BIOS workspace. P0 moves dashboard streams to bank 12
and keeps ISR palette data in RAM; see the [current measured budget](p0-foundation.md).
Subsequent stages must maintain a measured RAM/entity and banked-code budget;
the existing four resident segments cannot absorb the rest of the game unchanged.
Keep the validated mapper restoration and disjoint VRAM allocator as contracts.

The current projectile pool is a performance choice, not a manual ammunition
limit. Use separate simulation/entity/effect budgets and measure worst-case
island fire, simultaneous aircraft/torpedoes, smoke and landing. Off-screen
simulation and objective state cannot disappear when a visual sprite is culled.
Preserve nominal game-time behavior across PAL/NTSC; prevent view rebuilds from
silently granting pauses in fuel drain or enemy attacks. Optimize transitions
and rendering before increasing active combat load. Do not silently depend on
turbo mode or upgrade the hardware target.

Retain a separate debug/training profile for renderer tests, instant reset and
direct pose inspection. Faithful gameplay must pass its gates with those helpers
disabled. Existing pixel checks remain valuable but do not establish gameplay
fidelity; add deterministic scenario/event tests and timed Amiga comparisons.

## Evidence work and completion policy

Use the English Amiga/C64 transcription and French Amiga-covering booklet
with their edition/confidence labels; use the Apple guide for explicit remaining
fallbacks. Use the extracted Amiga files,
minimal targeted executable analysis and recordings for unspecified behavior.
Keep source hashes and a source/edition/confidence label for recovered tables.
The open-question table in the functional spec is the research backlog.

A phase can have working prototype behavior while its numerical fidelity remains
unverified. Mark that distinction in its report; do not mark the manual gate
complete just because it renders or passes a test that repeats an assumption.
Further graphical corrections remain a feedback stream rather than blocking all
functional development. Keep existing source PDFs/notes and user artwork intact.

Existing evidence remains in [asset extraction](extraction-notes.md),
[shape format](format-shp.md), [mission mapping](mission-map.md),
[aircraft orientation](aircraft-orientation.md), [audio extraction](audio-extraction.md)
and [weapons prototype](combat-prototype.md). The original discovery prompt in
[CODEX_HANDOFF_PROMPT.md](../CODEX_HANDOFF_PROMPT.md) is historical context,
not the next-task list.
