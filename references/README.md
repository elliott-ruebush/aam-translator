# References — AAM formats and vendor docs

Stable specs for AAM `.inp`, NMBGF terrain grids, and related terminology. **Not** runtime package data — for developers working on `aam_translator` or cross-checking generated files.

This tree is part of the **public** [aam-translator](https://github.com/elliott-ruebush/aam-translator) repo. USDOT/Volpe **vendor** manuals and Fortran extracts are **not** committed (redistribution); only the markdown specs and one manual figure PNG below ship in git.

| Path | In git? | What |
|------|---------|------|
| [`notes/aam_inp_format.md`](notes/aam_inp_format.md) | yes | AAM `.inp` keywords, two-grid rules, examples |
| [`notes/aam_nmbgf.md`](notes/aam_nmbgf.md) | yes | NMBGF `.ELV`/`.IMP`/`.GRD` headers and extent |
| [`notes/glossary.md`](notes/glossary.md) | yes | Shared terms (CRS, grids, NMBGF tags, metrics) |
| [`notes/aam_figure_3_2_grids.png`](notes/aam_figure_3_2_grids.png) | yes | Manual Figure 3-2 (embedded in [`aam_inp_format.md`](notes/aam_inp_format.md)) |
| [`manuals/`](manuals/) | README only | Full AAM v3 PDF + `.txt` — [place locally](manuals/README.md) |
| [`source/`](source/) | README only | e.g. `Plt2Elv.f` — [place locally](source/README.md) |

**Implementation pipeline** (DEM → AEQD → `.ELV`): [`docs/elv_pipeline.md`](../docs/elv_pipeline.md).

**NMSim comparison, harness fixtures, and validation reports** live in [`nmsim-aam-experiments`](https://github.com/elliott-ruebush/nmsim-aam-experiments) (`compare/`, `reports/`, [`notes/nmsim_vs_aam_comparison.md`](https://github.com/elliott-ruebush/nmsim-aam-experiments/blob/main/notes/nmsim_vs_aam_comparison.md)).
