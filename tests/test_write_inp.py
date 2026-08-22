"""Tests for single-event ``.INP`` file writing."""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from aam_translator.constants import (
    DEFAULT_MODEL_CELL_FT,
    FT_PER_M,
    FT_S_PER_KN,
    MAX_POI_POINTS,
    MAX_TRACK_POINTS,
)
from aam_translator.context import (
    TerrainResult,
    aoi_envelope,
    build_aeqd_crs,
    elv_extent_ft,
    lonlat_to_model_ft,
)
from aam_translator.write_elv import write_elv_from_dem
from aam_translator.write_imp import ImpGridContext, write_imp_for_elv_grid
from aam_translator.write_inp import (
    PoiPoint,
    TrackPoint,
    hop_speed_kn,
    setup_para_block,
    write_inp,
)


@pytest.fixture
def terrain(tmp_path: Path, tiny_dem_path, tiny_aoi_geom) -> TerrainResult:
    return _build_terrain(tmp_path, tiny_dem_path, tiny_aoi_geom)


def test_write_inp_keywords_present(terrain: TerrainResult, tmp_path: Path) -> None:
    inp_path = tmp_path / "scenario.inp"
    write_inp(
        terrain,
        inp_path,
        track=[TrackPoint(-177.0, 54.1485, 500.0)],
        pois=[PoiPoint("Receiver", -177.0, 54.1485, 1.6)],
        source_id="OMNI",
    )
    text = inp_path.read_text()
    for keyword in ("COMPUTEPOI", "TERRAIN", "SETUP PARA", "ONE TRACK", "POI", "END"):
        assert keyword in text


def test_write_inp_terrain_basenames(terrain: TerrainResult, tmp_path: Path) -> None:
    inp_path = tmp_path / "scenario.inp"
    write_inp(
        terrain,
        inp_path,
        track=[TrackPoint(-177.0, 54.1485, 500.0)],
        pois=[PoiPoint("Receiver", -177.0, 54.1485, 1.6)],
        source_id="OMNI",
    )
    lines = inp_path.read_text().splitlines()
    terrain_idx = lines.index("TERRAIN")
    assert lines[terrain_idx + 1] == "scenario.elv"
    assert lines[terrain_idx + 2] == "scenario.imp"


def test_setup_para_ur_corner_inside_elv_extent(terrain: TerrainResult) -> None:
    block = setup_para_block(terrain)
    lines = block.splitlines()
    assert lines[0] == "SETUP PARA"
    ur_line = lines[3]
    assert re.fullmatch(r"\s*\d+\.\d{4}\s*\d+\.\d{4}", ur_line)

    xmax = float(ur_line[:14])
    ymax = float(ur_line[14:28])
    elv_x, elv_y = elv_extent_ft(terrain)
    assert xmax <= elv_x
    assert ymax <= elv_y
    assert xmax == pytest.approx(
        math.floor(elv_x / DEFAULT_MODEL_CELL_FT) * DEFAULT_MODEL_CELL_FT,
    )
    assert ymax == pytest.approx(
        math.floor(elv_y / DEFAULT_MODEL_CELL_FT) * DEFAULT_MODEL_CELL_FT,
    )


def test_write_inp_track_and_poi_coordinates(
    terrain: TerrainResult, tmp_path: Path,
) -> None:
    track_lon, track_lat = -177.0001, 54.1485
    poi_lon, poi_lat = -176.9995, 54.1488
    alt_m = 123.456
    agl_m = 1.6

    inp_path = tmp_path / "scenario.inp"
    write_inp(
        terrain,
        inp_path,
        track=[TrackPoint(track_lon, track_lat, alt_m)],
        pois=[PoiPoint("Receiver", poi_lon, poi_lat, agl_m)],
        source_id="OMNI",
        speed_kn=42.0,
        heading_deg=270.0,
    )

    expected_tx, expected_ty = lonlat_to_model_ft(terrain, track_lon, track_lat)
    expected_px, expected_py = lonlat_to_model_ft(terrain, poi_lon, poi_lat)
    expected_alt_ft = alt_m * FT_PER_M
    expected_agl_ft = agl_m * FT_PER_M

    lines = inp_path.read_text().splitlines()
    track_idx = lines.index("ONE TRACK")
    track_row = lines[track_idx + 3]
    poi_idx = lines.index("POI")
    poi_row = lines[poi_idx + 2]

    assert float(track_row[0:12]) == pytest.approx(expected_tx, abs=0.01)
    assert float(track_row[12:24]) == pytest.approx(expected_ty, abs=0.01)
    assert float(track_row[24:34]) == pytest.approx(expected_alt_ft, abs=0.05)
    assert "     42.0" in track_row
    assert track_row.rstrip().endswith("270.")

    assert poi_row.startswith("Receiver    ")
    assert float(poi_row[12:24]) == pytest.approx(expected_px, abs=0.01)
    assert float(poi_row[24:36]) == pytest.approx(expected_py, abs=0.01)
    assert float(poi_row[36:44]) == pytest.approx(expected_agl_ft, abs=0.01)


def test_write_inp_track_altitude_no_pad(
    terrain: TerrainResult, tmp_path: Path,
) -> None:
    alt_m = 321.987
    inp_path = tmp_path / "scenario.inp"
    write_inp(
        terrain,
        inp_path,
        track=[TrackPoint(-177.0, 54.1485, alt_m)],
        pois=[PoiPoint("Receiver", -177.0, 54.1485, 1.6)],
        source_id="OMNI",
    )
    lines = inp_path.read_text().splitlines()
    track_idx = lines.index("ONE TRACK")
    track_row = lines[track_idx + 3]
    alt_ft = float(track_row[24:34])
    assert alt_ft == pytest.approx(alt_m * FT_PER_M, abs=0.05)
    assert alt_ft != pytest.approx(alt_m * FT_PER_M + 500.0, abs=1.0)


def test_write_inp_returns_path_and_creates_file(
    terrain: TerrainResult,
    tmp_path: Path,
) -> None:
    inp_path = tmp_path / "out" / "scenario.inp"
    returned = write_inp(
        terrain,
        inp_path,
        track=[TrackPoint(-177.0, 54.1485, 500.0)],
        pois=[PoiPoint("Receiver", -177.0, 54.1485, 1.6)],
        source_id="OMNI",
    )
    assert returned == str(inp_path)
    assert inp_path.is_file()


def test_write_inp_rejects_empty_track(terrain: TerrainResult, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="track must contain at least one point"):
        write_inp(
            terrain,
            tmp_path / "scenario.inp",
            track=[],
            pois=[PoiPoint("Receiver", -177.0, 54.1485, 1.6)],
            source_id="OMNI",
        )


def test_write_inp_rejects_empty_pois(terrain: TerrainResult, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="pois must contain at least one point"):
        write_inp(
            terrain,
            tmp_path / "scenario.inp",
            track=[TrackPoint(-177.0, 54.1485, 500.0)],
            pois=[],
            source_id="OMNI",
        )


def test_write_inp_rejects_track_over_max_points(
    terrain: TerrainResult, tmp_path: Path,
) -> None:
    point = TrackPoint(-177.0, 54.1485, 500.0)
    track = [point] * (MAX_TRACK_POINTS + 1)
    with pytest.raises(
        ValueError,
        match=(
            rf"track has {MAX_TRACK_POINTS + 1} points; AAM 3\.0\.0 accepts at most "
            rf"{MAX_TRACK_POINTS} and fails with exit code 0 beyond that"
        ),
    ):
        write_inp(
            terrain,
            tmp_path / "scenario.inp",
            track=track,
            pois=[PoiPoint("Receiver", -177.0, 54.1485, 1.6)],
            source_id="OMNI",
        )
    assert not (tmp_path / "scenario.inp").exists()


def test_write_inp_rejects_pois_over_max_points(
    terrain: TerrainResult, tmp_path: Path,
) -> None:
    poi = PoiPoint("Receiver", -177.0, 54.1485, 1.6)
    pois = [poi] * (MAX_POI_POINTS + 1)
    with pytest.raises(
        ValueError,
        match=(
            rf"pois has {MAX_POI_POINTS + 1} points; AAM accepts at most "
            rf"{MAX_POI_POINTS}"
        ),
    ):
        write_inp(
            terrain,
            tmp_path / "scenario.inp",
            track=[TrackPoint(-177.0, 54.1485, 500.0)],
            pois=pois,
            source_id="OMNI",
        )


def test_write_inp_rejects_multi_point_track_with_zero_speed(
    terrain: TerrainResult, tmp_path: Path,
) -> None:
    track = [
        TrackPoint(-177.0, 54.1485, 500.0),
        TrackPoint(-177.0001, 54.1485, 500.0),
    ]
    with pytest.raises(ValueError, match="effective speed 0"):
        write_inp(
            terrain,
            tmp_path / "scenario.inp",
            track=track,
            pois=[PoiPoint("Receiver", -177.0, 54.1485, 1.6)],
            source_id="OMNI",
        )


def test_write_inp_accepts_multi_point_track_with_positive_speed(
    terrain: TerrainResult, tmp_path: Path,
) -> None:
    track = [
        TrackPoint(-177.0, 54.1485, 500.0),
        TrackPoint(-177.0001, 54.1485, 500.0),
    ]
    inp_path = tmp_path / "scenario.inp"
    write_inp(
        terrain,
        inp_path,
        track=track,
        pois=[PoiPoint("Receiver", -177.0, 54.1485, 1.6)],
        source_id="OMNI",
        speed_kn=100.0,
    )
    assert inp_path.is_file()


def test_write_inp_rejects_per_point_zero_speed_override(
    terrain: TerrainResult, tmp_path: Path,
) -> None:
    track = [
        TrackPoint(-177.0, 54.1485, 500.0, speed_kn=100.0),
        TrackPoint(-177.0001, 54.1485, 500.0, speed_kn=0.0),
    ]
    with pytest.raises(ValueError, match="track point 1 has effective speed 0"):
        write_inp(
            terrain,
            tmp_path / "scenario.inp",
            track=track,
            pois=[PoiPoint("Receiver", -177.0, 54.1485, 1.6)],
            source_id="OMNI",
            speed_kn=100.0,
        )


def test_write_inp_single_point_track_allows_zero_speed(
    terrain: TerrainResult, tmp_path: Path,
) -> None:
    inp_path = tmp_path / "scenario.inp"
    write_inp(
        terrain,
        inp_path,
        track=[TrackPoint(-177.0, 54.1485, 500.0)],
        pois=[PoiPoint("Receiver", -177.0, 54.1485, 1.6)],
        source_id="OMNI",
        speed_kn=0.0,
    )
    assert inp_path.is_file()


def test_write_inp_per_point_speed_and_heading_overrides(
    terrain: TerrainResult, tmp_path: Path,
) -> None:
    track = [
        TrackPoint(-177.0, 54.1485, 500.0, speed_kn=55.0, heading_deg=180.0),
        TrackPoint(-177.0001, 54.1485, 500.0),
    ]
    inp_path = tmp_path / "scenario.inp"
    write_inp(
        terrain,
        inp_path,
        track=track,
        pois=[PoiPoint("Receiver", -177.0, 54.1485, 1.6)],
        source_id="OMNI",
        speed_kn=42.0,
        heading_deg=270.0,
    )

    lines = inp_path.read_text().splitlines()
    track_idx = lines.index("ONE TRACK")
    first_row = lines[track_idx + 3]
    second_row = lines[track_idx + 4]

    assert "     55.0" in first_row
    assert first_row.rstrip().endswith("180.")
    assert "     42.0" in second_row
    assert second_row.rstrip().endswith("270.")


def test_hop_speed_kn_for_known_segment(terrain: TerrainResult) -> None:
    segment_ft = 9841.19
    alt_delta_m = segment_ft / FT_PER_M
    track = [
        TrackPoint(-177.0, 54.1485, 0.0),
        TrackPoint(-177.0, 54.1485, alt_delta_m),
    ]
    expected = segment_ft / (1.0 * FT_S_PER_KN)
    assert hop_speed_kn(track, terrain, hop_s=1.0) == pytest.approx(expected, rel=1e-4)
    assert expected == pytest.approx(5830.7, rel=1e-3)


def test_hop_speed_kn_rejects_single_point_track(terrain: TerrainResult) -> None:
    with pytest.raises(ValueError, match="track must contain at least two points"):
        hop_speed_kn([TrackPoint(-177.0, 54.1485, 500.0)], terrain)


def test_hop_speed_kn_rejects_non_positive_hop_s(terrain: TerrainResult) -> None:
    track = [
        TrackPoint(-177.0, 54.1485, 500.0),
        TrackPoint(-177.0001, 54.1485, 500.0),
    ]
    with pytest.raises(ValueError, match="hop_s must be positive, got 0"):
        hop_speed_kn(track, terrain, hop_s=0.0)


def _build_terrain(tmp_path: Path, tiny_dem_path, tiny_aoi_geom) -> TerrainResult:
    envelope = aoi_envelope(tiny_aoi_geom)
    aeqd_crs = build_aeqd_crs(tiny_aoi_geom)
    elv_path = tmp_path / "scenario.elv"
    imp_path = tmp_path / "scenario.imp"

    elv_result = write_elv_from_dem(
        str(tiny_dem_path),
        str(elv_path),
        aoi_envelope=envelope,
        crs_in="EPSG:4326",
        aeqd_crs=aeqd_crs,
    )
    write_imp_for_elv_grid(
        str(imp_path),
        grid=ImpGridContext.from_elv_write(elv_result),
    )

    return TerrainResult.from_elv_write(
        elv_result,
        aeqd_crs=aeqd_crs,
        elv_path=str(elv_path),
        imp_path=str(imp_path),
    )
