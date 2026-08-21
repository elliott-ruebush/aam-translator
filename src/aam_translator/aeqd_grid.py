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


@dataclass(frozen=True)
class AeqdGrid:
    """North-up elevation lattice in a local azimuthal-equidistant CRS."""

    nx: int
    ny: int
    dx_m: float
    dy_m: float
    minx_m: float
    miny_m: float
    maxx_m: float
    maxy_m: float
    transform: Affine
    local_crs: CRS


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
    local_crs: CRS,
    *,
    crs_in: str | CRS = "EPSG:4326",
) -> tuple[float, float, float, float]:
    """Axis-aligned AEQD bounds of ``geom``'s corner coordinates."""
    aeqd_geom = transform_geometry_to_crs(geom, crs_in=crs_in, crs_out=local_crs)
    return aeqd_geom.bounds


def aeqd_bounds_from_dem_src(
    src: rasterio.io.DatasetReader,
    local_crs: CRS,
) -> tuple[float, float, float, float]:
    """Axis-aligned AEQD bounds of the parent DEM footprint."""
    to_aeqd = Transformer.from_crs(src.crs, local_crs, always_xy=True)
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
    return min(xs), min(ys), max(xs), max(ys)


def aeqd_bounds_from_dem(
    dem_path: str | Path,
    local_crs: CRS,
) -> tuple[float, float, float, float]:
    """Axis-aligned AEQD bounds of the parent DEM footprint."""
    with rasterio.open(dem_path) as src:
        return aeqd_bounds_from_dem_src(src, local_crs)


def merge_bounds(
    *bounds: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Return the union of several axis-aligned bounds."""
    minx = min(b[0] for b in bounds)
    miny = min(b[1] for b in bounds)
    maxx = max(b[2] for b in bounds)
    maxy = max(b[3] for b in bounds)
    return minx, miny, maxx, maxy


def assert_aoi_within_dem_src(
    clip_box: BaseGeometry,
    dem_src: rasterio.io.DatasetReader,
    local_crs: CRS,
    *,
    crs_in: str | CRS = "EPSG:4326",
    tol_m: float,
) -> None:
    """Raise if the AOI envelope extends beyond the parent DEM footprint."""
    aoi_bounds = aeqd_bounds_from_geometry(clip_box, local_crs, crs_in=crs_in)
    dem_bounds = aeqd_bounds_from_dem_src(dem_src, local_crs)
    if (
        aoi_bounds[0] < dem_bounds[0] - tol_m
        or aoi_bounds[1] < dem_bounds[1] - tol_m
        or aoi_bounds[2] > dem_bounds[2] + tol_m
        or aoi_bounds[3] > dem_bounds[3] + tol_m
    ):
        raise ValueError(
            "AOI extends beyond parent DEM coverage; "
            "use a DEM that fully covers the study area"
        )


def build_aeqd_grid(
    clip_box: BaseGeometry,
    local_crs: CRS,
    dx_m: float,
    *,
    crs_in: str | CRS = "EPSG:4326",
    dy_m: float | None = None,
    dem_path: str | Path | None = None,
    dem_src: rasterio.io.DatasetReader | None = None,
) -> AeqdGrid:
    """Snap an axis-aligned AEQD rectangle that covers ``clip_box`` and the DEM."""
    if dy_m is None:
        dy_m = dx_m

    bounds = [aeqd_bounds_from_geometry(clip_box, local_crs, crs_in=crs_in)]
    if dem_src is not None:
        bounds.append(aeqd_bounds_from_dem_src(dem_src, local_crs))
    elif dem_path is not None:
        bounds.append(aeqd_bounds_from_dem(dem_path, local_crs))
    minx, miny, maxx, maxy = merge_bounds(*bounds)

    nx = int(math.ceil((maxx - minx) / dx_m))
    ny = int(math.ceil((maxy - miny) / dy_m))
    grid_maxx = minx + nx * dx_m
    grid_maxy = miny + ny * dy_m

    grid_transform = from_origin(minx, grid_maxy, dx_m, dy_m)
    return AeqdGrid(
        nx=nx,
        ny=ny,
        dx_m=dx_m,
        dy_m=dy_m,
        minx_m=minx,
        miny_m=miny,
        maxx_m=grid_maxx,
        maxy_m=grid_maxy,
        transform=grid_transform,
        local_crs=local_crs,
    )


def aeqd_cell_center(grid: AeqdGrid, i: int, j: int) -> tuple[float, float]:
    """Return the AEQD center of model cell ``(i, j)`` (``j=0`` is south)."""
    x_m = grid.minx_m + (i + 0.5) * grid.dx_m
    y_m = grid.miny_m + (j + 0.5) * grid.dy_m
    return x_m, y_m


def resample_dem_to_aeqd_src(
    src: rasterio.io.DatasetReader,
    grid: AeqdGrid,
) -> np.ndarray:
    """Bilinear-resample ``src`` onto ``grid``; nodata → ``NaN``."""
    dst = np.full((grid.ny, grid.nx), np.nan, dtype=np.float64)
    reproject(
        source=rasterio.band(src, 1),
        destination=dst,
        src_transform=src.transform,
        src_crs=src.crs,
        dst_transform=grid.transform,
        dst_crs=grid.local_crs,
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
    profile = {
        "driver": "GTiff",
        "dtype": "float64",
        "count": 1,
        "width": grid.nx,
        "height": grid.ny,
        "crs": grid.local_crs,
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
