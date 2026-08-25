# Plan: `load_terrain`

Working plan for a PR — not shipped docs. Fold the lasting bits into `docs/elv_pipeline.md` (clip as georeference sidecar) and delete this file when the API lands.

Inverse of `write_terrain`: rebuild `TerrainResult` from files this library already wrote, so consumers can cache ELV/IMP and call `write_inp` / `lonlat_to_model_ft` without resampling the parent DEM.

ActiveSpace already does this ad hoc (`nps_active_space.active_space.aam_terrain._terrain_from_disk`). The origin math belongs here so write and reload cannot drift. After load, `TerrainResult` is self-contained — `lonlat_to_model_ft` / `write_inp` do not reopen the clip.

**This PR:** `GridSpec.from_north_up_transform` + `load_terrain`, with a write→load round-trip test.

**Not this PR:** elevation sampling, below-ground filtering, or teaching `setup_para_block` to read `TerrainResult.model_cell_ft` / `cutoff_ft` / `flow_resistivity`.

## Why the clip GeoTIFF is required

ELV is AAM model space: `XRYR=(0,0)`, `DIDJ`/`ZALT` in header units (usually feet), no CRS. `lonlat_to_model_ft` needs `aeqd_crs` and `GridSpec` origins in AEQD meters. Those live only on the clip sidecar that `write_elv_from_dem` (and therefore `write_terrain`) always writes via `clip_path_for_elv` (`{stem}_clip.tif`).

AAM does not read the clip. This library does, as the georeference twin of ZALT (meters MSL, same lattice). Missing clip → hard `FileNotFoundError`; do not rebuild AEQD from a new AOI (that lattice would not match the written ELV).

When this ships, update `docs/elv_pipeline.md`: clip is still unused by AAM, but it is a required artifact of `write_elv_from_dem` / `write_terrain` for reload. Also mention `load_terrain` in the README import list.

## What can be recovered vs caller kwargs

| `TerrainResult` field | From disk? | Source |
|---|---|---|
| `spec` (counts, dx/dy m, SW origin) | Yes | Clip affine + width/height |
| `aeqd_crs` | Yes | Clip CRS (must be AEQD; see below) |
| `elv_header_feet` | Yes | `read_nmbgf_header(elv_path).units` |
| `elv_path` / `clip_tif_path` | Yes | Arguments / `clip_path_for_elv` |
| `imp_path` | Only if passed | No sibling auto-discovery (`elv_basename` / `imp_basename` are independent) |
| `flow_resistivity` | Optional | Kwarg, else constant IMP `FLOW`, else default |
| `grid_agl_ft` | **No** | SETUP PARA AGL; ActiveSpace sets this from receiver AGL |
| `model_cell_ft` | **No** | SETUP PARA calculating-grid cell |
| `cutoff_ft` | **No** | SETUP PARA |

Do not take cell size from ELV `di`/`dj` blindly — those are header units (feet when `to_feet=True`) stored as **float32**. Clip transform is meters, matching `GridSpec`.

`write_elv_from_dem` alone is a supported load: ELV + clip, `imp_path=None`.

## Proposed API

Public, next to `write_terrain` (re-export from `__init__.py`). One function; skip `TerrainResult.from_disk` unless a consumer actually wants the alias.

```python
def load_terrain(
    elv_path: str | Path,
    *,
    imp_path: str | Path | None = None,
    clip_tif_path: str | Path | None = None,  # default: clip_path_for_elv(elv_path)
    grid_agl_ft: float = DEFAULT_GRID_AGL_FT,
    model_cell_ft: float = DEFAULT_MODEL_CELL_FT,
    cutoff_ft: float = DEFAULT_CUTOFF_FT,
    flow_resistivity: float | None = None,
) -> TerrainResult:
    """Rebuild TerrainResult from an on-disk ELV + clip GeoTIFF (+ optional IMP)."""
```

Path fields stay `str`, matching `write_terrain`. Missing ELV or clip → `FileNotFoundError` naming the path. Explicit `imp_path` that does not exist → `FileNotFoundError` too.

### `flow_resistivity`

1. Caller kwarg wins (ActiveSpace always passes `params.flow_resistivity`; do not also read the IMP payload).
2. Else if `imp_path` is set, read FLOW with `read_nmbgf_grid` (numpy, not `header.values`). Constant grid → that value. Non-constant → `DEFAULT_FLOW_RESISTIVITY` (do not `ValueError`: georeference reload still works, and `write_inp` ignores this field today).
3. Else `DEFAULT_FLOW_RESISTIVITY`.

Do not infer IMP from the ELV stem. Callers that want FLOW-from-disk pass `imp_path=written.imp_path`.

### `GridSpec.from_north_up_transform`

Inverse of `from_origin(west, north, dx, dy)` in `build_aeqd_grid`. Implement as a `GridSpec` classmethod in `grid_spec.py` (keep that module rasterio-light: duck-type `.a`–`.f`, or `TYPE_CHECKING` + `Affine`). Put a one-line comment at the `from_origin` call pointing at this method so the pair cannot drift.

```python
@classmethod
def from_north_up_transform(
    cls,
    transform,  # rasterio Affine: a, b, c, d, e, f
    width: int,
    height: int,
) -> GridSpec:
    # origin_x = transform.c                         # west
    # origin_y = transform.f + height * transform.e  # SW; e < 0 for north-up
    # cell_dx_m = transform.a                        # after rejecting a <= 0
    # cell_dy_m = -transform.e                       # after rejecting e >= 0
```

Reject with `ValueError` (this library only writes north-up, pixel-is-area clips):

- rotated / skewed: `transform.b`, `transform.d` not ~0 (atol ~1e-9 m)
- flipped: `transform.a <= 0` (west-up) or `transform.e >= 0` (south-up)
- non-positive `width` / `height`

Use the signed components after those checks, not `abs()`, so a sign bug cannot silently produce a NE origin. ActiveSpace currently uses `abs(transform.e)` and `transform.f + height * transform.e` (signed `e`) — same numeric result for a valid north-up affine.

### Cross-checks in `load_terrain`

Clip CRS is not optional:

- missing CRS → `ValueError`
- not azimuthal equidistant (e.g. `crs.coordinate_operation.method_name` / PROJ `aeqd`) → `ValueError`

A same-size UTM GeoTIFF can share posting with the ELV; DIDJ vs `cell_dx_m` will not catch that. Origins would be UTM eastings, and `lonlat_to_model_ft` would be garbage. Require AEQD.

Also:

- clip `width`/`height` vs ELV `ni`/`nj` — must match
- cell size: if `elv_header_feet`, `|di| / FT_PER_M ≈ cell_dx_m` and same for `dj`/`cell_dy_m`; else `|di| ≈ cell_dx_m` (METR / `to_feet=False`). Relative tolerance ~1e-5, because DIDJ is float32
- clip must have one band; we do not compare ZALT vs clip samples in this PR

`read_nmbgf_header` slurps the ZALT payload. Acceptable for v1 (existing API). Do not add a header-only parser here.

## Tests

Use existing `tiny_dem_path` / `tiny_aoi_geom` fixtures. Home: `tests/test_write_aam.py` for `load_terrain`; `from_north_up_transform` next to grid tests (`test_aeqd_grid.py` or a small `test_grid_spec.py`).

1. **Round-trip** — `written = write_terrain(...)`; `loaded = load_terrain(written.elv_path, imp_path=written.imp_path, grid_agl_ft=written.grid_agl_ft, model_cell_ft=written.model_cell_ft, cutoff_ft=written.cutoff_ft)`. Assert `spec` fields (`pytest.approx` on origins/cell size), `aeqd_crs.equals` (not WKT string compare), `elv_header_feet`, paths, `flow_resistivity`. Reconstruct spec from the **on-disk clip** transform, not only `grid_from_elv_result` (GeoTIFF serialization is the production path). Existing `test_write_elv_from_dem` already checks `clip.crs == aeqd_crs`.
2. **`lonlat_to_model_ft`** — SW → ~(0, 0) ft and NE → extent, same assertions as `test_lonlat_to_model_ft_corners` but on the **loaded** object. Optionally `write_inp(loaded, ...)` still produces a TERRAIN block (regression for the documented consumer).
3. **ELV + clip only** — `write_elv_from_dem` then `load_terrain(elv)` with no IMP; `imp_path is None`; `lonlat_to_model_ft` still works.
4. **Missing clip / missing ELV** — `FileNotFoundError`.
5. **`from_north_up_transform`** — inverse of `from_origin` via `grid_from_elv_result(...).transform`; `ValueError` on rotation, south-up (`e > 0`), and west-up (`a < 0`).
6. **Mismatched clip** — same-shape non-AEQD GeoTIFF (e.g. the parent UTM DEM copied beside the ELV) → `ValueError`. Optional: clip with different `width`/`height` → `ValueError`.
7. **`to_feet=False`** — `write_elv_from_dem(..., to_feet=False)` then load; `elv_header_feet is False`; METR DIDJ vs meters cell size still passes.

Kwarg-default trap (document, no extra test required): `write_terrain(..., model_cell_ft=150)` then `load_terrain(elv)` without that kwarg yields `DEFAULT_MODEL_CELL_FT`. Those fields are not on disk.

No pandas/geopandas in the library API (numpy / rasterio / pyproj / shapely only).

## Out of scope (stay in ActiveSpace)

- `terrain_cache.json`, DEM mtime, AOI-bounds invalidation, site directory layout
- `Microphone`, NMSim omni mapping, TIS-shaped DataFrames
- GeoDataFrame split of points below terrain, job logging, clearance tolerance (currently 3 m)

`write_inp` currently reads `terrain.grid_agl_ft` but still uses **kwargs defaults** for `model_cell_ft` / `cutoff_ft` / `flow_resistivity` in `setup_para_block`. Reloading those fields onto `TerrainResult` does not change INP until a separate `write_inp` change. Do not bundle that with `load_terrain`.

## Later: sample surface elevation

A generic sampler is reasonable later; it is not required to ship `load_terrain`.

ActiveSpace bilinear-samples the clip as a proxy for AAM’s ELV lookup, then applies a clearance so mesh jobs do not die on `z <= surface`. That filter and tolerance are adapter policy. Clip sampling is why ActiveSpace needs the sidecar for more than CRS — this PR only needs it for georeference.

If this library later exposes sampling, prefer the grid AAM actually reads:

```python
def sample_elv_elevation_m(
    terrain: TerrainResult,
    lons: np.ndarray,
    lats: np.ndarray,
) -> np.ndarray:
    """Bilinear-sample written ZALT at WGS84 lon/lat; return meters MSL (NaN off-grid)."""
```

Use `lonlat_to_model_ft` / fractional `col_i`,`row_j` and `read_nmbgf_grid` (north-up, convert feet→m with `FT_PER_M`). Document it as “sample the lattice we wrote,” not bit-exact TERRAINCHK. Do not add geopandas. Do not freeze clip-vs-ELV interpolator details until a Docker/AAM check exists that points the sampler calls above-ground are accepted.

## Implementation notes

- Home: `write_terrain` / `load_terrain` in `terrain.py`. `from_north_up_transform` on `GridSpec`. `write_aam.py` keeps `write_aam_inputs` only.
- Style: match `write_terrain` (pathlib, keyword-only extras, raise on bad inputs).
- `grid_spec.py` should not grow a rasterio import unless it stays type-only.
- Consumer follow-up (not this repo): ActiveSpace `_terrain_from_disk` becomes `load_terrain(elv, imp_path=..., grid_agl_ft=params.grid_agl_ft, flow_resistivity=params.flow_resistivity)`.
