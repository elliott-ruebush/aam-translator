"""Tests for COMPUTEPOI ``.INP`` deck writing."""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from aam_translator.constants import DEFAULT_MODEL_CELL_FT, FT_PER_M
from aam_translator.context import (
    TerrainResult,
    aoi_clip_box,
    build_local_crs,
    elv_extent_ft,
    lonlat_to_model_ft,
)
from aam_translator.write_elv import clip_path_for_elv, write_elv_from_dem
from aam_translator.write_imp import ImpGridContext, write_imp_for_elv_grid
from aam_translator.write_inp import PoiPoint, TrackPoint, setup_para_block, write_inp


def _build_terrain(tmp_path: Path, tiny_dem_path, tiny_aoi_geom) -> TerrainResult:
    clip_box = aoi_clip_box(tiny_aoi_geom)
    local_crs = build_local_crs(tiny_aoi_geom)
    elv_path = tmp_path / "scenario.elv"
    imp_path = tmp_path / "scenario.imp"

    elv_result = write_elv_from_dem(
        str(tiny_dem_path),
        str(elv_path),
        clip_box=clip_box,
        crs_in="EPSG:4326",
        local_crs=local_crs,
    )
    write_imp_for_elv_grid(
        str(imp_path),
        grid=ImpGridContext(
            width=elv_result.nx,
            height=elv_result.ny,
            dx_m=elv_result.elv_dx_m,
            dy_m=elv_result.elv_dy_m,
        ),
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


def test_write_inp_track_and_poi_coordinates(terrain: TerrainResult, tmp_path: Path) -> None:
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


def test_write_inp_track_altitude_no_pad(terrain: TerrainResult, tmp_path: Path) -> None:
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
