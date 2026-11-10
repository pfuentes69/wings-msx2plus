# Audio recovered from the supplied Amiga disk files

- `effects/`: eight raw-effect WAV previews. Their 8,363 Hz playback rate is
  assumed for audition; the game changes pitch through hardware periods.
- `instruments/`: six exact embedded 8SVX files, with WAVs at their declared
  header rates. Loop waveform data is played once in these WAVs.
- `music/`: the original `wofsongs` bytes renamed `kh.Wings_of_Fury` for replay,
  beside their matching `songplay`; neither file is modified.
- `music/previews/`: four 10-second, stereo UADE renders, one per unique song
  definition. Slot 3 references the same definition as slot 1. These are
  previews, not full-track extractions or MSX music data.
- `manifest.json`: provenance, counts, offsets, sample rates and assumptions.

See `docs/audio-extraction.md` for format evidence, reproduction commands,
remaining uncertainties and the implications for PSG/MSX-MUSIC adaptation.
Original copyrights remain with their owners; extraction does not grant
redistribution rights. These files retain the same source-derived research
status as the original game resources.
