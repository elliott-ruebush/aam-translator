# ActiveSpace integration

Notes for wiring this library into `nps-activespace-nmsim`'s future AAM adapter.

## Mapping

| NMSim | AAM | This library |
| --- | --- | --- |
| `.sit` (fixed mic) | `POI` block (1 receiver) | `PoiPoint`, `write_inp` |
| `.trj` (N test points) | `ONE TRACK` (N vertices) | `TrackPoint`, `hop_speed_kn` |
| propagation output | `.POI` + run log | `read_poi`, `read_run_log`, `assert_track_alignment` |

General output-reading guidance: [Reading AAM output](reading_aam_output.md).

## In this library

| Shipped | Module / API |
| --- | --- |
| Spectral time history | `read_poi`, `bands` |
| Run log | `read_run_log` |
| Per-receiver metrics CSV | `read_poi_summary_csv` |
| Track ↔ row verification | `poi_align.assert_track_alignment`, `arrival_time_residuals` |
| NMBGF read-back | `read_nmbgf_grid` (`.ELV`/`.IMP` only) |
| Input guardrails | `MAX_TRACK_POINTS`, `hop_speed_kn`, per-point `TrackPoint` fields |

## Out of scope here

Audibility/ambience thresholds, mesh triangulation or contour refinement, merging many
`.inp` runs into one active-space result, `Microphone`/domain glue, and NMSim comparison
logic belong in `ActiveSpaceGenerator` and its AAM adapter, not in `aam_translator`.

## Deferred

| Item | Notes |
| --- | --- |
| AAM `.GRD` reader | Different NMBGF dialect (`MTRC`/`CART`/`GRID`; no `CASE` block). Pair with a `COMPUTEGRD` writer if taken on. |
| `cell_size_m` override on `write_elv_from_dem` | Expose coarser terrain mesh; value choice stays with the consumer. |
| `COMPUTEGRD` `write_inp` variant | ActiveSpace reciprocity uses `COMPUTEPOI`, not grid metrics. |

## External references

- `~/dev/nps-activespace-nmsim/docs/aam_integration_notes.md` — adapter-side scoping.
- `~/dev/nmsim-aam-experiments/activespace-experiments/runs/tier4*` — runs that validated
  the 400-point cap, exit-code-0 failures, and hop-speed workaround.
