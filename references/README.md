# References — AAM formats and vendor docs

Stable specs for AAM `.inp`, NMBGF terrain grids, and related terminology. **Not** runtime package data — for developers working on `aam_translator` or cross-checking generated files.

| Path | What |
|------|------|
| [`notes/aam_inp_format.md`](notes/aam_inp_format.md) | AAM `.inp` keywords, two-grid rules, examples |
| [`notes/aam_nmbgf.md`](notes/aam_nmbgf.md) | NMBGF `.ELV`/`.IMP`/`.GRD` headers and extent |
| [`notes/glossary.md`](notes/glossary.md) | Shared terms (CRS, grids, NMBGF tags, metrics) |
| [`manuals/`](manuals/) | Vendor manual PDF + text extract (gitignored — local only) |
| [`source/`](source/) | Vendor Fortran extracts (gitignored — local only, e.g. `Plt2Elv.f`) |

Gitignored local copies in `notes/`: `aam_figure_3_2_grids.png` (manual Figure 3-2). See [`manuals/README.md`](manuals/README.md).

**Implementation pipeline** (DEM → AEQD → `.ELV`): [`docs/elv_pipeline.md`](../docs/elv_pipeline.md).

**NMSim comparison, harness fixtures, and validation reports** live in the sibling [`nmsim-aam-experiments`](https://github.com/elliott-ruebush/nmsim-aam-experiments) repo (`compare/`, `reports/`, `notes/nmsim_vs_aam_comparison.md`).
