# aam-translator

Prepare geospatial inputs for the U.S. DOT **Advanced Acoustic Model** (AAM), and read
its outputs back.

Inputs written:

- `.ELV` — NMBGF elevation grid
- `.IMP` — NMBGF ground-impedance grid
- `.INP` — single-event AAM scenario input (Computation mode, calculation grid, terrain inputs, noise source tracks)

Outputs read:

- `.POI` — spectral time history per receiver (Tecplot ASCII)
- `.Single.POI.csv` — event-integrated metrics per receiver
- `{basename}.txt` — run log: read errors, the track AAM actually analyzed, grid extents
- `.ELV` / `.IMP` — NMBGF grids, as north-up 2D arrays

```python
from aam_translator import write_terrain, write_inp, write_aam_inputs
from aam_translator import read_poi, read_run_log, read_poi_summary_csv
```

## Reading a `COMPUTEPOI` run

`COMPUTEPOI` writes one `.POI` zone per receiver, and within a zone one row per track
point **in track order**. Nothing in the file states that correspondence, so verify it
rather than assuming it:

```python
from aam_translator import read_poi, read_run_log, assert_track_alignment

history = read_poi("scenario.POI")[0]
log = read_run_log("scenario.txt")
assert_track_alignment(history=history, track=track, terrain=terrain, run_log=log)

history.time_s          # arrival times, one per track point
history.broadband("dBA")
history.band_levels_db  # (n_points, n_bands), NaN where AAM wrote its -370 dB sentinel
```

Two things routinely surprise people here:

- **AAM can fail while exiting 0.** When it rejects an input deck it writes a `READ ERROR`
  into the log and no `.POI` at all, so check `read_run_log(...).ok` rather than the exit
  status. `read_poi` raises `ValueError` on a missing or empty file for the same reason.
- **Arrival times are not monotonic.** A row's `Time` is when sound *arrives* at the
  receiver, so scattered source points produce out-of-order timestamps. Sorting by time
  would silently scramble the row-to-source-point mapping.

Writing N independent source points as one track needs a speed high enough that AAM does
not subdivide segments, since it rejects speed 0 on a multi-point track. `hop_speed_kn`
computes one, at the cost noted in its docstring:

```python
from aam_translator import hop_speed_kn

speed = hop_speed_kn(track, terrain, hop_s=1.0)
write_inp(terrain, "scenario.inp", track=track, pois=pois,
          source_id="OMNI", speed_kn=speed)
```

`PoiTimeHistory.to_dataframe()` is available for consumers that want pandas; pandas is
not a runtime dependency of this package.

Requires Python >=3.12 (tested on 3.12). Install in another project with:

```
pip install git+https://github.com/elliott-ruebush/aam-translator.git
```

Or from a local clone:

```
pip install -e /path/to/aam_translator
```

## Platform notes

- **Python >=3.12** — required; CI tests on 3.12 only.
- **GDAL** — bundled with rasterio wheels on macOS, Linux, and Windows; no separate GDAL install is needed for typical use.

## Docs

- [DEM → AAM ELV pipeline](docs/elv_pipeline.md) — AEQD bilinear resample pipeline (implementation).
- [References](references/README.md) — AAM `.inp` / NMBGF format specs, glossary, vendor manual extract, `Plt2Elv.f`.
