# English Amiga manual reference

Reviewed 2026-11-12: [Games Database's Amiga/C64 manual transcription](https://www.gamesdatabase.org/Media/SYSTEM/Commodore_Amiga/Manual/formated/Wings_of_Fury_-_1990_-_Br%C3%B8derbund_Software.htm).
Page references below follow its PAGE markers. This is transcribed manual text,
not a publisher scan; typographic errors and conflicts still need runtime checks.

| Page | Additional evidence | Planning consequence |
| --- | --- | --- |
| 6 | Neutral throttle is 3/4 | Corroborates the Apple diagram for Amiga-era documentation |
| 7-8 | Hold Fire for guns; short clicks for secondary weapons | Optional compatibility evidence; user-selected MSX secondary is trigger 2/N/GRAPH |
| 8 | Loads are 30 bombs, 15 rockets or one torpedo | Torpedo stock is no longer unknown |
| 9, 11-12 | Flashing white horizon, objective bonuses, torpedo-plane arrow and persistent top-ten scores | These no longer rely solely on Apple evidence |
| 12 | Save on the carrier with Ctrl-G and a name; return to play | Add named checkpoints and carrier-only save eligibility |
| 12-13 | Ctrl-L opens loading; rank menu also has Return from R & R | Add loading in game and from the menu; this is not an eighth rank |
| 13 | Esc resumes when pressed again | Amiga pause policy supersedes any-key resume |

The exact Fire timing remains unmeasured. Gun ammo limits, four-cable count and
numeric simulation/damage/score rules remain unresolved for Amiga. The French
manual still supplies Space/Enter keyboard controls and explicit screen-right
landing approach. The [specification](MANUAL_FUNCTIONAL_SPEC.md) and
[plan](PORT_ANALYSIS_AND_STRATEGY.md) integrate these sources without changing
current gameplay code.

The user-selected MSX binding overrides the source-platform gesture: Space/trigger
1 fires guns; N, GRAPH and trigger 2 are equivalent secondary-button inputs.
Enter is for menus/text. See the functional specification for alias aggregation
and context routing; no gameplay change is implied by this reference review.
