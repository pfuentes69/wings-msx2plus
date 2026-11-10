# Converted MSX artwork

`hellcat/` contains raw SCREEN 5 data for `hc01`, `hc05` and `hc09`.
Each `.sc5` is a 48×32 canvas, 24 bytes per row (left pixel in the high nibble),
768 bytes total, **without a BSAVE header**. `palette.bin` contains all sixteen
V9958 palette entries as red/blue, green byte pairs. The last four entries are
reserved for the prototype UI. `manifest.json` records source PNG hashes,
index mapping, padding, palette quantization and output hashes.

`hc01-left.sc5`, `hc05-left.sc5`, and `hc09-left.sc5` are exact horizontal
pixel reflections of those canvases, also exported as generated C arrays.
They provide temporary left-facing flight artwork; authentic turning frames
and pivots still need to be mapped from the decoded source animation.

Regenerate from the repository root with:

```sh
python tools/convert_hellcat.py
python tools/convert_hellcat.py --check
```

The same conversion generates `src/generated/hellcat_frames.c` and `.h` so
normal ROM builds need only Node, SDCC and MSXhex. Regeneration needs Pillow
from `requirements.txt`. Index zero is flattened to the sky; a general mask
or terrain compositor is not implemented. Original artwork remains subject
to its original copyrights; conversion grants no redistribution rights.
