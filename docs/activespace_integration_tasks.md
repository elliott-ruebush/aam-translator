# Scoped additions for NPS-ActiveSpace integration

Context: `nps-activespace-nmsim`'s `ActiveSpaceGenerator` needs a `PropagationModel`-style
adapter that runs AAM instead of NMSim. Its NMSim usage pattern maps onto AAM's
`COMPUTEPOI` mode: a fixed receiver (NMSim `.sit` ↔ AAM `POI`, 1 point) and N independent
source test points written as one run (NMSim `.trj` "trajectory" ↔ AAM `ONE TRACK`).

**Non-goals** — do not add: audibility/ambience thresholds, point-mesh density or
triangulation/contour refinement, batching many `.inp` runs into one active-space result,
`Microphone`/domain-object glue, or any NMSim comparison logic. That's `ActiveSpaceGenerator`
and its future AAM adapter's job, not this library's.

## Status

Shipped: `.POI` reader + `bands.py`, run-log reader, alignment guard, `.Single.POI.csv`
reader, `read_nmbgf_grid`, point-cap and speed guardrails, per-point track fields.

Deferred until a concrete consumer needs them: AAM `.GRD` reader (§1b), terrain cell-size
override (§2c), `COMPUTEGRD` writer (§2d).

## Corrections to the original plan

Several assumptions in the first draft of this document turned out to be wrong when
checked against the AAM 3.0.0 runs in `~/dev/nmsim-aam-experiments`. Recording them here
so they don't get re-adopted:

| Original claim | What's actually true |
| --- | --- |
| Track cap is 500 points, per the manual | AAM rejects 500 with `exceeds 400 You have entered > 500`. The real cap is **400**; `MAX_TRACK_POINTS = 400` |
| Exceeding a cap causes "a cryptic AAM failure" | AAM exits **0**, writes no `.POI`, and only records `READ ERROR` in the log. Exit status is not a success signal |
| `.GRD` is the same NMBGF family as `.ELV`/`.IMP`, "no new format knowledge needed" | AAM's `.GRD` is a different dialect (`MTRC`/`CART`/`LINS`/`GRID` tags, no `CASE` block). `read_nmbgf_grid` is scoped to the `CASE` family this library writes |
| Run log exposes a `TERRAINCHK` pass/fail to parse | No log line contains that string. The log does carry `Terrain Information` / `Impedance Information` extents, which is what the check compares, so those are parsed instead |
| `read_poi` returns `pd.DataFrame` | This library is numpy-only. `PoiTimeHistory` holds numpy arrays with an opt-in `to_dataframe()`; pandas stays a dev-only dependency |
| Speed is a harmless formatting detail | The default `speed_kn=0.0` makes AAM reject any multi-point track with `ERROR: Excessive trajectory points. INTRTIME`. Multi-point tracks now require a positive speed, and `hop_speed_kn` computes a workable one |

## Why `COMPUTEPOI` works for this, and what it rests on

One `.POI` row is emitted per track point, in track order. That holds because this writer
never emits `TIMESPACING` and always writes zero turn radii, so AAM does not subdivide
segments. The correspondence is positional and unstated in the file, so
`assert_track_alignment` checks it against the run log's `Interpolated Track for analysis`
table, which is the only place AAM says what it actually analyzed.

Two limits worth knowing:

- A row's `Time` is an **arrival** time, not an emission time, so timestamps are
  non-monotonic whenever consecutive source points sit at very different ranges. A
  validated 400-point run has 228 decreasing steps. Never sort by time.
- `arrival_time_residuals` reconstructs expected arrival times from geometry and needs no
  log, but it only catches gross pairing errors: on a dense track, adjacent rows differ by
  far less than the ~2% uncertainty in sound speed, so it cannot detect a one-row shift.
  The log-based coordinate check is the one that can.

The hop speed is a modeling device, not a physical airspeed. It is acoustically inert only
when the source sphere has a single airspeed; otherwise AAM interpolates spheres on speed
and a high hop speed silently changes source levels.

## Remaining work

### 1b. AAM `.GRD` reader — deferred

Needs format work, not just a read path: AAM's `COMPUTEGRD` output uses a different NMBGF
tag layout than the `CASE`-family `.ELV`/`.IMP` files this library writes. `read_nmbgf_grid`
raises rather than guessing. Take this on together with §2d, since a `.GRD` reader without
a `COMPUTEGRD` writer has nothing to read.

### 2c. Terrain cell-size override

`write_elv_from_dem` (and therefore `write_terrain`/`write_aam_inputs`) always derives
`cell_dx_m`/`cell_dy_m` from native DEM posting via `dem_posting_meters_from_src`. An
optional `cell_size_m: float | None = None` would allow coarsening the terrain mesh for
performance. This is just exposing a parameter — deciding *what* value to pick for
ActiveSpace-scale performance work stays in `nps-activespace-nmsim`.

### 2d. `COMPUTEGRD` writer variant

A `write_inp(..., mode="COMPUTEGRD", metrics=["SELA"])` path (no `POI` block, metric
line(s) instead) would round out format coverage. Deprioritized because
`ActiveSpaceGenerator`'s fixed-receiver/many-source pattern maps onto `COMPUTEPOI`.

## References

- `~/dev/nps-activespace-nmsim/docs/aam_integration_notes.md` — ActiveSpace-side scoping.
- `~/dev/nmsim-aam-experiments/compare/io/parsers.py`, `compare/io/bands.py` — the
  comparison-harness prototypes the `.POI` reader was ported from.
- `~/dev/nmsim-aam-experiments/activespace-experiments/runs/tier4*` — the runs that
  established the 400-point cap, the silent-failure mode, and the hop-speed workaround.
