"""Orchestration: full AAM scenario inputs (terrain + ``.INP``)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shapely.geometry.base import BaseGeometry

from .context import TerrainResult
from .terrain import _sanitize_basename, write_terrain
from .write_inp import PoiPoint, TrackPoint, write_inp


@dataclass
class AamInputs:
    """Paths and terrain state after writing a complete AAM case."""

    terrain: TerrainResult
    inp_path: str


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
    """Write terrain files and a single-event ``.INP`` (``COMPUTEPOI`` mode)."""
    terrain = write_terrain(dem_path, aoi, out_dir, crs_in=crs_in, **terrain_kwargs)
    inp_path = write_inp(
        terrain,
        Path(out_dir) / _sanitize_basename(inp_basename, kind="inp_basename"),
        track=track,
        pois=pois,
        source_id=source_id,
    )
    return AamInputs(terrain=terrain, inp_path=inp_path)
