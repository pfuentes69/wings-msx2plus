# Manual functionality and implementation gaps

Reviewed 2026-11-12. The [development plan](PORT_ANALYSIS_AND_STRATEGY.md)
implements these requirements in dependency order. This reference describes the
target behavior; it does not claim the existing prototype already provides it.

## Evidence and edition policy

The [English Amiga/C64 manual transcription](https://www.gamesdatabase.org/Media/SYSTEM/Commodore_Amiga/Manual/formated/Wings_of_Fury_-_1990_-_Br%C3%B8derbund_Software.htm)
now supplies explicit Amiga rules omitted from the local scans. **A** references
below follow its PAGE markers. The [English Amiga reference review](AMIGA_ENGLISH_REFERENCE.md)
records the additions and its transcription status; it is not a publisher scan.

The [French multi-platform manual covering Amiga](wingsoffurymanual-fr.pdf)
provides readable keyboard and approach instructions, cited as **FR PDF** pages.
The [French review](AMIGA_MANUAL_REVIEW.md) records translation issues/conflicts.
The clearer [Apple II guide](wingsoffurymanual.pdf) and its
[structured extraction](wingsoffurymanual.md) supplement missing details;
**EN** means Apple printed page (PDF page N+6). Relevant scanned pages and diagrams
were checked visually rather than relying on OCR alone.

Keep the recovered Amiga assets/data as the implementation source. Prefer
explicit Amiga references for version-specific rules; verify contradictions
against the Amiga executable/recordings. Keep French-specific, transcribed,
Apple-only and proposed MSX behavior distinguishable. Original source files
remain unchanged.

The extraction is left unchanged. The following qualifications govern its use:

- Machine-gun ammunition is unspecified. Its appendix's "likely unlimited"
  is an interpretation, not a documented rule. Thirty is the bomb load.
- A 8 explicitly establishes one torpedo, alongside 30 bombs and 15 rockets.
  Exact damage/range/rates, fuel consumption, oil thresholds, point values,
  rank names and mission sequences remain unspecified.
- The introductory two-fighter encounter is narrative context (pp. 1-2), not
  sufficient evidence that every first mission must spawn two fighters.
- FR PDF 8 explicitly places the landing approach on the right side of the
  screen, toward the carrier moving left. This resolves the earlier approach-side
  question. Wind wording differs between editions and does not define a wind-force
  model. Landing speed/height/capture thresholds still need Amiga evidence.
- A 7-8 distinguishes held Fire from short clicks; FR PDF 4 says double-Fire
  and PDF 9 mentions buttons 0/1. Do not equate a short click with two presses.
  Plan a tap/hold profile; measure timing and precedence in the Amiga game.
  French Space/Enter remains source evidence; the user-selected MSX mapping
  deliberately replaces Enter with N/GRAPH and joystick trigger 2.
- A 13 specifies Esc again to resume; FR/Apple specify any key. Use the Amiga
  Esc-toggle policy, recording the edition difference.
- Four arresting cables remain an Apple-only count. The Amiga transcription
  corroborates 15 rockets, neutral 3/4 throttle, a flashing white horizon,
  objective/mission bonuses, the bomber arrow and disk score persistence.
- Named in-progress saves are explicitly Amiga-only (A 12): on the carrier,
  Ctrl-G saves; Ctrl-L or the rank-menu load entry restores a game.
- The manual documents service, objectives and promotion, but does not specify
  every transition's timing, whether completion waits for a return landing, or
  which mission state survives death. The extraction's state diagram is a
  useful proposed structure, not proof of those missing rules.
- Apple disk flipping and hardware requirements are platform instructions.
  A cartridge-based MSX port needs no simulated disk-side prompt.

## Requirements and current gaps

Status refers to the current mission-flight prototype. "Partial" means there
is reusable infrastructure, not that the documented behavior is complete.
Phase names refer to the development plan.

| ID | Documented functionality | Sources (A transcription / EN Apple / FR PDF) | Current status and required change | Phase |
| --- | --- | --- | --- | --- |
| FLOW-01 | Title/attract flow; Amiga demo exits with the joystick button | A 3-4; EN 3; FR 6 | Missing; preserve interruptible attract flow without Apple disk prompts | P7 |
| FLOW-02 | Seven selectable ranks with increasing mission difficulty; arrows/joystick, Return/button confirms | A 5; EN 5; FR 6 | P0 seven-rank shell; names/order and difficulty remain P6 | P0 shell, P6 content |
| FLOW-03 | Briefing states that mission's objectives before play | A 5, 11; EN 5, 11; FR 6 | P0 practice briefing shell; authentic objectives remain P6 | P0 shell, P6 content |
| FLOW-04 | Mouse can also navigate rank selection | FR 6 | Missing; optional MSX mouse profile alongside required keyboard/joystick controls | P7 |
| LOAD-01 | Select one secondary type per sortie: bombs, rockets or torpedo; machine guns remain equipped | A 5, 8; EN 5, 7-8; FR 7, 9 | P0 selected-load state and previews; only bombs playable until P3/P4 | P0, P3-P4 |
| LOAD-02 | Carry 30 bombs or 15 rockets | A 8; EN 7; FR 9 (bombs) | P0 bombs 30; rocket stock 15 preview, weapon remains P3 | P0 bombs, P3 rockets |
| LOAD-04 | Torpedo load is one | A 8 | P0 stock 1 preview; launch behavior remains P4 | P0 data, P4 weapon |
| LOAD-03 | Hold Fire for guns; short Fire clicks release selected secondary; French double-Fire wording conflicts | A 7-8; EN 7-8; FR 4-5, 9 (conflict) | P0 native MSX profile: trigger 1/Space guns, trigger 2/N/GRAPH secondary; Amiga gesture compatibility deferred | P0 |
| FLY-01 | Neutral stick maintains 3/4 throttle in the current heading | A 6; EN 6 | P1 rounded 3/4 throttle; exact speed tuning unverified | P1 |
| FLY-02 | Left/right give full throttle in that direction; diagonals climb/dive in that direction | A 6; EN 5-6; FR 4-5, 7-8 | P1 heading/throttle with diagonal climb/dive; numeric tuning provisional | P1 |
| FLY-03 | Up alone stalls; down alone produces a stall dive | A 6; EN 6; FR 8 | P1 separate stall/stall-dive modes; numeric tuning provisional | P1 |
| FLY-04 | Reversing horizontal direction turns; turning loses altitude; climbing can compensate | A 6; EN 6; FR 8 | P1 simulation-clock bank with altitude loss and climb compensation | P1 |
| CARR-01 | Start on the carrier; take off leftward, then climb up-left near the deck edge | A 6; EN 5; FR 4, 7 | P1 deck start and normal leftward launch; parking X and speed provisional | P1 |
| CARR-02 | Approach from screen right, align with deck and stall/hook-capture; four cables is an EN fallback | A 7; EN 6 (four cables); FR 4-5, 8 | Missing; no aircraft collision or hook/cable model | P2 |
| CARR-03 | Taxi to elevator; joystick button or Enter lowers the aircraft; turn back if overshot | A 7; EN 7; FR 9 | Elevator/service implemented with heading retention; actual landing access remains P2 | P2 |
| CARR-04 | Hold service repairs oil pressure, refuels, and lets the player choose a new loadout | A 7, 9-10; EN 7, 9; FR 9-10 | Missing; unrestricted reset/replenishment is a debug shortcut | P2 |
| WPN-01 | Six .50-caliber guns attack aircraft and strafe islands | A 7; EN 7; FR 9 | Partial: small authored projectiles; no target damage; gun ammo policy unknown | P0 semantics, P3/P5 targets |
| WPN-02 | Bombs attack barracks and machine-gun dugouts | A 8; EN 7; FR 9 | Partial: only flat-surface flashes; no destructible targets | P3 |
| WPN-03 | Rockets attack aircraft/ground targets in French; English emphasizes heavy ground guns | A 8; EN 7; FR 9 | Missing | P3 |
| WPN-04 | A torpedo run follows disabling the ship's guns; release low over water and near enough to reach the ship | A 8; EN 8; FR 9 | Missing; stock is one; release envelope and energy/range need recovery | P4 |
| HUD-01 | Weapon icon/count identify the selected secondary and remaining load | A 9; EN 8; FR 11 | P0 selected-secondary icon/stock implemented | P0 |
| HUD-02 | Hellcat counter shows lives; start with three; gain one per promotion | A 9, 11; EN 9, 11; FR 10 | P0 starts at three, HUD driven by state; deaths/promotion remain P2/P6 | P0/P2, P6 promotion |
| HUD-03 | Oil pressure tracks engine damage; increasing damage adds smoke; critical warning blinks; seizure causes a crash | A 9; EN 9; FR 10 | Missing; oil dial is static | P2 state/service, P5 enemy damage |
| HUD-04 | Fuel decreases; critical warning blinks; exhaustion in flight causes a crash | A 10; EN 9; FR 10 | Missing; fuel dial is static | P2 |
| HUD-05 | Pilot window shows first-person distance to ships, planes and other targets | A 9; EN 9; FR 10 | Partial: eight altitude profiles and a surface lookahead; no target-distance projection | P2 carrier cue, P4-P5 entities |
| HUD-06 | Flashing white cursor is an artificial horizon for aiming and landing | A 7, 9; EN 6, 9; FR 10 | Wrong/incomplete: fixed colored reticle; no functional landing indicator | P2 |
| HUD-07 | Score displays game points; enemy aircraft kills have icons and a numeric count below score | A 10; EN 10; FR 10-11 | Missing: zeroes are artwork; lower pair must become kills, not another score/weapon field | P3 scoring, P5 kills |
| OBJ-01 | An island is neutralized only after all its barracks, soldiers and guns are destroyed | A 11; EN 11; FR 11 | Missing; static draw entries omit dynamic entities/objective semantics | P3 |
| OBJ-02 | Enemy ships must be sunk to be neutralized | A 11; EN 11; FR 11 | Missing; a gun hit or hull impact is not ship completion | P4 |
| OBJ-03 | Killing every fighter is not required to finish a mission | A 11; EN 11; FR 11 | Must be encoded explicitly in objective logic | P5-P6 |
| DEF-01 | Defend Wasp by destroying torpedo planes or their dropped torpedoes | A 1-2, 12; EN 1, 12; FR 3, 11 | Missing; carrier damage/failure thresholds are not given | P5 |
| DEF-02 | Bullets, bombs and rockets can destroy dropped enemy torpedoes | A 12; EN 12 | Missing; requires weapon-versus-projectile collision | P5 |
| DEF-03 | A pilot-window arrow indicates a spotted torpedo plane's relative position | A 12; EN 12; FR 11 (ambiguous term) | Missing; current surface display has no threat entity input | P5 |
| PROG-01 | Briefed objectives give individual bonuses, plus a whole-mission bonus | A 11; EN 11 | Missing; exact points and completion/return timing need recovery | P3 events, P6 progression |
| PROG-02 | Seven ranks provide progressively harder mission sets; promotion grants a plane | A 5, 9, 11; EN 5, 9, 11; FR 6, 10 | Missing; 15 map files do not establish their rank assignment | P6 |
| SCORE-01 | Top ten scores allow a name; rank is recorded automatically; save between sessions | A 12; EN 12; FR 11 | Missing; MSX cartridge needs an explicit persistence strategy | P6-P7 |
| SAVE-01 | Ctrl-G saves a named game while on the carrier, then returns to current play | A 12-13, explicitly Amiga-only | P0 shell and host-tested carrier-gated codec; actual eligibility/storage remain P2/P6 | P0 schema/backend, P6 feature |
| SAVE-02 | Load with Ctrl-L in game or Return from R & R on rank screen; select saved name and confirm | A 12-13 | P0 in-game and Return from R & R shells; actual loading remains P6 | P0 state shell, P6 feature |
| KEY-01 | Esc pauses and Esc again resumes for Amiga | A 13 (Esc toggle); EN 13 / FR 12 (any key) | P0 implemented; pause freezes game clocks and only Esc resumes | P0 |
| KEY-02 | Ctrl-R returns to rank selection | A 13; EN 13; FR 12 | P0 Ctrl-R resets at rank selection; debug R isolated | P0 |
| KEY-03 | Ctrl-S toggles sound | EN 13; FR 12 | Missing; extracted audio has not been integrated | P7 |
| KEY-04 | Ctrl-D shows scores; Ctrl-C clears them only after Ctrl-D | A 13; EN 13; FR 12 | Missing; scope clearing to the score-list state | P6 |
| KEY-05 | Ctrl-F reverses the joystick vertical axis | A 13; EN 13; FR 12 | P0 implemented before joystick mapping; keyboard unaffected | P0 |

## MSX input target

These are planned bindings, not the current prototype controls. The user's MSX
mapping takes precedence over the source platform's one-Fire gestures and Enter
binding. The default is a native two-button profile:

| Context | Primary action | Secondary action | Direction input |
| --- | --- | --- | --- |
| Rank/loadout menus | Enter or either logical button confirms | N/GRAPH/trigger 2 also confirm; no weapon release | Arrows/joystick change choice |
| Airborne | Space or joystick trigger 1 fires guns | N, GRAPH or joystick trigger 2 releases the selected secondary | Manual's nine-position flight mapping |
| Landed/taxiing over elevator | Either logical button activates elevator | N/GRAPH/trigger 2 behave as the same secondary button; no airborne weapon action | Ground taxi and turn rules |
| Pause | Esc again resumes and is consumed | Gameplay buttons cannot resume/fire | Simulation frozen |
| Save/load menus | Enter confirms text/selection | Logical button actions follow menu context, never weapon context | Joystick selects saved entry |
| Score list | Ctrl-C clears the table; return navigation to be defined | No in-flight controls | Menu navigation |

N, GRAPH and trigger 2 are simultaneous aliases of **one logical secondary
button**, available together without changing configuration. OR their pressed
states before detecting the logical edge. Pressing aliases together or pressing
GRAPH while N is already held must not release a second weapon; the logical
button must be released before another press is generated. This same logical
button is available to menus and elevator handling, not only the weapon code.

Space/trigger 1 is exclusively the gun action while airborne. A short primary
press must not release a secondary, and primary fire must not wait for a tap/hold
classifier in the default profile. Enter is reserved for menu confirmation and
text entry; it is not the MSX secondary weapon or elevator button. Do not add Z,
F or B as default aliases. Debug reset, pose inspection and stationary T remain
in a separate development profile.

Sample and timestamp keyboard/joystick edges frequently enough to preserve short
N/GRAPH/trigger-2 presses during redraws. Use a bounded queue, detect a single
secondary press after alias aggregation, and consume pending input on context
changes. A held secondary does not queue repeated releases. Menu/elevator/pause
transitions cannot leak an input into the next state.

The Amiga manual's held-Fire/short-click scheme and the French double-Fire
wording remain source evidence. A one-button compatibility profile may be
investigated separately, disabled by default; its timing is not a dependency for
the user-selected MSX two-button controls.

## State and data responsibilities

Use separate persistent game, mission and sortie data:

- `GameState`: chosen rank, three starting lives, score, aircraft kills, settings
  and the high-score table. Promotion increments lives exactly once.
- `MissionState`: briefing, explicit required objective groups, target states,
  ship gun/hull state, enemy aircraft/torpedoes and completion/bonus flags.
  Service visits retain mission progress. Death/restart retention rules need
  Amiga evidence rather than an assumed reset of every drawn map object.
- `SortieState`: flight mode, health/oil, fuel, selected secondary and its stock,
  weapon cooldowns, active projectiles, hook/cable contact and elevator status.
- `ControlState`: aggregated primary/secondary button states, timestamped edges,
  joystick axis inversion and context routing; optional one-button recognition
  is isolated from the default MSX profile.
  Pause blocks gameplay clocks without replaying held menu/fire edges.
- `RenderState`: derived HUD values, camera/projection, animation and clean
  footprints. Cached pixels must not decide inventory, damage or objectives.
- `SessionSnapshot`: versioned, asset-compatible gameplay state needed for a
  named carrier checkpoint. Rebuild render caches after load; never serialize
  VRAM pointers or bank-window addresses. Validate before replacing a live game.

The intended flow is title/attract, rank choice, briefing, loadout, deck/takeoff,
airborne, landing/taxi, elevator and service, then another sortie. Crashes feed
life/game-over handling; completed objectives feed mission completion/promotion;
eligible game-over scores feed name entry. Timing, death retention and the
mission-completion landing requirement remain research decisions.

Do not turn manual outcomes into guessed constants. Target durabilities,
per-target score, oil/fuel rates, stall/turn parameters, cable capture tolerances,
rank content and unknown numeric parameters belong in evidence-labeled data tables.

## Open evidence and tuning work

| Question | Evidence needed before claiming fidelity | Implementation consequence |
| --- | --- | --- |
| Optional one-button compatibility | A 7-8 versus FR PDF 4/9; Amiga input traces | Research timing only for a separate profile; default MSX uses trigger 1/Space and trigger 2/N/GRAPH |
| Gun ammunition finite or unlimited? | Amiga firing/inventory behavior or executable data | Remove the invented 30-round gun limit; provisional unlimited guns are an explicitly labeled policy until resolved |
| Torpedo release and energy | A 8 establishes stock of one; Amiga release/running traces still needed | Use stock one; recover release envelope and range/energy numerics |
| Exact flight, stall and turn response | Timed Amiga maneuvers, including neutral and pure-vertical input | Tune deterministic physics against recorded traces, not animation frame IDs |
| Landing capture conditions | FR PDF 8 resolves right-to-left approach; recordings and hook/cable/elevator logic are still needed | Recover permitted speed/height, cable count, crash versus missed-hook and taxi transitions |
| Damage and fuel rates | Gun-hit, smoke, warning, seizure, fuel-use and service observations | Establish thresholds, drain rates and service timing |
| Target/weapon effectiveness | Original hits on huts, dugouts, soldiers, AA and ship parts | Define hitboxes, durability and damage without assuming one-hit kills or arbitrary immunity |
| Pilot threat arrow behavior | A 12 identifies the torpedo plane; Amiga traces still needed | Use the bomber as the documented target; recover visibility, update and disappearance rules |
| Enemy and soldier behavior | Mission initialization and encounter traces | Do not invent soldier spawn rules from barracks artwork or treat every strip word as a target |
| Ranks, mission sets and promotion | Amiga rank selection, briefing/objective tables and completion behavior | Do not assign the 15 maps to seven ranks by filename order |
| Carrier loss, death and mission finish | Failure/completion/retry observations | Define mission failure and retained progress; no invented single-hit carrier loss |
| Score values, bonus sizes and kill overflow | Original score changes and counter behavior | Award once per event; choose display rollover only from evidence or a recorded MSX adaptation |
| Save mechanism on MSX | A 12 requires named game saves as well as top ten; target storage capabilities | Provide a tested writable backend for both; ordinary ASCII8 ROM has no persistent write facility |

An unresolved numeric detail may use a named prototype value for development,
but it must stay distinct from manual requirements and cannot satisfy the
corresponding fidelity acceptance gate by itself.
