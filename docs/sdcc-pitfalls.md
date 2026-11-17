# SDCC code generation pitfalls

Compiler: SDCC 4.6.0 #16555 (Homebrew), Z80 target, as used by `build.sh`.

## Indexed loop over a struct array with a call in the body

Found 2026-11-14 by profiling `Combat_Advance`:

```c
for (i = 0; i < state->count; ++i) Advance(state, &state->projectile[i]);
```

SDCC loaded `state` into HL once, then at the loop head ran
`ld de,#0x96 / add hl,de / ld b,(hl)` to read `count`. Around the call, it
pushed and popped the already-offset HL, so each iteration added 0x96 again.
The loop bound came from `state + n*0x96`, which is unrelated RAM. The loop
called `Advance` about 15 times per weapon tick instead of `count` times. A
large stray byte could have walked past the 18-entry pool into the state
fields that follow it.

The fix walks a pointer with a local count:

```c
for (i = state->count, p = state->projectile; i; --i, ++p) Advance(state, p);
```

How to audit: in the generated `out/<project>/*.asm`, look for a loop whose
head reads HL incrementally (`add hl,..`) before it sets HL, with
`push hl` / `call` / `pop hl` in the body. When the scan was run on
2026-11-14, the release build had no other instance. The only other loop
head that reads HL first, in `Terrain_DrawColumn`, is a correct pointer walk.

The host tests use the native compiler and cannot catch this class of bug.
Emulator profiling (`tools/profile_p0.py`) found it through call counts.

## A loop that never runs drops the rest of the function

Found 2026-11-17 on map j, which has no islands (`ISLAND_COUNT` 0). In
`Smoke_Draw` the island flag's loop

```c
if (!far)
    for (i = 0; i < ISLAND_COUNT; ++i) { ... s_IslandFlagX[i] ... }
```

compiled to nothing, and so did everything after it: the soldiers, the
puffs, the rockets and the store of `g_SmokeDrawnCount`. The function
returned straight after the dugout loop above it. No warning. On map j no
smoke-path shape was ever drawn, engine smoke included.

The fix keeps the loop out of the build when the map has no islands
(`#if ISLAND_COUNT`). `soldiers.c` already returned early for the same
reason.

How to audit: build the map and compare each module's source-line
annotations (`;./src/...c:NNN:`) in `out/mission-flight-<map>/*.asm` with
map a's. A run of missing lines that are not conditional on the map is
dropped code. On 2026-11-17 the remaining differences (island, soldiers,
ships, surfaces) were all map data.
