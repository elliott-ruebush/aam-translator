"""Orchestration: terrain (``.ELV`` / ``.IMP``) and full AAM scenario inputs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry.base import BaseGeometry

from .constants import (
    DEFAULT_CUTOFF_FT,
    DEFAULT_FLOW_RESISTIVITY,
    DEFAULT_GRID_AGL_FT,
    DEFAULT_MODEL_CELL_FT,
)
from .context import TerrainResult, aoi_clip_box, build_local_crs
from .write_elv import clip_path_for_elv, write_elv_from_dem
from .write_imp import ImpGridContext, write_imp_for_elv_grid
from .write_inp import PoiPoint, TrackPoint, write_inp

logger = logging.getLogger(__name__)


@dataclass
class AamInputs:
    """Paths and terrain state after writing a complete AAM case."""

    terrain: TerrainResult
    inp_path: str


def write_terrain(
    dem_path: str | Path,
    aoi: BaseGeometry,
    out_dir: str | Path,
    *,
    crs_in: str = "EPSG:4326",
    elv_basename: str = "scenario.elv",
    imp_basename: str = "scenario.imp",
    elv_title: str = "AAM elevation grid",
    imp_title: str = "AAM impedance grid",
    z0: float | None = None,
    to_feet: bool = True,
    nodata_policy: str = "edge",
    flow_resistivity: float = DEFAULT_FLOW_RESISTIVITY,
    grid_agl_ft: float = DEFAULT_GRID_AGL_FT,
    model_cell_ft: float = DEFAULT_MODEL_CELL_FT,
    cutoff_ft: float = DEFAULT_CUTOFF_FT,
) -> TerrainResult:
    """Clip ``dem_path`` to ``aoi``, write matching ``.ELV`` and ``.IMP`` files."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    clip_box = aoi_clip_box(aoi)
    local_crs = build_local_crs(aoi, crs_in=crs_in)
    elv_path = out / elv_basename
    imp_path = out / imp_basename

    elv_result = write_elv_from_dem(
        str(dem_path),
        str(elv_path),
        clip_box=clip_box,
        crs_in=crs_in,
        local_crs=local_crs,
        title=elv_title,
        z0=z0,
        to_feet=to_feet,
        nodata_policy=nodata_policy,
    )
    write_imp_for_elv_grid(
        str(imp_path),
        grid=ImpGridContext(
            width=elv_result.nx,
            height=elv_result.ny,
            dx_m=elv_result.elv_dx_m,
            dy_m=elv_result.elv_dy_m,
            header_feet=elv_result.elv_header_feet,
            default_flow_resistivity=flow_resistivity,
        ),
        title=imp_title,
        constant_value=flow_resistivity,
    )

    return TerrainResult(
        nx=elv_result.nx,
        ny=elv_result.ny,
        elv_dx_m=elv_result.elv_dx_m,
        elv_dy_m=elv_result.elv_dy_m,
        elv_header_feet=elv_result.elv_header_feet,
        elv_world_minx_m=elv_result.elv_world_minx_m,
        elv_world_miny_m=elv_result.elv_world_miny_m,
        local_crs=local_crs,
        elv_path=str(elv_path),
        imp_path=str(imp_path),
        clip_tif_path=clip_path_for_elv(str(elv_path)),
        grid_agl_ft=grid_agl_ft,
        model_cell_ft=model_cell_ft,
        cutoff_ft=cutoff_ft,
        flow_resistivity=flow_resistivity,
    )


def write_aam_inputs(
    dem_path: str | Path,
    aoi: BaseGeometry,
    out_dir: str | Path,
    *,
    track: list[TrackPoint],
    pois: list[PoiPoint],
    source_id: str,
    crs_in: str = "EPSG:4326",
    inp_basename: str = "scenario.inp",
    **terrain_kwargs,
) -> AamInputs:
    """Write terrain files and a single-event ``.INP`` file (``COMPUTEPOI`` mode) in one call."""
    terrain = write_terrain(dem_path, aoi, out_dir, crs_in=crs_in, **terrain_kwargs)
    inp_path = write_inp(
        terrain,
        Path(out_dir) / inp_basename,
        track=track,
        pois=pois,
        source_id=source_id,
    )
    return AamInputs(terrain=terrain, inp_path=inp_path)
