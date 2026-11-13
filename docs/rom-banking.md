# Mission ROM code banking

Updated 2026-11-13. Applies to `mission-flight` and `mission-flight-debug`.

The P1/elevator release had filled the four resident ASCII8 segments
(32,472 of 32,768 bytes). Later phases need far more code, so the mission ROM
now banks code and grows to 256 KiB.

## Memory map

| CPU window | Address | Contents |
| --- | --- | --- |
| 0 | 4000h–5FFFh | Resident segment 0: crt0, `Scenery_Read`, ISRs, input sampler |
| 1 | 6000h–7FFFh | Resident segment 1; `Scenery_Read` borrows it for data and restores it |
| 2 | 8000h–9FFFh | Resident segment 2 |
| 3 | A000h–BFFFh | **Banked code**: segment 3 at boot, then the last banked call's segment |

| ROM segment | Use |
| --- | --- |
| 0–2 | Resident code and constants |
| 3 | Banked code: `WINGS_SEGMENT_HUD` (dashboard, weapons) |
| 4–15 | Raw data banks, unchanged (mission, dashboard, aircraft, waves, ship, elevator) |
| 16 | Banked code: `WINGS_SEGMENT_SCENE` (menu, ship, carrier elevator) |
| 17–31 | Free for code or data |

Measured release layout (after the cannon overlay change; the banking change itself left 3,411 resident bytes free):

| Area | Used | Free |
| --- | --- | --- |
| Resident 4000h–9FFFh | 22,372 bytes | 2,204 of 24,576 |
| Segment 3 | 6,006 bytes | 2,186 |
| Segment 16 | 4,821 bytes | 3,371 |
| Static RAM (`_DATA`) | 11,071 bytes | n/a |

The debug profile is smaller (20,917 resident bytes; its segment 16 omits the
P1 elevator). Every build prints these figures in its post-build step.

## How it works

- `src/msx/banking.h` assigns module groups to segments (`WINGS_SEGMENT_*`).
  A banked module starts with `WINGS_CODE_SEGMENT(WINGS_SEGMENT_x)`, which
  places all its code, constants and string literals in area `_SEGn`.
- Public functions of banked modules are declared and defined `WINGS_BANKED`
  (`__banked`). SDCC calls them through `___sdcc_bcall_ehl`, which saves the
  current window-3 segment, switches, calls and restores it. Arguments are
  passed on the stack; return values in A/DE survive. Calls into another
  banked segment work the same way, and so do calls inside one segment.
- `src/msx/banking.c` provides the resident `set_bank`/`get_bank` helpers.
  They write the ASCII8 window-3 register (7800h) and crt0's `g_Bank3Segment`.
- `mission-flight.js` reads the `WINGS_SEGMENT_*` values and links each
  segment at `(segment << 16) | A000h`; MSXhex maps that to ROM offset
  `segment × 8 KiB`. Host builds and other ROM variants define
  `WINGS_BANKED` and `WINGS_CODE_SEGMENT` as empty.
- `tools/check_rom_layout.py` runs after every mission build. It fails if
  resident code reaches A000h, banked code leaves A000h–BFFFh, a segment is
  undeclared or outside the ROM, or a code segment overlaps a raw data bank.

## Rules for banked code

1. Interrupt handlers and anything they call stay resident.
2. Do not export constants from a banked module or return pointers to them.
   Resident code would read whatever segment window 3 holds at that moment.
   Copy through a banked function instead (see `Dashboard_CopyPalette`), or
   keep shared tables in RAM or resident modules.
3. Do not call banked functions through function pointers; that bypasses
   the trampoline.
4. Banked code reads raw data through `Scenery_Read` (window 1), as before.
   It never maps data into window 3.
5. Keep each banked call coarse; the trampoline costs roughly 150 T-states.

Adding a module: pick or add a `WINGS_SEGMENT_*` value in `banking.h`, add the
segment macro at the top of the `.c` file, mark its public prototypes and
definitions `WINGS_BANKED`, and add it to `tests/test_rom_layout.py`'s module list.

## Validation

Measured with the release and debug ROMs after the change:

- `python3 tools/verify_p0.py --headless`: 89 snapshots pass (Panasonic FS-A1WX).
- `python3 tools/verify_p0.py --headless --machine C-BIOS_MSX2+_EU`: 89 pass.
- `python3 tools/verify_world_flight.py --project mission-flight --debug-profile --weapons --headless`:
  64 pass. Maximum redraw is 101.00 ms, against 102.36 ms for the same check
  on the unbanked build, so banking adds no measurable cost.
- 131 host tests pass, including the layout checker.

Physical FS-A1WX validation still needs an ASCII8-capable flash cartridge of
at least 256 KiB.
