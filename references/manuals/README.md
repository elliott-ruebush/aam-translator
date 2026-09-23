# Vendor manuals — AAM

The **aam-translator** repo is public, but the full AAM v3 manual **PDF and text extract are not in git** (USDOT/Volpe redistribution). Add them locally under this directory if you need `rg` or offline PDF tables.

| File | Source |
|------|--------|
| `aam_v3_manual.txt` | USDOT/Volpe *AAM v3 Technical Reference and User's Guide* (27 Dec 2020) — text extract for `rg` |
| `USDOT 2020 AAM_v3_TechnicalReferenceAndUsersGuide_27Dec2020.pdf` | Same (PDF) |

Typical source: NPS data drive or your own copy from the vendor distribution. Paths are listed in [`.gitignore`](../../.gitignore) so they are never committed by mistake.

Use `rg` on `aam_v3_manual.txt` once present; PDFs are for figures and tables not captured in the extract.

Manual **Figure 3-2** (two nested grids) is committed as [`../notes/aam_figure_3_2_grids.png`](../notes/aam_figure_3_2_grids.png) so [`aam_inp_format.md`](../notes/aam_inp_format.md) renders on GitHub without the full manual.

NMSim manuals: [`nmsim-aam-experiments` `notes/manuals/`](https://github.com/elliott-ruebush/nmsim-aam-experiments/tree/main/notes/manuals).
