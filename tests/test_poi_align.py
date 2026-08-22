"""Tests for verifying ``.POI`` rows against the track that produced them."""

from __future__ import annotations

import math

import numpy as np
import pytest
from shapely.geometry import Point

from aam_translator.constants import FT_PER_M, FT_S_PER_KN
from aam_translator.context import TerrainResult, build_aeqd_crs, lonlat_to_model_ft
from aam_translator.grid_spec import GridSpec
from aam_translator.poi_align import (
    SOUND_SPEED_FT_S,
    arrival_time_residuals,
    assert_track_alignment,
)
from aam_translator.read_log import AamRunLog, AnalysisTrackPoint
from aam_translator.read_poi import PoiTimeHistory
from aam_translator.write_inp import PoiPoint, TrackPoint

SITE_LON, SITE_LAT = -148.87473, 63.66258
SPEED_KN = 136.1


@pytest.fixture
def terrain() -> TerrainResult:
    """A terrain whose model-foot origin sits on the AEQD origin."""
    return TerrainResult(
        spec=GridSpec(
            cell_count_x=400,
            cell_count_y=400,
            cell_dx_m=30.0,
            cell_dy_m=30.0,
            grid_origin_x_m=-6000.0,
            grid_origin_y_m=-6000.0,
        ),
        aeqd_crs=build_aeqd_crs(Point(SITE_LON, SITE_LAT)),
        elv_header_feet=True,
        elv_path="scenario.elv",
    )


@pytest.fixture
def poi() -> PoiPoint:
    return PoiPoint("Receiver", SITE_LON, SITE_LAT, 1.5)


@pytest.fixture
def track() -> list[TrackPoint]:
    return [
        TrackPoint(SITE_LON - 0.02, SITE_LAT + 0.01, 400.0),
        TrackPoint(SITE_LON - 0.01, SITE_LAT + 0.01, 400.0),
        TrackPoint(SITE_LON + 0.01, SITE_LAT + 0.01, 400.0),
    ]


def test_arrival_residuals_are_zero_for_a_consistent_history(
    terrain: TerrainResult, track: list[TrackPoint], poi: PoiPoint
) -> None:
    times = _expected_arrivals(terrain, track, poi, SPEED_KN)
    history = _history(times)
    residuals = arrival_time_residuals(
        history=history,
        track=track,
        poi=poi,
        terrain=terrain,
        speed_kn=SPEED_KN,
    )
    np.testing.assert_allclose(residuals, 0.0, atol=1e-9)


def test_arrival_residuals_detect_a_shifted_history(
    terrain: TerrainResult, track: list[TrackPoint], poi: PoiPoint
) -> None:
    times = _expected_arrivals(terrain, track, poi, SPEED_KN)
    shifted = _history(np.roll(times, 1))
    residuals = arrival_time_residuals(
        history=shifted,
        track=track,
        poi=poi,
        terrain=terrain,
        speed_kn=SPEED_KN,
    )
    assert np.abs(residuals).max() > 1.0


def test_arrival_residuals_tolerate_non_monotonic_times(
    terrain: TerrainResult, poi: PoiPoint
) -> None:
    # A supersonic hop speed makes emission time advance far slower than the
    # change in slant range, so arrival times decrease. This is a valid run.
    hop_track = [
        TrackPoint(SITE_LON - 0.05, SITE_LAT, 400.0),
        TrackPoint(SITE_LON + 0.001, SITE_LAT, 400.0),
    ]
    times = _expected_arrivals(terrain, hop_track, poi, 5833.3)
    assert times[1] < times[0]

    residuals = arrival_time_residuals(
        history=_history(times),
        track=hop_track,
        poi=poi,
        terrain=terrain,
        speed_kn=5833.3,
    )
    np.testing.assert_allclose(residuals, 0.0, atol=1e-9)


def test_arrival_residuals_reject_row_count_mismatch(
    terrain: TerrainResult, track: list[TrackPoint], poi: PoiPoint
) -> None:
    with pytest.raises(ValueError, match="has 2 rows but 3 track points"):
        arrival_time_residuals(
            history=_history(np.array([1.0, 2.0])),
            track=track,
            poi=poi,
            terrain=terrain,
            speed_kn=SPEED_KN,
        )


def test_arrival_residuals_reject_zero_speed(
    terrain: TerrainResult, track: list[TrackPoint], poi: PoiPoint
) -> None:
    with pytest.raises(ValueError, match="positive speed"):
        arrival_time_residuals(
            history=_history(np.zeros(3)),
            track=track,
            poi=poi,
            terrain=terrain,
            speed_kn=0.0,
        )


def test_assert_alignment_passes_on_matching_counts(
    terrain: TerrainResult, track: list[TrackPoint]
) -> None:
    assert_track_alignment(history=_history(np.zeros(3)), track=track, terrain=terrain)


def test_assert_alignment_rejects_row_count_mismatch(
    terrain: TerrainResult, track: list[TrackPoint]
) -> None:
    with pytest.raises(ValueError, match="2 rows but 3 track points"):
        assert_track_alignment(
            history=_history(np.zeros(2)), track=track, terrain=terrain
        )


def test_assert_alignment_accepts_matching_analysis_track(
    terrain: TerrainResult, track: list[TrackPoint]
) -> None:
    assert_track_alignment(
        history=_history(np.zeros(3)),
        track=track,
        terrain=terrain,
        run_log=_run_log(_analysis_points(terrain, track)),
    )


def test_assert_alignment_detects_off_by_one_analysis_track(
    terrain: TerrainResult, track: list[TrackPoint]
) -> None:
    # Same row count, but AAM analyzed the points in a shifted order. Only the
    # coordinate comparison can catch this.
    points = _analysis_points(terrain, track)
    shifted = [points[-1], *points[:-1]]
    with pytest.raises(ValueError, match="track point 0 was written at"):
        assert_track_alignment(
            history=_history(np.zeros(3)),
            track=track,
            terrain=terrain,
            run_log=_run_log(shifted),
        )


def test_assert_alignment_detects_subdivided_analysis_track(
    terrain: TerrainResult, track: list[TrackPoint]
) -> None:
    points = _analysis_points(terrain, track)
    with pytest.raises(ValueError, match="analyzed 4 track points but 3 were written"):
        assert_track_alignment(
            history=_history(np.zeros(3)),
            track=track,
            terrain=terrain,
            run_log=_run_log([*points, points[-1]]),
        )


def test_assert_alignment_rejects_a_run_with_a_read_error(
    terrain: TerrainResult, track: list[TrackPoint]
) -> None:
    log = _run_log(_analysis_points(terrain, track), read_error="*** READ ERROR ***")
    with pytest.raises(ValueError, match="AAM reported a read error"):
        assert_track_alignment(
            history=_history(np.zeros(3)),
            track=track,
            terrain=terrain,
            run_log=log,
        )


def test_assert_alignment_skips_checks_without_an_analysis_track(
    terrain: TerrainResult, track: list[TrackPoint]
) -> None:
    assert_track_alignment(
        history=_history(np.zeros(3)),
        track=track,
        terrain=terrain,
        run_log=_run_log(None),
    )


def _history(times: np.ndarray) -> PoiTimeHistory:
    times = np.asarray(times, dtype=float)
    return PoiTimeHistory(
        zone_index=1,
        time_s=times,
        broadband_db=np.zeros((times.size, 5)),
        band_levels_db=np.zeros((times.size, 4)),
        band_numbers=(10, 11, 12, 13),
    )


def _expected_arrivals(
    terrain: TerrainResult,
    track: list[TrackPoint],
    poi: PoiPoint,
    speed_kn: float,
) -> np.ndarray:
    """Compute arrival times independently of ``poi_align``'s internals."""
    positions = [
        (*lonlat_to_model_ft(terrain, p.lon, p.lat), p.alt_m * FT_PER_M) for p in track
    ]
    receiver = (*lonlat_to_model_ft(terrain, poi.lon, poi.lat), poi.agl_m * FT_PER_M)
    speed_ft_s = speed_kn * FT_S_PER_KN

    arrivals = []
    emission = 0.0
    for index, position in enumerate(positions):
        if index > 0:
            emission += math.dist(positions[index - 1], position) / speed_ft_s
        arrivals.append(emission + math.dist(position, receiver) / SOUND_SPEED_FT_S)
    return np.array(arrivals)


def _analysis_points(
    terrain: TerrainResult, track: list[TrackPoint]
) -> list[AnalysisTrackPoint]:
    points = []
    for point in track:
        x_ft, y_ft = lonlat_to_model_ft(terrain, point.lon, point.lat)
        points.append(
            AnalysisTrackPoint(
                time_s=0.0,
                x_ft=x_ft,
                y_ft=y_ft,
                z_msl_ft=point.alt_m * FT_PER_M,
                speed_kn=SPEED_KN,
            )
        )
    return points


def _run_log(
    analysis: list[AnalysisTrackPoint] | None,
    *,
    read_error: str | None = None,
) -> AamRunLog:
    return AamRunLog(
        read_error=read_error,
        declared_analysis_points=len(analysis) if analysis else None,
        analysis_track=tuple(analysis) if analysis is not None else None,
        elevation=None,
        impedance=None,
        raw_text="",
    )
