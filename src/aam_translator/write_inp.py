"""Write a single-event AAM ``.INP`` file (``COMPUTEPOI`` mode)."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path

from .constants import (
    DEFAULT_CUTOFF_FT,
    DEFAULT_FLOW_RESISTIVITY,
    DEFAULT_MODEL_CELL_FT,
    FT_PER_M,
)
from .context import TerrainResult, elv_extent_ft, lonlat_to_model_ft

logger = logging.getLogger(__name__)


@dataclass
class TrackPoint:
    lon: float
    lat: float
    alt_m: float  # MSL meters


@dataclass
class PoiPoint:
    name: str
    lon: float
    lat: float
    agl_m: float


def setup_para_block(
    terrain: TerrainResult,
    *,
    model_cell_ft: float = DEFAULT_MODEL_CELL_FT,
    cutoff_ft: float = DEFAULT_CUTOFF_FT,
    flow_resistivity: float = DEFAULT_FLOW_RESISTIVITY,
) -> str:
    """Return a SETUP PARA block whose grid bounds match the written ``.ELV``.

    AAM's TERRAINCHK compares the SETUP PARA upper-right corner to the ``.ELV``
    extent (nx * cell_size * 3.28084), reading the cell size back as the float32
    it was stored as. Corners are floored to whole model cells so the grid fits
    strictly inside the terrain extent.
    """
    elv_x, elv_y = elv_extent_ft(terrain)
    xmax = math.floor(elv_x / model_cell_ft) * model_cell_ft
    ymax = math.floor(elv_y / model_cell_ft) * model_cell_ft
    agl = terrain.grid_agl_ft
    return (
        "SETUP PARA\n"
        f"{model_cell_ft:10.0f}{model_cell_ft:10.0f}{0.0:10.1f}\n"
        f"{0.0:10.0f}{0.0:10.0f}{agl:10.1f}\n"
        f"{xmax:14.4f}{ymax:14.4f}\n"
        f"{40.0:10.0f}{cutoff_ft:10.0f}{flow_resistivity:10.0f}{0.0:10.1f}"
    )


def write_inp(
    terrain: TerrainResult,
    inp_path: str | Path,
    *,
    track: list[TrackPoint],
    pois: list[PoiPoint],
    source_id: str,
    track_name: str = "Track",
    elv_basename: str | None = None,
    imp_basename: str | None = None,
    include_diagnostics: bool = True,
    remark: str = "aam_translator COMPUTEPOI case",
    speed_kn: float = 0.0,
    heading_deg: float = 90.0,
) -> str:
    """Write a single-event ``.INP`` file and return the output path."""
    out = Path(inp_path)
    elv_name = elv_basename or Path(terrain.elv_path).name
    imp_name = imp_basename or (
        Path(terrain.imp_path).name if terrain.imp_path else "scenario.imp"
    )

    track_rows = [
        _format_track_row(
            terrain,
            point,
            speed_kn=speed_kn,
            heading_deg=heading_deg,
        )
        for point in track
    ]
    poi_rows = [_format_poi_row(terrain, poi) for poi in pois]

    lines = [
        f"REM {remark}",
        "COMPUTEPOI",
    ]
    if include_diagnostics:
        lines.append("DIAGNOSTICS")
    lines.extend([
        "TERRAIN",
        elv_name,
        imp_name,
        setup_para_block(terrain),
        source_id,
        "1",
        "      0.00      0.00      0.00",
        "0",
        "0",
        "ONE TRACK",
        track_name,
        str(len(track_rows)),
        *track_rows,
        "POI",
        str(len(poi_rows)),
        *poi_rows,
        "END",
    ])

    out.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    out.write_text(text, encoding="ascii")
    logger.info(".INP file saved to %s", out)
    return str(out)


def _format_track_row(
    terrain: TerrainResult,
    point: TrackPoint,
    *,
    speed_kn: float,
    heading_deg: float,
) -> str:
    x_ft, y_ft = lonlat_to_model_ft(terrain, point.lon, point.lat)
    alt_ft = point.alt_m * FT_PER_M
    return (
        f"{x_ft:12.2f}{y_ft:12.2f}{alt_ft:10.1f}    0.00    0.00"
        f"{speed_kn:9.1f}    0.00    0.00    0.00      {heading_deg:.0f}."
    )


def _format_poi_row(terrain: TerrainResult, poi: PoiPoint) -> str:
    x_ft, y_ft = lonlat_to_model_ft(terrain, poi.lon, poi.lat)
    agl_ft = poi.agl_m * FT_PER_M
    return f"{poi.name[:12]:12s}{x_ft:12.2f}{y_ft:12.2f}{agl_ft:8.2f}"
