# Glossary — NMSim, AAM, and formats

Shared terms for file formats, grids, coordinates, and acoustic metrics. AAM `.inp` keywords: [`aam_inp_format.md`](aam_inp_format.md). Cross-model NMSim↔AAM overview: `nmsim-aam-experiments/notes/nmsim_vs_aam_comparison.md`.

## Models

| Term | Meaning |
|------|---------|
| **NMSim** | Noise Model Simulation — NPS (National Park Service) batch tool (`Nord2000batch.exe`). |
| **AAM** | Advanced Acoustic Model (USDOT Volpe Center). Vendor binary: `AAM_3.0.0.exe`. |
| **Nord2000** | Outdoor propagation method NMSim uses when a `.wea` weather file is selected (2013 update). |
| **AAM_inp** | *(historical)* Earlier Python prep tool in **AAM-Python-Tools**. Superseded by **`aam_translator`**. |
| **`aam_translator`** | Installable Python package: clips/resamples a parent GeoTIFF onto an **AEQD** lattice, writes `.ELV`/`.IMP`, and emits `.inp` blocks (`write_terrain`, `write_inp`, `write_aam_inputs`). Not the AAM executable. |

<a id="coordinates-and-projections"></a>

## Coordinates and projections

| Term | Meaning |
|------|---------|
| **CRS** | Coordinate reference system. |
| **WGS84** | Geographic CRS (lon/lat on the WGS 84 ellipsoid). Source CRS for AOI polygons and parent DEMs in `aam_translator`. |
| **EPSG** | Registry of CRS identifiers (e.g. EPSG:4326 = WGS84 geographic; EPSG:326xx = UTM north zones). |
| **UTM** | Universal Transverse Mercator (meters easting/northing). NMSim native frame in comparison harnesses. |
| **AEQD** | Azimuthal equidistant projection (meters). `aam_translator` builds a local tangent plane with origin at the AOI centroid (EPSG:4326 → custom AEQD), resamples the parent DEM onto that lattice, then writes `.ELV`/`.IMP`. Distances from the origin are true to scale. |
| **model feet** | AAM user-coordinate horizontal distances in **feet** (manual §3.5): `SETUP PARA`, `ONE TRACK`, and `POI` x/y. Not an EPSG CRS — you pick the origin and corners. |
| **grid-local feet** | Model feet when the calculating-grid LL and terrain **`XRYR`** share the same origin (often `(0,0)` at the terrain SW corner). See [`aam_inp_format.md` — Two grids](aam_inp_format.md#two-grids-one-frame). |
| **MSL / AGL** | Height above mean sea level / above ground level. |
| **DEM** | Digital elevation model (GeoTIFF or similar). `aam_translator` reads the parent in its native CRS and warps to AEQD for `.ELV`. |

<a id="nmbgf-and-terrain-inputs"></a>

## NMBGF and terrain inputs

| Term | Meaning |
|------|---------|
| **NMBGF** | Noise Model Binary Grid Format. Family for AAM `.ELV`, `.IMP`, `.GRD` (and NMSim `.elv`). |
| **`METR` / `FEET`** | NMBGF unit tag: horizontal distances and (when converted) elevation/impedance values in meters or feet. |
| **`NINJ`** | Grid dimensions Ni × Nj (number of cells along each axis). |
| **`DIDJ`** | Cell spacing Δi, Δj along the grid axes (meters if `METR`, feet if `FEET`). |
| **`XRYR`** | **Terrain-grid** NMBGF header field (`.ELV`/`.IMP`): user model feet of cell **(1, 1)** — SW corner of the terrain raster. **Not** a `SETUP PARA` field. Calculating-grid corners and tracks must still lie inside the ELV extent derived from `XRYR` + `NINJ`×`DIDJ` (`TERRAINCHK`). |
| **`IRJR`** | Grid index of the reference point (typically (1, 1) at the lower-left). |
| **UTMZ** | NMBGF header tag: UTM zone number. Present on NMSim `.elv`; omitted on AAM `.ELV` (AAM uses model feet, not UTM). |
| **`.ELV` / `.IMP`** | AAM terrain elevation and ground-impedance grids (NMBGF). NMSim uses a related `.elv` for `grid` mode. |
| **GridFloat** | ESRI ASCII GridFloat (`.flt` + `.hdr`). Used for NMSim **`site`** runs (terrain height at listed receivers). For NMSim **`grid`** runs (TIG output), use NMBGF `.elv` instead. |

## Grids (three roles)

| Term | Meaning |
|------|---------|
| **calculating grid** | AAM **noise / calculating grid** (manual Figure 3-2): `SETUP PARA` LL/UR corners and Δx/Δy (model **ft**). Track, `POI` block, and PLT/GRD output coordinates live here. |
| **terrain grid** | `.ELV` / `.IMP` sampling grid (§3.4): NMBGF headers `XRYR`, `NINJ`, `DIDJ`. Finer than the calculating grid. Must fully cover calculating grid + tracks (`TERRAINCHK`). |
| **computational / TIG grid** | NMSim receiver lattice for **`grid`** batch mode: user N×M over the study area (`.tig` output). Independent of DEM cell size. |

## AAM prep and setup keywords

| Term | Meaning |
|------|---------|
| **`.inp`** | AAM scenario input file (keywords + data). Format: [`aam_inp_format.md`](aam_inp_format.md). |
| **AOI** | Area of interest polygon passed to `write_terrain()`. Centroid → AEQD origin; envelope → ELV domain. |
| **`SETUP PARA`** | Required AAM block: calculating-grid spacing, corners, receiver AGL, and [line-4 propagation parameters](#aam-propagation-parameters-setup-para-line-4) (Δβ, cutoff, flow resistivity, decoherence). |
| **`TERRAINCHK`** | AAM startup check: the calculating grid (`SETUP PARA` corners) must fit inside the `.ELV` terrain extent. |

<a id="aam-propagation-parameters-setup-para-line-4"></a>

## AAM propagation parameters — SETUP PARA line 4

These fields sit on **`SETUP PARA` line 4** in every `.inp`. Syntax: [`aam_inp_format.md`](aam_inp_format.md). AAM uses **proximity checks** before running full path/propagation work for a source–receiver pair: if the aircraft is too far from the receiver (or too far past closest approach), the contribution would be negligible after geometric spreading, so AAM **skips** that pair instead of ray-tracing it. `{cutoff_ft}` and **Δβ** control that pruning; `{flow_ρ}` and `{decoherence}` affect ground reflection physics when propagation *does* run. Use keyword **`CALCALL`** to disable proximity checks (slower, rarely needed).

| Term | Meaning |
|------|---------|
| **Δβ (spherical loss factor)** | Decibels (manual default **40**). With slant range at closest approach \(R_{\min}\), AAM analyzes track points out to \(R_{\max} = R_{\min} \times 10^{\Delta\beta/20}\). Larger Δβ → wider propagation window; smaller → more aggressive skip. Not an atmospheric constant — a **compute/prune** knob tied to spherical spreading (manual eq. 22, §3.5.1.3). |
| **cutoff distance** | Maximum source–receiver distance of interest (**ft**; manual default **30 000**, comparison harnesses often **50 000–60 000**). If slant range to the point of closest approach (PCA) on a track exceeds `{cutoff_ft}`, AAM **bypasses the entire track** for that receiver. |
| **flow resistivity** | Flat-earth ground impedance parameter (**kPa·s/m²**; typical **200** for soft ground). Used when **`TERRAIN` is off**; **ignored when `TERRAIN` is on** (impedance from `.IMP`). |
| **turbulent decoherence** | Turbulence-induced incoherence (**rad·s/√ft**; manual recommends **0.0004**, **0** disables). Modifies propagation when paths *are* computed. |

## Run modes and output files

| Term | Meaning |
|------|---------|
| **`COMPUTEPOI`** | AAM run mode (keyword at top of `.inp`): time × 1/3-oct at POI-block receivers → `.POI`. One run mode per file; do not combine with PLT/GRD. |
| **`COMPUTEPLT`** | AAM run mode: integrated metrics on the calculating grid → `.PLT` (SEL, Lmax-A, EPNL, etc.; no bands or time). |
| **`COMPUTEGRD`** | AAM run mode: one metric per run on the calculating grid → `.GRD` (NMBGF; default metric SELA). |
| **GRD** / `.GRD` | Output of `COMPUTEGRD`: NMBGF raster of **one** metric (default **SELA**). |
| **PLT** / `.PLT` | Output of `COMPUTEPLT`: ASCII raster of **event metrics** (no bands, no time). |
| **`ONE TRACK` block** | `.inp` keyword: source path vertices (model ft; z MSL with `TERRAIN`). Manual **500 max** segments; **AAM 3.0.0: 400 max** empirically. ActiveSpace oracle: N sources + 1 POI mic. |
| **`POI` block** | `.inp` keyword: receiver names and x/y/z (model ft, z AGL). Manual **500 max** receivers. Grid/TIG analogue uses many POIs; reciprocity uses **1** POI. |
| **`.POI` file** | Output of `COMPUTEPOI`: time × 1/3-oct spectra at each POI (Tecplot ASCII ZONEs). |
| **TIS** / `.tis` | Time at site. NMSim batch **`site`** mode: time × 1/3-oct at receivers listed in `.sit`. |
| **TIG** / `.tig` | Time in grid. NMSim batch **`grid`** mode: same payload as TIS, one block per lattice cell (`iiiijjjj`). |
| **`.sit` / `.trj` / `.flt`** | NMSim receiver list, trajectory, and terrain (GridFloat). |
| **`.wea`** | NMSim weather/atmosphere file; selecting it enables Nord2000 propagation. |

<a id="metrics-and-spectra"></a>

## Metrics and spectra

| Term | Meaning |
|------|---------|
| **1/3-oct** | One-third-octave band. Levels vs frequency, one number per ANSI band *n*. |
| **ANSI *n*** | Band number; center *f* = 10^(*n*/10) Hz. *n* = 10 → 10 Hz; 30 → 1 kHz; 40 → 10 kHz; 41 → 12.5 kHz. |
| **dB / dBA / dBC** | Sound pressure level; **A** or **C** frequency weighting. AAM `.POI` output is already dB. |
| **centibel (cB)** | NMSim TIS/TIG storage: 10 cB = 1 dB. Parser multiplies by 0.1. |
| **Lmax** / **Lmax-A** | Maximum level during the event (A-weighted if -A). |
| **SEL** / **SEL-A** / **SELA** | Sound exposure level: time-integrated energy of the event (A-weighted if -A). AAM GRD keyword `SELA`. |
| **SEL-unwt / SEL-C** | Unweighted / C-weighted SEL. |
| **EPNL** | Effective perceived noise level (tone-corrected, duration-corrected PNL; aircraft certification-style). |
| **DNL** | Day–night average level (penalizes night). AAM **GRD** metric, not a PLT column. |
| **PNL / PNLT** | Perceived noise level / tone-corrected PNL. Present in AAM `.POI` columns; not used in NMSim–AAM metric pairing. |
| **sentinel** | "No data" fill. NMSim: **−999** cB. AAM `.POI` empty bands often **−370** dB. |
