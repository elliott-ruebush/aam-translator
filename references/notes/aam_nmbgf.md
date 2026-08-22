# NMBGF terrain files — quick reference

Scope: **AAM binary terrain grids** referenced by `TERRAIN` in `.inp` — `.ELV`, `.IMP`, and (briefly) output `.GRD`. ASCII keywords and calculating-grid rules: [`aam_inp_format.md`](aam_inp_format.md). Term definitions (`XRYR`, `NINJ`, `METR`/`FEET`, etc.): [`glossary.md`](glossary.md).

---

## What NMBGF is here

**NMBGF** (Noise Model Binary Grid Format) is AAM's tagged binary grid family. With `TERRAIN` set, a run loads **`.ELV`** (elevation) and **`.IMP`** (ground flow resistivity) from paths in the `.inp`. **`COMPUTEGRD`** writes metric rasters as **`.GRD`** (same header pattern, different payload tag).

NMSim also uses NMBGF for **`.elv`**, but headers differ (e.g. **`UTMZ`** on NMSim terrain, not on AAM `.ELV`) — see [glossary — NMBGF](glossary.md#nmbgf-and-terrain-inputs).

---

## File roles

| File | Payload tag | Values | Used when |
|------|-------------|--------|-----------|
| **`.ELV`** | `ZALT` | Ground elevation **MSL ft** (per header units) | `TERRAIN` — drives ground height and **`TERRAINCHK`** extent |
| **`.IMP`** | `FLOW` | Flow resistivity **kPa·s/m²** | `TERRAIN` — ground impedance (replaces flat `SETUP PARA` line-4 `{flow_ρ}`) |
| **`.GRD`** | metric-specific | One map metric (e.g. SELA) | Output of `COMPUTEGRD` only — **different tag dialect**, see below |

**`.GRD` is not simply an AAM-written `.ELV`.** Despite sharing the NMBGF family it uses a
different tag layout (`MTRC` / `CART` / `LINS` / `GRID`, no `CASE` block), so this
package's readers do **not** accept it. Treat `.GRD` support as unimplemented format work,
not as a missing read path.

**`.ELV` and `.IMP` share the same grid geometry** (`NINJ`, `DIDJ`, `XRYR`, units). Cell **(1, 1)** is the lower-left (SW) corner of the raster.

---

## Header fields (CASE block → MTRC → data)

Read order matches vendor [`Plt2Elv.f`](../source/Plt2Elv.f). Canonical read path in this package: [`nmbgf_io.read_nmbgf_header`](../../src/aam_translator/nmbgf_io.py).

| Tag | Meaning | Units / notes |
|-----|---------|----------------|
| **`TITL`** / **`Vers`** | Format version | Major/minor integers |
| **`CASE`** | Scenario title string | Filename or label (record length varies — see [Still open](#still-open)) |
| **`METR`** or **`FEET`** | Horizontal grid units | Spacing in tag; **`FEET`** is vendor default for terrain |
| **`DIDJ`** | Cell spacing Δi, Δj | Meters if `METR`, feet if `FEET` |
| **`NINJ`** | Grid size Ni × Nj | Number of cells along each axis |
| **`IRJR`** | Reference cell index | Usually **(1, 1)** at lower-left |
| **`MTRC`** | Metric / projection block wrapper | Followed by **`XRYR`** |
| **`XRYR`** | User (x, y) of cell **(1, 1)** | Same **model-foot frame** as `.inp` horizontal coords (after unit conversion) |
| **`ZALT`** / **`FLOW`** | Raster payload | ELV: MSL elevation; IMP: flow resistivity; column-major **i** then **j** |

---

## Extent (terrain domain)

Terrain rectangle in **model feet** (same basis as post-run **`scenario.txt`** UR corners):

```
LL = (XRYR_x, XRYR_y) × scale
UR = LL + (Ni × Δi, Nj × Δj) × scale
scale = 3.28084 if header METR else 1.0
```

Example: `XRYR=(0,0)`, `Ni=272`, `Nj=100`, `Δ=98.4252 ft` → domain `(0,0)–(26772, 9843) ft`.

---

## Same frame as `.inp`

All horizontal positions in the scenario — **`SETUP PARA`** corners, **`ONE TRACK`** x/y, **`POI`** x/y — live in one **user model-foot** plane (not UTM/EPSG). NMBGF headers declare where the **terrain raster** sits in that plane via **`XRYR`** + spacing.

- **`TERRAINCHK`** (when `TERRAIN` is on): calculating grid must fit inside the **`.ELV`** extent; track points must lie inside the calculating grid. Details and Figure 3-2 buffer guidance: [`aam_inp_format.md` — Two grids](aam_inp_format.md#two-grids-one-frame).
- **ELV drives the check** in practice; **ELV and IMP should share `XRYR` and units** even though the runtime check is ELV-based.

---

<a id="this-repos-convention"></a>

## This package's convention

Terrain is built with **`write_terrain()`** / **`write_aam_inputs()`**, not vendor `PLT2ELV`.

**DEM → AEQD resample pipeline** (three coordinate spaces, grid types, bilinear sampling, track/POI projection): [`docs/elv_pipeline.md`](../../docs/elv_pipeline.md).

| Choice | Value | Why |
|--------|-------|-----|
| **`XRYR`** | **`(0, 0)`** on ELV and IMP | Coresident with calculating-grid origin at terrain SW corner (`SETUP PARA` LL often `(0,0)`) |
| Units tag | **`FEET`** | Aligns with `Plt2Elv.f` and `.inp` BSU feet |
| **`DIDJ` / `ZALT`** | Feet | Spacing and MSL elevations converted on write (`FT_PER_M = 3.28084`) |
| **`FLOW`** | **200.0** kPa·s/m² | Constant soft-ground impedance (not multiplied by feet) |

Non-zero **`XRYR`** (PLT2ELV-style absolute user coords) is valid in principle but **breaks `TERRAINCHK`** unless track, POI, and **`SETUP PARA`** are rebased into the same frame — not the current convention.

Historical note: an earlier **`AAM_inp`** path copied UTM-clipped pixels into ELV while georef used AEQD — that misaligned elevations at high latitude. Variant-test write-ups live in `nmsim-aam-experiments/runs/aam_inp_variant_tests/`.

### Reading grids back

`read_nmbgf_header()` returns the header plus the payload as a flat tuple in **on-disk
order** (`iter_grid_cells`: column-major, `j` descending). `read_nmbgf_grid()` wraps that
and reshapes to 2D:

```python
values = flat.reshape((header.nj, header.ni), order="F")[::-1, :]
```

So `values[j, i]` is the cell `iter_grid_cells(ni, nj)` yields, `values.shape` is
`(nj, ni)`, and **row 0 is the north edge** — the same north-up convention rasterio uses,
which is what makes the DEM round-trip in `tests/test_write_elv.py` comparable cell for
cell. Values come back in the header's declared units (`FEET` here), *not* converted to
metres, and as `float32` because that is how the payload is stored.

---

## Vendor reference

Authoritative write order for terrain NMBGF: [`source/Plt2Elv.f`](../source/Plt2Elv.f) (`FEET`, `DIDJ`, `NINJ`, `XRYR`, `ZALT`/`FLOW`).

---

## Still open

- **`CASE`** record: 12-char filename (`Plt2Elv`) vs 20-char title (`aam_translator`) — not re-tested against AAM 3.0 here.
- **Lon/lat ↔ model feet** — `aam_translator.context.lonlat_to_model_ft`; not encoded in NMBGF headers.
- **Terrain grid resolution vs run time** — defer to NPS-ActiveSpace AAM perf work.
