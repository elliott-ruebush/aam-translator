"""Verify that ``.POI`` output rows line up with the track points that were written.

A ``.POI`` file carries no source-point index: row ``k`` corresponds to track
point ``k`` purely by position. AAM writes rows in track order and never sorts
or merges them, so the correspondence holds -- but nothing in the output file
proves it, and a mismatch would silently attribute a level to the wrong source
point. These helpers check it from the outside.

Two independent checks are available:

* :func:`assert_track_alignment` compares each row against the run log's
  ``Interpolated Track for analysis`` coordinates. This is exact and will catch
  an off-by-one, but it needs a log written with ``DIAGNOSTICS`` enabled.
* :func:`arrival_time_residuals` reconstructs each row's expected arrival time
  from pure geometry. It needs no log, but it only catches gross pairing errors:
  on a densely sampled track, neighbouring rows differ by far less than the
  uncertainty in sound speed, so a single-row shift is not detectable this way.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING

import numpy as np

from .constants import FT_PER_M, FT_S_PER_KN
from .context import TerrainResult, lonlat_to_model_ft

if TYPE_CHECKING:  # pragma: no cover - import only for type checking
    from .read_log import AamRunLog
    from .read_poi import PoiTimeHistory
    from .write_inp import PoiPoint, TrackPoint

# Dry-air speed of sound near 15 C. Varies about +/-2% over normal temperatures,
# which is why arrival-time checks are advisory rather than strict.
SOUND_SPEED_FT_S = 1116.4


def assert_track_alignment(
    *,
    history: PoiTimeHistory,
    track: Sequence[TrackPoint],
    terrain: TerrainResult,
    run_log: AamRunLog | None = None,
    tol_ft: float = 1.0,
) -> None:
    """Raise ``ValueError`` unless ``.POI`` row ``k`` is track point ``k``.

    Always checks the row count. When ``run_log`` carries an analysis track
    (AAM writes one under ``DIAGNOSTICS``), also checks that every analysis
    point matches the written track's model-foot position within ``tol_ft``,
    which is what actually detects an off-by-one.

    Row timestamps are deliberately not checked for monotonicity: arrival times
    routinely decrease between consecutive scattered source points.
    """
    if history.n_samples != len(track):
        raise ValueError(
            f"POI zone {history.zone_index} has {history.n_samples} rows but "
            f"{len(track)} track points were written; row k no longer "
            "corresponds to track point k"
        )

    if run_log is None:
        return
    if run_log.read_error is not None:
        raise ValueError(
            f"AAM reported a read error, so its output cannot be trusted:\n"
            f"{run_log.read_error}"
        )

    analysis = run_log.analysis_track
    if analysis is None:
        return
    if len(analysis) != len(track):
        raise ValueError(
            f"AAM analyzed {len(analysis)} track points but {len(track)} were "
            "written; AAM subdivided or dropped points"
        )

    for index, (point, analyzed) in enumerate(zip(track, analysis, strict=True)):
        x_ft, y_ft = lonlat_to_model_ft(terrain, point.lon, point.lat)
        offset = math.dist((x_ft, y_ft), (analyzed.x_ft, analyzed.y_ft))
        if offset > tol_ft:
            raise ValueError(
                f"track point {index} was written at ({x_ft:.2f}, {y_ft:.2f}) ft "
                f"but AAM analyzed ({analyzed.x_ft:.2f}, {analyzed.y_ft:.2f}) ft, "
                f"off by {offset:.2f} ft (tolerance {tol_ft} ft)"
            )


def arrival_time_residuals(
    *,
    history: PoiTimeHistory,
    track: Sequence[TrackPoint],
    poi: PoiPoint,
    terrain: TerrainResult,
    speed_kn: float,
    poi_ground_msl_ft: float = 0.0,
    sound_speed_ft_s: float = SOUND_SPEED_FT_S,
) -> np.ndarray:
    """Return per-row ``observed - predicted`` arrival time, in seconds.

    Predicted arrival is the emission time of track point ``k`` plus the slant
    range from that point to ``poi`` divided by ``sound_speed_ft_s``. Emission
    times accumulate segment by segment using AAM's constant-acceleration
    kinematics, so a per-point ``speed_kn`` override is honoured.

    Interpreting the result: a near-constant offset across all rows usually
    means ``sound_speed_ft_s`` or ``poi_ground_msl_ft`` does not match the run,
    not that rows are misaligned. Residuals that scatter, or that grow along the
    track, indicate the track and output do not belong together. On a validated
    400-point run this returns residuals under 0.01 s.

    ``poi_ground_msl_ft`` is needed because ``PoiPoint.agl_m`` is height above
    local ground while track altitudes are MSL; only the caller knows the DEM
    elevation under the receiver. The default of 0.0 suits near-sea-level sites.
    """
    if history.n_samples != len(track):
        raise ValueError(
            f"POI zone {history.zone_index} has {history.n_samples} rows but "
            f"{len(track)} track points were given"
        )
    if sound_speed_ft_s <= 0.0:
        raise ValueError(f"sound_speed_ft_s must be positive, got {sound_speed_ft_s}")

    positions = [_track_point_ft(terrain, point) for point in track]
    speeds = [_effective_speed_ft_s(point, speed_kn) for point in track]

    poi_x_ft, poi_y_ft = lonlat_to_model_ft(terrain, poi.lon, poi.lat)
    receiver = (poi_x_ft, poi_y_ft, poi_ground_msl_ft + poi.agl_m * FT_PER_M)

    predicted = np.empty(len(track), dtype=float)
    emission = 0.0
    for index, position in enumerate(positions):
        if index > 0:
            segment_ft = math.dist(positions[index - 1], position)
            # Constant acceleration between endpoint speeds; reduces to d / v
            # when the two speeds are equal.
            emission += 2.0 * segment_ft / (speeds[index - 1] + speeds[index])
        predicted[index] = emission + math.dist(position, receiver) / sound_speed_ft_s

    return history.time_s - predicted


def _track_point_ft(
    terrain: TerrainResult, point: TrackPoint
) -> tuple[float, float, float]:
    x_ft, y_ft = lonlat_to_model_ft(terrain, point.lon, point.lat)
    return x_ft, y_ft, point.alt_m * FT_PER_M


def _effective_speed_ft_s(point: TrackPoint, speed_kn: float) -> float:
    effective_kn = point.speed_kn if point.speed_kn is not None else speed_kn
    if effective_kn <= 0.0:
        raise ValueError(
            "arrival times need a positive speed on every track point; "
            f"got {effective_kn} kn"
        )
    return effective_kn * FT_S_PER_KN
