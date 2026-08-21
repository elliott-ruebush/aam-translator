# DEM → AAM ELV pipeline

Reference for the AEQD resample implemented in ``write_elv.py``. Regenerating figures:

```
uv pip install matplotlib   # not a runtime dependency
python docs/generate_elv_pipeline_figures.py
```

## Three spaces

| Space | CRS | Units / lattice |
| --- | --- | --- |
| **UTM GeoTIFF** (any projected DEM) | native DEM CRS | pixel values in **meters MSL** |
| **Local AEQD tangent plane** | `+proj=aeqd +lat_0 +lon_0 +datum=WGS84 +units=m` from the AOI envelope centroid | continuous Cartesian **meters**. The CRS exists only to define the plane. |
| **ELV / AAM model space** | **none** | regular `(i, j)` lattice. `XRYR=(0,0)`, `DIDJ` in **feet**, `ZALT` in **feet**. First payload cell is SW (column-major, j-reversed). |

```mermaid
flowchart LR
  subgraph utmSpace ["1. UTM GeoTIFF"]
    dem["Projected DEM<br/>meters MSL"]
  end
  subgraph aeqdSpace ["2. Local AEQD tangent plane"]
    plane["Cartesian meters<br/>origin = AOI centroid"]
  end
  subgraph elvSpace ["3. ELV / AAM model space"]
    elv["No CRS — (i, j) lattice<br/>DIDJ / ZALT in feet"]
  end
  dem -->|"GDAL warp; bilinear at cell centers"| plane
  plane -->|"× 3.28084, XRYR = (0, 0)"| elv
  poi["Tracks / POIs"] -->|"lonlat_to_model_ft"| elv
```

## Intended pipeline

1. **Inputs:** parent DEM + AOI (WGS84). Cell size `dx`/`dy` comes from the DEM posting at the AOI centroid (`dem_posting_meters_from_src`) — metric only; never put degrees in `DIDJ`.
2. **Build AEQD** from the AOI envelope centroid (`build_local_crs`).
3. **Window** the source DEM in its native CRS if you like (optional preprocess). That window is **not** the ELV grid; the writer reprojects the open raster via GDAL warp.
4. Transform the AOI envelope **and** parent DEM footprint to AEQD; take the axis-aligned bbox of their **union** (`build_aeqd_grid`). `nx = ceil(width/dx)`, `ny = ceil(height/dy)` so the rectangle **covers** that bbox. Reject AOIs that extend past the DEM (`assert_aoi_within_dem_src`).
5. Cell **corners:** SW of cell `(0,0)` is the model origin. Cell **centers** (where Z is sampled):

   `center = (minx + (i + 0.5)·dx, miny + (j + 0.5)·dy)`

6. **Bilinear-sample** the parent DEM at those geographic centers (GDAL warp onto the AEQD affine). Fill nodata **after** resample, not before.
7. **Write NMBGF:** `FEET`, `DIDJ = dx · 3.28084`, `XRYR = (0, 0)`, `ZALT = z_m · 3.28084`. `_clip.tif` should be this AEQD grid.
8. **Tracks / POIs:** `lonlat → AEQD → (i, j) → feet` (`lonlat_to_model_ft`).

## Current behavior

``write_elv_from_dem`` builds a regular AEQD lattice, bilinear-resamples the parent DEM onto it, fills nodata **after** resample, and writes that grid to both ``_clip.tif`` (meters, ``local_crs``) and ``.ELV`` (feet).

## Constants

- `FT_PER_M = 3.28084` (AAM / TERRAINCHK, **not** 3.280839895).
- FLOW stays **mks rayls** (do not multiply by `FT_PER_M`).

## Figures

Synthetic geometry (UTM zone 6N, ~9 km × 4 km at 63.73°N, −148.90°). Not a Denali DEM.

**Figure 1 — UTM rectangle vs true AEQD bbox (the horizontal lie).** Legacy UTM-index copy treated pixels as if they sat on the dashed rectangle; the current writer bilinear-resamples onto AEQD cell centers (see [Current behavior](#current-behavior)).

![UTM tile in AEQD vs fake rectangle vs true bbox](figures/utm_vs_aeqd.png)

**Figure 2 — cell corner vs cell center.** Origin is a corner; `ZALT` is a center sample.

![4x3 cartoon grid with origin at SW corner and samples at centers](figures/cell_center_vs_corner.png)

**Figure 3 — sampling.** Bilinear-sample the parent DEM at AEQD centers — they do not coincide with UTM pixel centers.

![AEQD sample centers over a UTM pixel grid](figures/aeqd_sample_centers.png)
