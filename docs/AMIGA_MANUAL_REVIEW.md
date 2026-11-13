# French Amiga manual review

Reviewed 2026-11-12 against rendered pages and the PDF's text layer. The supplied
[French manual](wingsoffurymanual-fr.pdf) covers Amiga alongside Atari ST,
Amstrad CPC and PC compatibles (PDF page 5); its credits explicitly identify
the Amiga and PC conversions (PDF page 2). It is a multi-platform booklet,
not an exclusively Amiga-specific technical specification.

Use PDF page numbers below: this 12-page scan has no reliable printed page
numbers. The [English Apple II guide](wingsoffurymanual.pdf) remains a clearer
supplement for omitted details, with its edition recorded. The original PDFs
and the user's English extraction remain unchanged.

## Update after the English Amiga reference

The [Amiga/C64 transcription review](AMIGA_ENGLISH_REFERENCE.md) supersedes the
earlier control conclusion: plan held Fire versus short clicks, keeping this
French double-Fire wording as a conflict. It also supplies one torpedo,
15 rockets, neutral 3/4 throttle, horizon flashing, bonuses, a bomber arrow,
score persistence, named carrier saves and Esc-toggle resume. The rows below
record what the French booklet itself says, not the final source precedence.

## Verified findings and plan consequences

| French PDF page | Reading from the page | Consequence |
| --- | --- | --- |
| 4-5 | Keyboard arrows/diagonals control flight; Space fires the machine guns; Enter releases bombs, rockets or torpedo | Source-platform binding only; MSX user choice is trigger 2/N/GRAPH for secondary, Space for gunfire |
| 4 | One Fire press is gunfire; two rapid consecutive Fire presses release the secondary | Retain as conflicting single-button evidence; the English Amiga text instead distinguishes hold from short click. Sample edges faster than redraws |
| 9 | The generic weapon section also mentions joystick buttons 0/1 | Internal inconsistency with page 4. Do not treat this as proof of two physical Amiga buttons; verify the target executable. MSX trigger 2 may be a documented convenience binding |
| 6-7 | Seven ranks; arrows, joystick or mouse navigate; Enter/button confirms; choose armament before takeoff | Keep rank/loadout flow; add an optional MSX mouse input profile to the plan |
| 4, 7 | Quick instructions allow a direction of takeoff with a leftward example; checklist prescribes full left, then up-left | Keep leftward takeoff as the documented default; confirm whether rightward takeoff also works in the Amiga game |
| 8 | Landing approach is explicitly from the right side of the screen; reversing horizontal input loses altitude | Resolve the approach-side ambiguity: approach toward the carrier from its right, moving left. Do not invent a wind-force simulation from the wind wording |
| 4-5, 8 | Up is used during the final landing phase; the flight diagram labels stall/stall dive and diagonal climb/dive | Keep stall-based landing and nine-position controls. The diagram does not label neutral as 3/4 throttle; that value remains an English-edition fallback |
| 9 | Taxi over the elevator; joystick button or Enter activates it; repair, refuel and rearm there | Source-platform binding; MSX uses the logical button aliases by context and consumes the event |
| 9-11 | Thirty bombs; three initial aircraft; one extra aircraft per promotion; HUD identifies carried weapon and stock | Confirms the inventory/life/HUD corrections. Neither gun ammo nor torpedo quantity is established |
| 9 | Rockets are described as useful against aircraft and ground targets | Plan air and ground rocket hit interactions; validate effectiveness against the Amiga game rather than restricting rockets to ground AA guns |
| 9 | Bombard the ship, return with a torpedo, release close and low over water | Confirms a staged attack/return/rearm/torpedo loop. The exact requirement that every ship gun be disabled is explicit in English, not in this French passage |
| 10-11 | Oil/damage/smoke, white pilot cursor, fuel warning/crash, island destruction, ship sinking and optional fighter kills | Confirms the functional HUD and objective model. The reused dashboard illustration is not sufficient evidence of every Amiga display format |
| 11 | A relative-direction arrow represents a threat called a "torpille volante" | The term is ambiguous between a torpedo-plane threat and the weapon itself. Confirm which entity drives the Amiga arrow; the English guide explicitly describes a torpedo plane |
| 11 | Top-ten name entry with automatically recorded rank | Confirms table contents. Disk persistence is explicit in English; this French paragraph does not specify storage |
| 12 | Esc, Ctrl-R, Ctrl-S, Ctrl-D, Ctrl-C and Ctrl-F | Confirms the special keys. The scan shows Ctrl-D, although OCR returned Ctrl-0. The score-view-only Ctrl-C restriction is stated in English, not repeated here |

## Translation and omission cautions

The French weapon description prints "50 mm" for the wing guns. The English
manual specifies .50 caliber. Do not turn that translation error into a different
weapon. The two guides also use different wind wording; screen approach side
is the useful French instruction, while aerodynamic wind effects are unspecified.

This booklet does not supply rocket stock, torpedo stock, exact rates/ranges,
neutral-throttle value, cable count, numerical damage/fuel/scoring rules, rank
names or rank-to-map assignments. Keep 15 rockets, 3/4 neutral throttle, four
cables, cursor flashing, objective/mission bonuses and save-to-disk behavior
identified as details absent from this booklet. The English Amiga transcription
now corroborates them except the four-cable count. An omission is not evidence
that the Amiga feature was removed.

Use the current source precedence in the [functional specification](MANUAL_FUNCTIONAL_SPEC.md).
The French booklet remains useful for direct keyboard bindings and approach
side; conflicting input timing must be checked against the target executable.

## Current P0 and P2 consequences

The user-selected MSX profile is trigger 1/Space for guns and trigger 2/N/GRAPH
for the selected secondary, with Enter reserved for menus/text. All secondary
aliases represent one button in every context; aggregate them before edge
detection. The Amiga tap/hold and French double-click schemes are evidence for
an optional compatibility profile, not requirements of the default MSX binding.
Context transitions consume pending input so no menu/elevator action fires a weapon.

P2 retains right-to-left carrier approach tests. Exact hook geometry, cable
count, capture tolerances and service timing still require Amiga evidence.
