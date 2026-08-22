"""Build a regular AEQD lattice and resample a parent DEM onto it."""

from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.transform import Affine, from_origin
from rasterio.warp import Resampling, reproject
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from .grid_spec import BoundsM, GridSpec, merge_bounds


@dataclass(frozen=True)
class AeqdGrid:
    """North-up elevation lattice in a local azimuthal-equidistant CRS."""

    spec: GridSpec
    grid_extent_x_m: float
    grid_extent_y_m: float
    transform: Affine
    aeqd_crs: CRS


def dem_posting_meters_from_src(
    src: rasterio.io.DatasetReader,
    *,
    ref_lon: float,
    ref_lat: float,
) -> float:
    """Return the source DEM cell size in meters at ``(ref_lon, ref_lat)``."""
    dx = abs(src.transform.a)
    dy = abs(src.transform.e)
    if not src.crs.is_geographic:
        return float(dx if abs(dx - dy) < 1e-6 else max(dx, dy))

    # Approximate metric posting for geographic rasters at the reference latitude.
    meters_per_deg_lon = 111_320.0 * math.cos(math.radians(ref_lat))
    meters_per_deg_lat = 111_132.0
    dx_m = dx * meters_per_deg_lon
    dy_m = dy * meters_per_deg_lat
    return float(dx_m if abs(dx_m - dy_m) < 1e-6 else max(dx_m, dy_m))


def transform_geometry_to_crs(
    geom: BaseGeometry,
    *,
    crs_in: str | CRS,
    crs_out: CRS,
) -> BaseGeometry:
    """Reproject ``geom`` from ``crs_in`` into ``crs_out``."""
    tf = Transformer.from_crs(crs_in, crs_out, always_xy=True)
    return transform(tf.transform, geom)


def aeqd_bounds_from_geometry(
    geom: BaseGeometry,
    aeqd_crs: CRS,
    *,
    crs_in: str | CRS = "EPSG:4326",
) -> BoundsM:
    """Axis-aligned AEQD bounds of ``geom``'s corner coordinates."""
    aeqd_geom = transform_geometry_to_crs(geom, crs_in=crs_in, crs_out=aeqd_crs)
    return BoundsM.from_tuple(aeqd_geom.bounds)


def aeqd_bounds_from_dem_src(
    src: rasterio.io.DatasetReader,
    aeqd_crs: CRS,
) -> BoundsM:
    """Axis-aligned AEQD bounds of the parent DEM footprint."""
    to_aeqd = Transformer.from_crs(src.crs, aeqd_crs, always_xy=True)
    bounds = src.bounds
    corners = [
        (bounds.left, bounds.bottom),
        (bounds.right, bounds.bottom),
        (bounds.right, bounds.top),
        (bounds.left, bounds.top),
    ]
    xs, ys = zip(
        *(to_aeqd.transform(x, y) for x, y in corners),
        strict=True,
    )
    return BoundsM(min(xs), min(ys), max(xs), max(ys))


def aeqd_bounds_from_dem(
    dem_path: str | Path,
    aeqd_crs: CRS,
) -> BoundsM:
    """Axis-aligned AEQD bounds of the parent DEM footprint."""
    with rasterio.open(dem_path) as src:
        return aeqd_bounds_from_dem_src(src, aeqd_crs)


def assert_aoi_within_dem_src(
    aoi_envelope: BaseGeometry,
    dem_src: rasterio.io.DatasetReader,
    aeqd_crs: CRS,
    *,
    crs_in: str | CRS = "EPSG:4326",
    tol_m: float,
) -> None:
    """Raise if the AOI envelope extends beyond the parent DEM footprint."""
    aoi_bounds = aeqd_bounds_from_geometry(aoi_envelope, aeqd_crs, crs_in=crs_in)
    dem_bounds = aeqd_bounds_from_dem_src(dem_src, aeqd_crs)
    if (
        aoi_bounds.xmin_m < dem_bounds.xmin_m - tol_m
        or aoi_bounds.ymin_m < dem_bounds.ymin_m - tol_m
        or aoi_bounds.xmax_m > dem_bounds.xmax_m + tol_m
        or aoi_bounds.ymax_m > dem_bounds.ymax_m + tol_m
    ):
        raise ValueError(
            "AOI extends beyond parent DEM coverage; "
            "use a DEM that fully covers the study area"
        )


def build_aeqd_grid(
    aoi_envelope: BaseGeometry,
    aeqd_crs: CRS,
    cell_dx_m: float,
    *,
    crs_in: str | CRS = "EPSG:4326",
    cell_dy_m: float | None = None,
    dem_path: str | Path | None = None,
    dem_src: rasterio.io.DatasetReader | None = None,
) -> AeqdGrid:
    """Snap an axis-aligned AEQD rectangle that covers ``aoi_envelope`` and the DEM."""
    if cell_dy_m is None:
        cell_dy_m = cell_dx_m

    bounds = [aeqd_bounds_from_geometry(aoi_envelope, aeqd_crs, crs_in=crs_in)]
    if dem_src is not None:
        bounds.append(aeqd_bounds_from_dem_src(dem_src, aeqd_crs))
    elif dem_path is not None:
        bounds.append(aeqd_bounds_from_dem(dem_path, aeqd_crs))
    merged = merge_bounds(*bounds)

    cell_count_x = int(math.ceil((merged.xmax_m - merged.xmin_m) / cell_dx_m))
    cell_count_y = int(math.ceil((merged.ymax_m - merged.ymin_m) / cell_dy_m))
    grid_extent_x_m = merged.xmin_m + cell_count_x * cell_dx_m
    grid_extent_y_m = merged.ymin_m + cell_count_y * cell_dy_m

    spec = GridSpec(
        cell_count_x=cell_count_x,
        cell_count_y=cell_count_y,
        cell_dx_m=cell_dx_m,
        cell_dy_m=cell_dy_m,
        grid_origin_x_m=merged.xmin_m,
        grid_origin_y_m=merged.ymin_m,
    )
    grid_transform = from_origin(
        spec.grid_origin_x_m,
        grid_extent_y_m,
        spec.cell_dx_m,
        spec.cell_dy_m,
    )
    return AeqdGrid(
        spec=spec,
        grid_extent_x_m=grid_extent_x_m,
        grid_extent_y_m=grid_extent_y_m,
        transform=grid_transform,
        aeqd_crs=aeqd_crs,
    )


def aeqd_cell_center(grid: AeqdGrid, col_i: int, row_j: int) -> tuple[float, float]:
    """Return the AEQD center of model cell ``(col_i, row_j)``; ``row_j=0`` is south."""
    spec = grid.spec
    aeqd_x_m = spec.grid_origin_x_m + (col_i + 0.5) * spec.cell_dx_m
    aeqd_y_m = spec.grid_origin_y_m + (row_j + 0.5) * spec.cell_dy_m
    return aeqd_x_m, aeqd_y_m


def resample_dem_to_aeqd_src(
    src: rasterio.io.DatasetReader,
    grid: AeqdGrid,
) -> np.ndarray:
    """Bilinear-resample ``src`` onto ``grid``; nodata → ``NaN``."""
    spec = grid.spec
    dst = np.full((spec.cell_count_y, spec.cell_count_x), np.nan, dtype=np.float64)
    reproject(
        source=rasterio.band(src, 1),
        destination=dst,
        src_transform=src.transform,
        src_crs=src.crs,
        dst_transform=grid.transform,
        dst_crs=grid.aeqd_crs,
        src_nodata=src.nodata,
        dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )
    return dst


def resample_dem_to_aeqd(
    dem_path: str | Path,
    grid: AeqdGrid,
) -> np.ndarray:
    """Bilinear-resample ``dem_path`` onto ``grid``; nodata → ``NaN``."""
    with rasterio.open(dem_path) as src:
        return resample_dem_to_aeqd_src(src, grid)


def write_aeqd_geotiff(
    path: str | Path,
    grid: AeqdGrid,
    elevation_m: np.ndarray,
    *,
    nodata: float | None = np.nan,
) -> None:
    """Write the AEQD elevation lattice that was encoded into ``.ELV``."""
    spec = grid.spec
    profile = {
        "driver": "GTiff",
        "dtype": "float64",
        "count": 1,
        "width": spec.cell_count_x,
        "height": spec.cell_count_y,
        "crs": grid.aeqd_crs,
        "transform": grid.transform,
        "nodata": nodata,
    }
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        suffix=out_path.suffix,
        dir=out_path.parent,
        prefix=f".{out_path.stem}.",
    )
    os.close(fd)
    tmp = Path(tmp_path)
    try:
        with rasterio.open(tmp, "w", **profile) as dst:
            dst.write(elevation_m.astype(np.float64), 1)
        tmp.replace(out_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
