"""Write a single-event AAM ``.INP`` file (``COMPUTEPOI`` mode)."""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .constants import (
    DEFAULT_CUTOFF_FT,
    DEFAULT_FLOW_RESISTIVITY,
    DEFAULT_MODEL_CELL_FT,
    FT_PER_M,
    FT_S_PER_KN,
    MAX_POI_POINTS,
    MAX_TRACK_POINTS,
)
from .context import TerrainResult, elv_extent_ft, lonlat_to_model_ft

logger = logging.getLogger(__name__)


@dataclass
class TrackPoint:
    """One source position on a ``ONE TRACK`` block.

    Varying ``speed_kn`` per point changes which NetCDF source sphere AAM
    selects, because AAM interpolates spheres on airspeed; a varying speed can
    silently change source levels.
    """

    lon: float
    lat: float
    alt_m: float  # MSL meters
    speed_kn: float | None = None  # falls back to write_inp's speed_kn
    heading_deg: float | None = None  # falls back to write_inp's heading_deg


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
    """Write a single-event ``.INP`` file and return the output path.

    One ``.POI`` output row is produced per track point, in track order. That
    holds because this writer never emits the ``TIMESPACING`` keyword and always
    writes zero turn radii, so AAM does not subdivide track segments. Note that
    output row timestamps are arrival times and may be non-monotonic when
    consecutive source points are at very different ranges; that is expected and
    does not indicate a problem.
    """
    if not track:
        raise ValueError("track must contain at least one point")
    if not pois:
        raise ValueError("pois must contain at least one point")
    if len(track) > MAX_TRACK_POINTS:
        raise ValueError(
            f"track has {len(track)} points; AAM 3.0.0 accepts at most "
            f"{MAX_TRACK_POINTS} and fails with exit code 0 beyond that",
        )
    if len(pois) > MAX_POI_POINTS:
        raise ValueError(
            f"pois has {len(pois)} points; AAM accepts at most {MAX_POI_POINTS}",
        )
    if len(track) > 1:
        for index, point in enumerate(track):
            effective_speed = (
                point.speed_kn if point.speed_kn is not None else speed_kn
            )
            if effective_speed <= 0:
                raise ValueError(
                    f"track point {index} has effective speed {effective_speed}; "
                    "multi-point tracks require strictly positive speed because "
                    "AAM rejects zero-speed segments with INTRTIME",
                )

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


def hop_speed_kn(
    track: Sequence[TrackPoint],
    terrain: TerrainResult,
    *,
    hop_s: float = 1.0,
) -> float:
    """Return the speed that makes the longest track segment take ``hop_s`` seconds.

    Writing N independent source points as one ``ONE TRACK`` block needs a speed
    high enough that AAM does not subdivide segments, and AAM rejects speed 0
    outright for multi-point tracks. This is a modeling device rather than a
    physical airspeed: it is acoustically inert only when the source sphere has a
    single airspeed, because AAM otherwise interpolates spheres on speed.
    """
    if len(track) < 2:
        raise ValueError("track must contain at least two points")
    if hop_s <= 0:
        raise ValueError(f"hop_s must be positive, got {hop_s}")

    positions_ft: list[tuple[float, float, float]] = []
    for point in track:
        x_ft, y_ft = lonlat_to_model_ft(terrain, point.lon, point.lat)
        z_ft = point.alt_m * FT_PER_M
        positions_ft.append((x_ft, y_ft, z_ft))

    max_segment_ft = max(
        math.dist(positions_ft[i], positions_ft[i + 1])
        for i in range(len(positions_ft) - 1)
    )
    return max_segment_ft / (hop_s * FT_S_PER_KN)


def _format_track_row(
    terrain: TerrainResult,
    point: TrackPoint,
    *,
    speed_kn: float,
    heading_deg: float,
) -> str:
    x_ft, y_ft = lonlat_to_model_ft(terrain, point.lon, point.lat)
    alt_ft = point.alt_m * FT_PER_M
    row_speed = point.speed_kn if point.speed_kn is not None else speed_kn
    row_heading = point.heading_deg if point.heading_deg is not None else heading_deg
    return (
        f"{x_ft:12.2f}{y_ft:12.2f}{alt_ft:10.1f}    0.00    0.00"
        f"{row_speed:9.1f}    0.00    0.00    0.00      {row_heading:.0f}."
    )


def _format_poi_row(terrain: TerrainResult, poi: PoiPoint) -> str:
    x_ft, y_ft = lonlat_to_model_ft(terrain, poi.lon, poi.lat)
    agl_ft = poi.agl_m * FT_PER_M
    return f"{poi.name[:12]:12s}{x_ft:12.2f}{y_ft:12.2f}{agl_ft:8.2f}"
