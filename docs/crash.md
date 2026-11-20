# The player's crash

Updated 2026-11-20. Follows the original as recovered in
[research/amiga-player-crash.md](research/amiga-player-crash.md). The old
port showed a one-second splash or explosion and then the next plane. Now
the plane falls, slides, and then sinks or burns, for 12 s.

## What happens

Every loss goes through one path, as in the original:

1. **Mode 4, `FLIGHT_DEAD`.** It starts in one of two ways:
   - the engine fails in the air (oil or fuel, `Flight_EngineOut`);
   - a flying plane touches the sea, the ground, scenery or a deck outside
     the landing rules (`Crash_Contact`, 0xba80). On land, or on a deck at
     altitude 20 or more, that contact also makes a burst 16 px ahead and
     a rocket-type impact on the column below. The impact can wreck a hut,
     empty a dugout or destroy a ship's gun, with a white or red flash.

   In mode 4 there is no control and no gun. The plane falls: its speed
   stays, the vertical step drops by 1 a tick down to −10, and the nose
   goes to −31°. Then it slides level, without wheels, losing 85 of speed
   a tick. That is 9..16 ticks and 38..115 px.
   - **Sea:** two splashes a tick ahead of the nose.
   - **Land:** each tick a burst with a boom, a rocket-type impact (hut,
     dugout, AA gun) with its flash, and soldiers within 8 px killed.
   - **Deck:** silent; on an enemy ship the plane rides the bob.
   - **Hull side:** the first 40 px of a hull, from the sea. The plane is
     thrown back with a red flash and a burst, then falls into the sea.
2. **At rest:**
   - **Mode 6, `FLIGHT_SINKING`:** the sea, or a deck below altitude 20.
     The plane goes down a pixel every 3 ticks, its nose turning from
     `hc05` to `hc0a` over 17 ticks. The waves cover it from the strip's
     third row. Silent water bursts within 8 px come every 1, 4, 8 or 12
     ticks for the first 6 s.
   - **Mode 8, `FLIGHT_WRECK`:** land or a deck. The wreck is `hcr5`
     facing right or `hcrf` facing left. A fire puff every 4 ticks
     (`smk5`, then smoke) drifts downwind, and explosions with booms come
     for the first 6 s.

   The oil gauge falls to 0, the dashboard lamps go out, and the engine
   falls silent.
3. **After 150 ticks (12 s), or with fire held after 30 ticks (2.4 s),**
   the plane is lost. The next one waits in the hold, as before. If no
   plane is left, the game is over.

The camera follows the plane throughout. Nothing of the wreck stays on the
map. The damage the crash did stays: huts, dugouts, soldiers and ship
guns.

## Differences from the original

| Original | Port | Why |
| --- | --- | --- |
| The sinking plane's altitude goes to −48. | The altitude stays at 2. The plane is drawn `g_Crash.depth` px lower and clipped at the waterline (VRAM row 163 − heave). | Many altitude reads are unsigned (camera, far view, pan). |
| A falling plane stops at the ground. Over a deck, the next tick lifts it onto the deck. | It stops on the deck. | No dip into the hull. |
| A fall that ends over the sea shows the land explosion. | It shows a water burst. | Looks right. |
| The hull hit moves the plane back 4 px more to the right, whichever way it faces. | Back by the full step + 4. | Quirk. |
| A stray slide explosion at a garbage x (0xb304). | Left out. | Bug. |
| "THE END" shows over the last plane's wreck. | It shows after the wreck's 12 s, over the frozen view. | The existing plate drawing; the user accepted the frozen view. |
| 0.4 s black playfield before the next plane. | Not done. | Not needed. |

## Code

- `src/core/crash.c` (segment 27, about 2.6 KB): `Crash_Contact` and
  `Crash_Tick`. The flight model (`Flight_Tick`) calls `Crash_Tick` in
  modes 4, 6 and 8 and spreads its motion over the tick's 12 steps.
- `src/world_flight.c`: contact is checked only while flying, in its own
  function (`StepContact`): written inline in the step loop, SDCC spilled
  its arithmetic to the stack, about 2 ms a frame more in busy frames
  (enough to miss a P0 deadline at the bow). The crash
  clock ends the plane (`LosePlane`). The wreck frame replaces the plane
  (`s_CrashFrame`, streamed into `CRASH_HOST_SHAPE`'s atlas slot). The
  sinking plane is drawn lower and clipped.
- The bursts are ordinary weapon bursts marked `COMBAT_CRASH_BURST`: drawn
  as bombs' bursts, with a boom on land and silent on the sea, and they
  hurt nothing (`Island_Impacts`, `Sound_Bursts`).
- The art: `tools/convert_hellcat.py` (`crash_assets`), `hcr5`/`hcrf`
  from hellcat.shp.

## Verification

- `tests/test_crash.py`: contact, the slide table, the sinking poses and
  depth, the water bursts, the island strikes and the wreck's puffs, the
  deck, the hull side and the crash clock.
- `tests/test_flight_model.py`: the engine-out fall, through the real
  crash code.
- `tools/verify_crash.py` (`tools/crash_smoke.tcl`, map a) crashes three
  planes:
  - into the sea, waited out;
  - into the island, ended with fire after 2.4 s;
  - the last one, with a dead engine onto the deck, which ends the game.

  It checks the modes, the timings, the slide and the sinking depth, and
  saves snapshots.
- `verify_p0`: the dry-tank plane sinks (its depth goes to the pixel
  model). The sea dive and the last plane take the full 12 s.

Results, 2026-11-20 (missed deadlines NTSC / PAL): `verify_crash` 1 / 0,
`verify_p0` 0 / 0, planes 19 / 1, ships 19 / 8, fighters 16 / 7, cockpit
0 / 0; all pass. The planes scenario now checks the kill before the
island limit (the chase's timing moves with every build).
