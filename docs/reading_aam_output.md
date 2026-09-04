# Reading AAM output

This library parses a few post-run artifacts from AAM 3.x. The focus here is
`COMPUTEPOI` — one spectral time-history zone per receiver, one row per track point.

Format limits (400-point track cap, 1-vertex crash, `READ ERROR` behaviour) are documented in
[`references/notes/aam_inp_format.md`](../references/notes/aam_inp_format.md#batch-limits-computepoi).

## What each reader returns

| File | API | Notes |
| --- | --- | --- |
| `.POI` | `read_poi` | `list[PoiTimeHistory]` — one entry per receiver zone, in file order |
| `{basename}.txt` | `read_run_log` | `AamRunLog` — read errors, analysis track, terrain/impedance extents |
| `{basename}.Single.POI.csv` | `read_poi_summary_csv` | `list[PoiSummary]` — event-integrated metrics per receiver |
| `.ELV` / `.IMP` | `read_nmbgf_grid` | `NmbgfGrid` — north-up 2D array in header units (not AAM `.GRD`) |

`PoiTimeHistory` holds numpy arrays (`time_s`, `broadband_db`, `band_levels_db`).
Band cells at or below AAM's `-370 dB` sentinel become `NaN`.

## Reading a `COMPUTEPOI` run

Within a zone, row `k` corresponds to track point `k` **in track order**. The `.POI`
file does not state that — verify it rather than assuming:

```python
from aam_translator import read_poi, read_run_log, assert_track_alignment

history = read_poi("scenario.POI")[0]
log = read_run_log("scenario.txt")
assert_track_alignment(history=history, track=track, terrain=terrain, run_log=log)

history.time_s          # arrival times, one per track point
history.broadband("dBA")
history.band_levels_db  # (n_points, n_bands)
```

`assert_track_alignment` always checks the row count. With `DIAGNOSTICS` enabled, the
run log's `Interpolated Track for analysis` table lets it compare coordinates and catch
an off-by-one. `arrival_time_residuals` can cross-check arrival times from geometry
alone, but only catches gross mismatches on dense tracks — see its docstring.

## Surprises worth knowing upfront

**AAM can fail while exiting 0.** When it rejects an input deck it writes `READ ERROR`
into the log and no `.POI`. Check `read_run_log(...).ok`, not the process exit code.
`read_poi` raises on a missing or empty file for the same reason.

**Arrival times are not monotonic.** Each row's `Time` is when sound *reaches* the
receiver, not when it was emitted. Scattered source points produce out-of-order
timestamps. Sorting by time scrambles the row-to-source-point mapping.

**A 1-vertex `ONE TRACK` crashes AAM 3.0.0.** Wine exits 152 with an empty `.POI`;
the log never reaches the interpolated-track table. `write_inp` allows `speed_kn=0`
for N=1, but the binary still needs at least two vertices. A ~1 m pad hop works.
This library does not pad — that is a consumer choice. See
[batch limits](../references/notes/aam_inp_format.md#batch-limits-computepoi).

**A below-ground vertex or interpolated hop aborts the entire `ONE TRACK`.** AAM
bilinear-samples `.ELV` and writes `ERROR: Below ground. TERRAIN`, often leaving
an empty `.POI`. This library does not filter tracks. Consumers must prefilter or
split hops before write.

**Fortran `FILENAME` is 140 characters.** AAM 3.0.0 stores `ROTOR_NOISE` / `NCfiles`
paths in that buffer. Long work-dir paths fail; keep paths short.

**POI bands stop at 10 kHz.** AAM `.POI` spectra are 10 Hz–10 kHz
(`AAM_BAND_NUMBERS` / `range(10, 41)`). Consumers that need 12.5 kHz must pad;
this library does not invent band 41.

## Multi-point tracks

AAM rejects `speed_kn=0` on tracks with more than one point (`INTRTIME`). For many
independent source positions written as one `ONE TRACK` block, use a positive speed high
enough that AAM does not subdivide segments:

```python
from aam_translator import hop_speed_kn, MAX_TRACK_POINTS

speed = hop_speed_kn(track, terrain, hop_s=1.0)
write_inp(terrain, "scenario.inp", track=track, pois=pois,
          source_id="OMNI", speed_kn=speed)
```

`MAX_TRACK_POINTS` is **400** (empirical AAM 3.0.0 cap, not the manual's 500).
`hop_speed_kn` is a modeling device — read its docstring before varying speed per point,
since AAM interpolates source spheres on airspeed.
