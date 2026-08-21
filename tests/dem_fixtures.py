"""Synthetic DEM and AOI builders for elevation resampling tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.transform import from_origin
from shapely.geometry import Polygon, box

TRIPLE_LAKES_LON = -148.90
TRIPLE_LAKES_LAT = 63.73


def utm_epsg_for_lon(lon: float) -> int:
    zone = int((lon + 180.0) // 6.0) + 1
    return 32600 + zone


def write_utm_planar_ramp_dem(
    path: Path,
    *,
    center_lon: float,
    center_lat: float,
    width_m: float,
    height_m: float,
    res_m: float,
    base_z: float = 500.0,
    slope_e: float = 0.2,
    slope_n: float = 0.2,
) -> dict[str, float]:
    """Write a north-up UTM GeoTIFF with ``z = base + slope_e·Δe + slope_n·Δn``."""
    utm_epsg = utm_epsg_for_lon(center_lon)
    utm = CRS.from_epsg(utm_epsg)
    to_utm = Transformer.from_crs("EPSG:4326", utm, always_xy=True)
    cx, cy = to_utm.transform(center_lon, center_lat)

    nx = int(round(width_m / res_m))
    ny = int(round(height_m / res_m))
    minx = cx - width_m / 2.0
    miny = cy - height_m / 2.0
    maxy = miny + ny * res_m
    transform = from_origin(minx, maxy, res_m, res_m)

    cols = np.arange(nx, dtype=np.float64)
    rows = np.arange(ny, dtype=np.float64)
    eastings = minx + (cols + 0.5) * res_m
    northings = maxy - (rows + 0.5) * res_m
    ee, nn = np.meshgrid(eastings, northings, indexing="xy")
    data = base_z + slope_e * (ee - minx) + slope_n * (nn - miny)
    data = data.astype(np.float32)

    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "width": nx,
        "height": ny,
        "crs": utm,
        "transform": transform,
        "nodata": -9999.0,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)

    return {
        "center_lon": center_lon,
        "center_lat": center_lat,
        "minx": minx,
        "miny": miny,
        "maxx": minx + nx * res_m,
        "maxy": maxy,
        "res_m": res_m,
        "nx": float(nx),
        "ny": float(ny),
    }


def wgs84_box_from_utm_extent(
    *,
    center_lon: float,
    center_lat: float,
    width_m: float,
    height_m: float,
    pad_m: float = 0.0,
) -> Polygon:
    """Build a WGS84 AOI envelope covering a UTM-centered rectangle."""
    utm_epsg = utm_epsg_for_lon(center_lon)
    utm = CRS.from_epsg(utm_epsg)
    to_utm = Transformer.from_crs("EPSG:4326", utm, always_xy=True)
    to_wgs = Transformer.from_crs(utm, "EPSG:4326", always_xy=True)
    cx, cy = to_utm.transform(center_lon, center_lat)

    half_w = width_m / 2.0 + pad_m
    half_h = height_m / 2.0 + pad_m
    corners = [
        to_wgs.transform(cx - half_w, cy - half_h),
        to_wgs.transform(cx + half_w, cy - half_h),
        to_wgs.transform(cx + half_w, cy + half_h),
        to_wgs.transform(cx - half_w, cy + half_h),
    ]
    lons = [c[0] for c in corners]
    lats = [c[1] for c in corners]
    return box(min(lons), min(lats), max(lons), max(lats))


def grid_from_elv_result(result, local_crs):
    """Reconstruct an ``AeqdGrid`` from ``ElvWriteResult`` for test assertions."""
    from rasterio.transform import from_origin

    from aam_translator.aeqd_grid import AeqdGrid

    maxx = result.elv_world_minx_m + result.nx * result.elv_dx_m
    maxy = result.elv_world_miny_m + result.ny * result.elv_dy_m
    return AeqdGrid(
        nx=result.nx,
        ny=result.ny,
        dx_m=result.elv_dx_m,
        dy_m=result.elv_dy_m,
        minx_m=result.elv_world_minx_m,
        miny_m=result.elv_world_miny_m,
        maxx_m=maxx,
        maxy_m=maxy,
        transform=from_origin(
            result.elv_world_minx_m,
            maxy,
            result.elv_dx_m,
            result.elv_dy_m,
        ),
        local_crs=local_crs,
    )
