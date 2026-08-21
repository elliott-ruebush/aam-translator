"""Clip a DEM to an AOI and write an AAM NMBGF ``.ELV`` elevation grid."""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from typing import BinaryIO

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.mask import mask
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from .constants import FT_PER_M
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
class ClippedDem:
    """Metric DEM array clipped to the AOI, ready for ELV export."""

    data: np.ndarray
    profile: dict
    nodata: float | None
    crs: CRS


@dataclass(frozen=True)
class ElvGeoref:
    """Horizontal georeferencing for the ELV grid in AEQD metres."""

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


def clip_path_for_elv(elv_file: str) -> str:
    """Sidecar GeoTIFF path written alongside ``scenario.elv``."""
    return elv_file.replace(".elv", "_clip.tif")


def clip_dem_to_aoi(
    dem_path: str,
    clip_box: BaseGeometry,
    *,
    crs_in: str | CRS,
) -> ClippedDem:
    """Mask ``dem_path`` to ``clip_box`` (reprojecting the AOI into the DEM CRS)."""
    logger.info("Clipping DEM from %s", dem_path)
    with rasterio.open(dem_path) as src:
        dem_crs = src.crs
        if crs_in != dem_crs:
            tf = Transformer.from_crs(crs_in, dem_crs, always_xy=True)
            aoi_geom = transform(tf.transform, clip_box)
        else:
            aoi_geom = clip_box

        dem_clip, dem_clip_transform = mask(
            src, [aoi_geom], crop=True, filled=True, nodata=src.nodata,
        )
        arr = dem_clip[0]
        profile = src.profile.copy()
        profile.update({
            "height": arr.shape[0],
            "width": arr.shape[1],
            "transform": dem_clip_transform,
            "count": 1,
        })

    logger.info("DEM clipped to %s x %s cells", arr.shape[1], arr.shape[0])
    return ClippedDem(
        data=arr,
        profile=profile,
        nodata=profile.get("nodata"),
        crs=dem_crs,
    )


def write_clip_geotiff(clipped_tif: str, clipped: ClippedDem) -> None:
    """Persist the metric clip as ``scenario_clip.tif``."""
    with rasterio.open(clipped_tif, "w", **clipped.profile) as dst:
        dst.write(clipped.data, 1)


def compute_elv_georef(raster, local_crs: CRS) -> ElvGeoref:
    """Map the clipped raster SW corner into AEQD and WGS84."""
    tf_dem_to_local = Transformer.from_crs(raster.crs, local_crs, always_xy=True)
    world_minx_m, world_miny_m = tf_dem_to_local.transform(
        raster.bounds.left, raster.bounds.bottom,
    )
    tf_raster_to_wgs84 = Transformer.from_crs(raster.crs, "EPSG:4326", always_xy=True)
    sw_lon, sw_lat = tf_raster_to_wgs84.transform(
        raster.bounds.left, raster.bounds.bottom,
    )
    return ElvGeoref(
        world_minx_m=world_minx_m,
        world_miny_m=world_miny_m,
        dx_m=abs(raster.res[0]),
        dy_m=abs(raster.res[1]),
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
    raster,
    *,
    nodata_policy: str,
    z0: float | None,
) -> np.ndarray:
    """Read, fill nodata, and optionally offset elevations (metres MSL)."""
    data = fill_nodata(raster.read(1), raster.nodata, policy=nodata_policy)
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
        fp.write(struct.pack("f", val))
        count += 1
    logger.debug("Wrote %s ZALT cells", count)

    write_nmbgf_end(fp)
    return count


def write_nmbgf_elv_file(
    elv_file: str,
    *,
    title: str,
    spec: ElvGridSpec,
    elevation_m: np.ndarray,
) -> None:
    with open(elv_file, "wb") as fp:
        write_nmbgf_elv_stream(fp, title=title, spec=spec, elevation_m=elevation_m)
    logger.info(".ELV file saved to %s", elv_file)


def write_elv_from_dem(
    dem_path: str,
    elv_file: str,
    *,
    clip_box: BaseGeometry,
    crs_in: str | CRS,
    local_crs: CRS,
    title: str = "AAM elevation grid",
    z0: float | None = None,
    to_feet: bool = True,
    nodata_policy: str = "edge",
) -> ElvWriteResult:
    """End-to-end: clip DEM → ``scenario_clip.tif`` → ``scenario.elv``."""
    clipped = clip_dem_to_aoi(dem_path, clip_box, crs_in=crs_in)
    clipped_tif = clip_path_for_elv(elv_file)
    write_clip_geotiff(clipped_tif, clipped)

    with rasterio.open(clipped_tif) as raster:
        georef = compute_elv_georef(raster, local_crs)
        spec = build_elv_grid_spec(
            georef, raster.width, raster.height, to_feet=to_feet,
        )
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
        elevation_m = prepare_elevation_array(
            raster, nodata_policy=nodata_policy, z0=z0,
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
