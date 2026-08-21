"""AEQD local CRS and AAM model-space coordinate transforms."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry

from .constants import (
    DEFAULT_CUTOFF_FT,
    DEFAULT_FLOW_RESISTIVITY,
    DEFAULT_GRID_AGL_FT,
    DEFAULT_MODEL_CELL_FT,
    FT_PER_M,
)


@dataclass
class TerrainResult:
    """State after writing an ELV grid aligned to an AOI."""

    nx: int
    ny: int
    elv_dx_m: float
    elv_dy_m: float
    elv_header_feet: bool
    elv_world_minx_m: float
    elv_world_miny_m: float
    local_crs: CRS
    elv_path: str
    imp_path: str | None = None
    clip_tif_path: str | None = None
    grid_agl_ft: float = DEFAULT_GRID_AGL_FT
    model_cell_ft: float = DEFAULT_MODEL_CELL_FT
    cutoff_ft: float = DEFAULT_CUTOFF_FT
    flow_resistivity: float = DEFAULT_FLOW_RESISTIVITY


def build_local_crs(aoi_geom: BaseGeometry, crs_in: str = "EPSG:4326") -> CRS:
    """Build an azimuthal equidistant CRS from the AOI envelope centroid."""
    clip_box = aoi_clip_box(aoi_geom)
    lon0, lat0 = clip_box.centroid.x, clip_box.centroid.y
    return CRS.from_proj4(
        f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m +no_defs",
    )


def aoi_clip_box(aoi_geom: BaseGeometry) -> BaseGeometry:
    """Return the minimum bounding rectangle of the AOI."""
    return aoi_geom.envelope


def lonlat_to_model_ft(
    terrain: TerrainResult,
    lon: float,
    lat: float,
) -> tuple[float, float]:
    """Convert WGS84 lon/lat to AAM model feet on the ELV grid."""
    tf = Transformer.from_crs("EPSG:4326", terrain.local_crs, always_xy=True)
    x_m, y_m = tf.transform(lon, lat)
    i = (x_m - terrain.elv_world_minx_m) / terrain.elv_dx_m
    j = (y_m - terrain.elv_world_miny_m) / terrain.elv_dy_m
    x_ft = i * terrain.elv_dx_m * FT_PER_M
    y_ft = j * terrain.elv_dy_m * FT_PER_M
    return x_ft, y_ft


def elv_extent_ft(terrain: TerrainResult) -> tuple[float, float]:
    """Return the ELV upper-right corner in feet using float32 cell sizes."""
    dx32 = struct.unpack("f", struct.pack("f", terrain.elv_dx_m))[0]
    dy32 = struct.unpack("f", struct.pack("f", terrain.elv_dy_m))[0]
    elv_x = terrain.nx * dx32 * FT_PER_M
    elv_y = terrain.ny * dy32 * FT_PER_M
    return elv_x, elv_y
