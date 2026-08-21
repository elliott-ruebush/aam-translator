"""AEQD local CRS and AAM model-space coordinate transforms."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry

from .constants import (
    DEFAULT_CUTOFF_FT,
    DEFAULT_FLOW_RESISTIVITY,
    DEFAULT_GRID_AGL_FT,
    DEFAULT_MODEL_CELL_FT,
    FT_PER_M,
    NMBGF_FLOAT,
)
from .grid_spec import GridSpec

if TYPE_CHECKING:
    from .write_elv import ElvWriteResult


@dataclass
class TerrainResult:
    """State after writing an ELV grid aligned to an AOI."""

    spec: GridSpec
    aeqd_crs: CRS
    elv_header_feet: bool
    elv_path: str
    imp_path: str | None = None
    clip_tif_path: str | None = None
    grid_agl_ft: float = DEFAULT_GRID_AGL_FT
    model_cell_ft: float = DEFAULT_MODEL_CELL_FT
    cutoff_ft: float = DEFAULT_CUTOFF_FT
    flow_resistivity: float = DEFAULT_FLOW_RESISTIVITY

    @classmethod
    def from_elv_write(
        cls,
        elv: ElvWriteResult,
        *,
        aeqd_crs: CRS,
        elv_path: str,
        imp_path: str | None = None,
        clip_tif_path: str | None = None,
        grid_agl_ft: float = DEFAULT_GRID_AGL_FT,
        model_cell_ft: float = DEFAULT_MODEL_CELL_FT,
        cutoff_ft: float = DEFAULT_CUTOFF_FT,
        flow_resistivity: float = DEFAULT_FLOW_RESISTIVITY,
    ) -> TerrainResult:
        """Build terrain state from an ``.ELV`` write plus companion file paths."""
        if clip_tif_path is None:
            from .write_elv import clip_path_for_elv

            clip_tif_path = clip_path_for_elv(elv_path)
        return cls(
            spec=elv.spec,
            aeqd_crs=aeqd_crs,
            elv_header_feet=elv.header_feet,
            elv_path=elv_path,
            imp_path=imp_path,
            clip_tif_path=clip_tif_path,
            grid_agl_ft=grid_agl_ft,
            model_cell_ft=model_cell_ft,
            cutoff_ft=cutoff_ft,
            flow_resistivity=flow_resistivity,
        )


def build_aeqd_crs(aoi: BaseGeometry, crs_in: str = "EPSG:4326") -> CRS:
    """Build an azimuthal equidistant CRS from the AOI envelope centroid."""
    envelope = aoi_envelope(aoi)
    lon0, lat0 = envelope.centroid.x, envelope.centroid.y
    return CRS.from_proj4(
        f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m +no_defs",
    )


def aoi_envelope(aoi: BaseGeometry) -> BaseGeometry:
    """Return the minimum bounding rectangle of the AOI."""
    return aoi.envelope


@lru_cache(maxsize=32)
def _wgs84_to_aeqd_transformer(crs_key: str) -> Transformer:
    """Return a cached WGS84→AEQD transformer keyed by CRS WKT."""
    return Transformer.from_crs("EPSG:4326", CRS.from_wkt(crs_key), always_xy=True)


def _wgs84_to_aeqd_m(aeqd_crs: CRS, lon: float, lat: float) -> tuple[float, float]:
    """Convert WGS84 lon/lat to AEQD plane coordinates in meters."""
    tf = _wgs84_to_aeqd_transformer(aeqd_crs.to_wkt())
    return tf.transform(lon, lat)


def _aeqd_m_to_model_ij(
    spec: GridSpec,
    aeqd_x_m: float,
    aeqd_y_m: float,
) -> tuple[float, float]:
    """Convert AEQD meters to fractional model column/row indices."""
    col_i = (aeqd_x_m - spec.grid_origin_x_m) / spec.cell_dx_m
    row_j = (aeqd_y_m - spec.grid_origin_y_m) / spec.cell_dy_m
    return col_i, row_j


def _model_ij_to_ft(spec: GridSpec, col_i: float, row_j: float) -> tuple[float, float]:
    """Convert fractional model column/row indices to AAM model feet."""
    model_x_ft = col_i * spec.cell_dx_m * FT_PER_M
    model_y_ft = row_j * spec.cell_dy_m * FT_PER_M
    return model_x_ft, model_y_ft


def lonlat_to_model_ft(
    terrain: TerrainResult,
    lon: float,
    lat: float,
) -> tuple[float, float]:
    """Convert WGS84 lon/lat to AAM model feet on the ELV grid."""
    aeqd_x_m, aeqd_y_m = _wgs84_to_aeqd_m(terrain.aeqd_crs, lon, lat)
    col_i, row_j = _aeqd_m_to_model_ij(terrain.spec, aeqd_x_m, aeqd_y_m)
    return _model_ij_to_ft(terrain.spec, col_i, row_j)


def elv_extent_ft(terrain: TerrainResult) -> tuple[float, float]:
    """Return the ELV upper-right corner in feet using float32 cell sizes."""
    spec = terrain.spec
    dx32 = struct.unpack(NMBGF_FLOAT, struct.pack(NMBGF_FLOAT, spec.cell_dx_m))[0]
    dy32 = struct.unpack(NMBGF_FLOAT, struct.pack(NMBGF_FLOAT, spec.cell_dy_m))[0]
    elv_x = spec.cell_count_x * dx32 * FT_PER_M
    elv_y = spec.cell_count_y * dy32 * FT_PER_M
    return elv_x, elv_y
