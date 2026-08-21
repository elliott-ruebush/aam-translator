"""Clip a DEM to an AOI and write an AAM NMBGF ``.ELV`` elevation grid."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry

from .aeqd_grid import (
    AeqdGrid,
    assert_aoi_within_dem_src,
    build_aeqd_grid,
    dem_posting_meters_from_src,
    resample_dem_to_aeqd_src,
    write_aeqd_geotiff,
)
from .grid_spec import GridSpec
from .nmbgf_io import (
    NmbgfGridSpec,
    build_nmbgf_grid_spec,
    pack_nmbgf_payload,
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

    spec: GridSpec
    sw_lon: float
    sw_lat: float


@dataclass(frozen=True)
class ElvGridSpec(NmbgfGridSpec):
    """ELV grid spec plus elevation unit conversion flag."""

    to_feet: bool


@dataclass(frozen=True)
class ElvWriteResult:
    """State returned after a successful ``.ELV`` write."""

    spec: GridSpec
    header_feet: bool


def clip_path_for_elv(elv_file: str | Path) -> str:
    """Sidecar GeoTIFF path written alongside ``scenario.elv``."""
    path = Path(elv_file)
    return str(path.with_name(f"{path.stem}_clip.tif"))


def georef_from_aeqd_grid(grid: AeqdGrid) -> ElvGeoref:
    """Derive ELV georef tags from a snapped AEQD lattice."""
    to_wgs84 = Transformer.from_crs(grid.aeqd_crs, "EPSG:4326", always_xy=True)
    spec = grid.spec
    sw_lon, sw_lat = to_wgs84.transform(spec.grid_origin_x_m, spec.grid_origin_y_m)
    return ElvGeoref(spec=spec, sw_lon=sw_lon, sw_lat=sw_lat)


def build_elv_grid_spec(
    georef: ElvGeoref, *, to_feet: bool,
) -> ElvGridSpec:
    """Header cell spacing and units tag from metric georef."""
    spec = georef.spec
    nmbgf_spec = build_nmbgf_grid_spec(
        width=spec.cell_count_x,
        height=spec.cell_count_y,
        dx_m=spec.cell_dx_m,
        dy_m=spec.cell_dy_m,
        header_feet=to_feet,
    )
    return ElvGridSpec(
        width=nmbgf_spec.width,
        height=nmbgf_spec.height,
        dx_out=nmbgf_spec.dx_out,
        dy_out=nmbgf_spec.dy_out,
        units_tag=nmbgf_spec.units_tag,
        to_feet=to_feet,
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
    write_nmbgf_metric_header(
        fp, mtrc_tag=b"Zalt", payload_tag=b"ZALT", n_cells=n_cells,
    )

    logger.debug("Writing %s ZALT cells", n_cells)
    fp.write(pack_nmbgf_payload(elevation_m, to_feet=spec.to_feet))
    logger.debug("Wrote %s ZALT cells", n_cells)

    write_nmbgf_end(fp)
    return n_cells


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


def _aoi_centroid_lonlat(aoi_envelope: BaseGeometry) -> tuple[float, float]:
    centroid = aoi_envelope.centroid
    return centroid.x, centroid.y


def write_elv_from_dem(
    dem_path: str | Path,
    elv_file: str | Path,
    *,
    aoi_envelope: BaseGeometry,
    crs_in: str | CRS,
    aeqd_crs: CRS,
    title: str = "AAM elevation grid",
    z0: float | None = None,
    to_feet: bool = True,
    nodata_policy: str = "edge",
) -> ElvWriteResult:
    """End-to-end: resample parent DEM onto AEQD → ``scenario_clip.tif`` → ``.ELV``."""
    ref_lon, ref_lat = _aoi_centroid_lonlat(aoi_envelope)
    with rasterio.open(dem_path) as dem_src:
        cell_dx_m = dem_posting_meters_from_src(
            dem_src, ref_lon=ref_lon, ref_lat=ref_lat,
        )
        assert_aoi_within_dem_src(
            aoi_envelope, dem_src, aeqd_crs, crs_in=crs_in, tol_m=cell_dx_m,
        )
        grid = build_aeqd_grid(
            aoi_envelope, aeqd_crs, cell_dx_m, crs_in=crs_in, dem_src=dem_src,
        )
        elevation_m = resample_dem_to_aeqd_src(dem_src, grid)
        elevation_m = prepare_elevation_array(
            elevation_m, nodata_policy=nodata_policy, z0=z0,
        )

    clipped_tif = clip_path_for_elv(elv_file)
    write_aeqd_geotiff(clipped_tif, grid, elevation_m)

    georef = georef_from_aeqd_grid(grid)
    spec = build_elv_grid_spec(georef, to_feet=to_feet)
    grid_spec = georef.spec
    logger.info(
        (
            "Writing .ELV grid %s x %s; grid origin (m)=%s,%s; "
            "cell (m)=%s,%s; SW (deg)=%s,%s"
        ),
        spec.width,
        spec.height,
        grid_spec.grid_origin_x_m,
        grid_spec.grid_origin_y_m,
        grid_spec.cell_dx_m,
        grid_spec.cell_dy_m,
        georef.sw_lon,
        georef.sw_lat,
    )
    write_nmbgf_elv_file(
        elv_file, title=title, spec=spec, elevation_m=elevation_m,
    )

    return ElvWriteResult(spec=grid_spec, header_feet=spec.to_feet)
