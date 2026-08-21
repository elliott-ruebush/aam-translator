"""Clip a DEM to an AOI and write an AAM NMBGF ``.ELV`` elevation grid."""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry

from .aeqd_grid import (
    AeqdGrid,
    build_aeqd_grid,
    dem_posting_meters_from_src,
    resample_dem_to_aeqd_src,
    write_aeqd_geotiff,
)
from .constants import FT_PER_M, NMBGF_FLOAT
from .nmbgf_io import (
    NmbgfGridSpec,
    iter_grid_cells,
    write_nmbgf_case_header,
    write_nmbgf_end,
    write_nmbgf_metric_header,
    write_nmbgf_title,
)
from .nodata import fill_nodata

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ElvGeoref:
    """Horizontal georeferencing for the ELV grid in AEQD meters."""

    world_minx_m: float
    world_miny_m: float
    dx_m: float
    dy_m: float
    sw_lon: float
    sw_lat: float


@dataclass(frozen=True)
class ElvGridSpec(NmbgfGridSpec):
    """ELV grid spec plus elevation unit conversion flag."""

    to_feet: bool


@dataclass(frozen=True)
class ElvWriteResult:
    """State returned after a successful ``.ELV`` write."""

    nx: int
    ny: int
    elv_dx_m: float
    elv_dy_m: float
    elv_header_feet: bool
    elv_world_minx_m: float
    elv_world_miny_m: float


def clip_path_for_elv(elv_file: str | Path) -> str:
    """Sidecar GeoTIFF path written alongside ``scenario.elv``."""
    path = Path(elv_file)
    return str(path.with_name(f"{path.stem}_clip.tif"))


def georef_from_aeqd_grid(grid: AeqdGrid) -> ElvGeoref:
    """Derive ELV georef tags from a snapped AEQD lattice."""
    to_wgs84 = Transformer.from_crs(grid.local_crs, "EPSG:4326", always_xy=True)
    sw_lon, sw_lat = to_wgs84.transform(grid.minx_m, grid.miny_m)
    return ElvGeoref(
        world_minx_m=grid.minx_m,
        world_miny_m=grid.miny_m,
        dx_m=grid.dx_m,
        dy_m=grid.dy_m,
        sw_lon=sw_lon,
        sw_lat=sw_lat,
    )


def build_elv_grid_spec(georef: ElvGeoref, width: int, height: int, *, to_feet: bool) -> ElvGridSpec:
    """Header cell spacing and units tag from metric georef."""
    if to_feet:
        return ElvGridSpec(
            width=width,
            height=height,
            dx_out=georef.dx_m * FT_PER_M,
            dy_out=georef.dy_m * FT_PER_M,
            units_tag=b"FEET",
            to_feet=True,
        )
    return ElvGridSpec(
        width=width,
        height=height,
        dx_out=georef.dx_m,
        dy_out=georef.dy_m,
        units_tag=b"METR",
        to_feet=False,
    )


def prepare_elevation_array(
    elevation_m: np.ndarray,
    *,
    nodata_policy: str,
    z0: float | None,
) -> np.ndarray:
    """Fill nodata and optionally offset elevations (meters MSL)."""
    data = fill_nodata(elevation_m, np.nan, policy=nodata_policy)
    if z0 is not None:
        data = data + z0
    return data


def iter_zalt_values(data: np.ndarray, width: int, height: int, *, to_feet: bool):
    """Yield ZALT payload values in NMBGF column-major / j-reversed order."""
    for i, j in iter_grid_cells(width, height):
        val = float(data[j, i])
        if to_feet:
            val *= FT_PER_M
        yield val


def write_nmbgf_elv_stream(
    fp: BinaryIO,
    *,
    title: str,
    spec: ElvGridSpec,
    elevation_m: np.ndarray,
) -> int:
    """Write a complete ``.ELV`` NMBGF stream. Returns cells written."""
    write_nmbgf_title(fp)
    write_nmbgf_case_header(fp, title=title, spec=spec)
    n_cells = spec.width * spec.height
    write_nmbgf_metric_header(fp, mtrc_tag=b"Zalt", payload_tag=b"ZALT", n_cells=n_cells)

    logger.debug("Writing %s ZALT cells", n_cells)
    count = 0
    for val in iter_zalt_values(elevation_m, spec.width, spec.height, to_feet=spec.to_feet):
        fp.write(struct.pack(NMBGF_FLOAT, val))
        count += 1
    logger.debug("Wrote %s ZALT cells", count)

    write_nmbgf_end(fp)
    return count


def write_nmbgf_elv_file(
    elv_file: str | Path,
    *,
    title: str,
    spec: ElvGridSpec,
    elevation_m: np.ndarray,
) -> None:
    with open(elv_file, "wb") as fp:
        write_nmbgf_elv_stream(fp, title=title, spec=spec, elevation_m=elevation_m)
    logger.info(".ELV file saved to %s", elv_file)


def _reference_point(clip_box: BaseGeometry) -> tuple[float, float]:
    centroid = clip_box.centroid
    return centroid.x, centroid.y


def write_elv_from_dem(
    dem_path: str | Path,
    elv_file: str | Path,
    *,
    clip_box: BaseGeometry,
    crs_in: str | CRS,
    local_crs: CRS,
    title: str = "AAM elevation grid",
    z0: float | None = None,
    to_feet: bool = True,
    nodata_policy: str = "edge",
) -> ElvWriteResult:
    """End-to-end: resample parent DEM onto AEQD → ``scenario_clip.tif`` → ``.ELV``."""
    ref_lon, ref_lat = _reference_point(clip_box)
    with rasterio.open(dem_path) as dem_src:
        dx_m = dem_posting_meters_from_src(dem_src, ref_lon=ref_lon, ref_lat=ref_lat)
        grid = build_aeqd_grid(
            clip_box, local_crs, dx_m, crs_in=crs_in, dem_src=dem_src,
        )
        elevation_m = resample_dem_to_aeqd_src(dem_src, grid)
        elevation_m = prepare_elevation_array(
            elevation_m, nodata_policy=nodata_policy, z0=z0,
        )

    clipped_tif = clip_path_for_elv(elv_file)
    write_aeqd_geotiff(clipped_tif, grid, elevation_m)

    georef = georef_from_aeqd_grid(grid)
    spec = build_elv_grid_spec(georef, grid.nx, grid.ny, to_feet=to_feet)
    logger.info(
        "Writing .ELV grid %s x %s; AEQD lower-left (m)=%s,%s; cell (m)=%s,%s; SW (deg)=%s,%s",
        spec.width,
        spec.height,
        georef.world_minx_m,
        georef.world_miny_m,
        georef.dx_m,
        georef.dy_m,
        georef.sw_lon,
        georef.sw_lat,
    )
    write_nmbgf_elv_file(
        elv_file, title=title, spec=spec, elevation_m=elevation_m,
    )

    return ElvWriteResult(
        nx=spec.width,
        ny=spec.height,
        elv_dx_m=georef.dx_m,
        elv_dy_m=georef.dy_m,
        elv_header_feet=spec.to_feet,
        elv_world_minx_m=georef.world_minx_m,
        elv_world_miny_m=georef.world_miny_m,
    )
