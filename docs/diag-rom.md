# Diagnostic ROM

`python3 tools/build_diag.py` builds `out/diag/WOFDIAG.ROM` (512 KiB, the
game's size) and `out/diag/WOFD256.ROM` (256 KiB) from
`tools/diag/wofdiag.asm`. Both are ASCII8 ROMs laid out like the game: code
in bank 0 at 4000h, and every 8 KiB bank ends with the tag `'W', n, ~n, '8'`,
which the ROM reads to see which bank sits in each window. It prints in
text mode through the BIOS, and names each step before doing it, so the last
line on screen shows where a freeze happened.

Written for the first real-hardware report (2026-11-21): black screen when
SofaRun ran the game from a memory-mapper RAM cartridge ("Device: Memory
mapper"), where it has to emulate ASCII8's 8 KiB banks.

## Reading the screen

| Line | Meaning |
|---|---|
| `WOF DIAG 1 BANKS 064 MSXVER 02 VDP 02` | banks in this ROM; MSX version (02 = MSX2+); VDP id (00 V9938, 02 V9958) |
| `ROM SLOT / P3 SLOT / A8` | slot of this ROM (page 1) and of page-3 RAM, as the game's startup computes them; primary slot register |
| `HIMEM BOTTOM SP` | the game's startup puts its stack at `HIMEM`; `SP` is the stack at INIT |
| `MAPPER FC-FF` | memory-mapper segment registers |
| `TIMI / KEYI` | first bytes of the interrupt hooks (C9 = unused, F7 = a call into another slot) |
| `BOOT BANKS` | banks seen in windows 4000h/6000h/8000h/A000h before any switch (`--`: no tag, not ROM data) |
| `BASE 1 2 3` | windows 1..3 set to banks 1, 2, 3 |
| `A W1..W3` | a switch with `LD (6800h/7000h/7800h),A`, the form loaders patch |
| `B W1..W3` | the same through `LD (HL),A`, which the game also uses (`Scenery_Read`, `Terrain_InitPage`) |
| `C 8000 / A000` | a write into the window itself: `ok` (no change) on ASCII8, a switch on MegaRAM |
| `SCAN` | each bank 0..N-1 put in each window: number found, `@xx` the first bank that failed |
| `SPEED 32 SWITCHES` | frames 32 switches took: 0 on a real mapper; a loader copying 8 KiB per switch takes 1-2+ |
| `FM SLOT` | slot with `OPLL` at 401Ch (MSX-MUSIC) |
| `IM2 AT C000` | the game's interrupt setup (vector table C000h, routine C1C1h): interrupts in ~1 s (about 50-67) |
| `RAM C000-xxxx` | that RAM (the game's variables) filled with HALT, BIOS interrupts left on for a second: a freeze here, or `CHG` above 0, means something lives there |
| `IM2 / RAM A W3` | a switch after those two steps: fails if the loader's helper lived in that RAM |

Each test line shows the four windows' banks after the write, then `ok` or
`BAD` against what an ASCII8 mapper does.
