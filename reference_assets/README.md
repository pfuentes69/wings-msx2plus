# Recovered Wings of Fury reference assets

Derived from the user-provided Amiga ADF. For private inspection and port development; original copyrights remain with their respective owners.

- `original_files/`: 73 recovered files from AmigaDOS, including original `.shp`, `.map`, executable and sound data.
- `unpacked_shapes/`: 12 `.shp.unpacked` blobs and 1,049 individually extracted raw PPkc records in subdirectories. **Raw records are not decoded sprites.**
- `previews/png/`: 10 converted IFF/ILBM PNG images.
- `previews/wings_iff_contact_sheet.png`: source-derived previews.
- `MANIFEST.json`: per-file SHA-256 plus source ADF SHA-256.

The original exploratory scripts are preserved unchanged in `tools/legacy/`.
Portable CLIs with bounds validation now live in `tools/`. The supplied
reference assets and manifest remain unchanged. Decoded aircraft are exported
separately to `assets_src/hellcat/`; see `docs/format-shp.md` for evidence and
the remaining format assumptions.

The ADF itself is not duplicated here (the user already has it). The extracted game executable is included in `original_files/`.
