"""Tests for AEQD CRS and model-space coordinate transforms."""

from __future__ import annotations

from pathlib import Path

import pytest
from pyproj import Transformer

from aam_translator.constants import FT_PER_M
from aam_translator.context import (
    TerrainResult,
    aoi_clip_box,
    build_local_crs,
    elv_extent_ft,
    lonlat_to_model_ft,
)
from aam_translator.write_elv import clip_path_for_elv, write_elv_from_dem
from dem_fixtures import grid_from_elv_result


def test_build_local_crs_returns_valid_crs(tiny_aoi_geom) -> None:
    crs = build_local_crs(tiny_aoi_geom)
    assert crs.is_projected
    operation = crs.coordinate_operation
    assert operation is not None
    assert operation.method_name == "Azimuthal Equidistant"
    tf = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    x, y = tf.transform(-177.0, 54.0)
    assert x == pytest.approx(0.0, abs=500_000.0)
    assert y == pytest.approx(0.0, abs=500_000.0)


def test_lonlat_to_model_ft_corners(
    tmp_path: Path, tiny_dem_path, tiny_aoi_geom,
) -> None:
    clip_box = aoi_clip_box(tiny_aoi_geom)
    local_crs = build_local_crs(tiny_aoi_geom)
    elv_path = tmp_path / "scenario.elv"

    result = write_elv_from_dem(
        str(tiny_dem_path),
        str(elv_path),
        clip_box=clip_box,
        crs_in="EPSG:4326",
        local_crs=local_crs,
    )
    grid = grid_from_elv_result(result, local_crs)
    terrain = TerrainResult(
        nx=result.nx,
        ny=result.ny,
        elv_dx_m=result.elv_dx_m,
        elv_dy_m=result.elv_dy_m,
        elv_header_feet=result.elv_header_feet,
        elv_world_minx_m=result.elv_world_minx_m,
        elv_world_miny_m=result.elv_world_miny_m,
        local_crs=local_crs,
        elv_path=str(elv_path),
        clip_tif_path=clip_path_for_elv(str(elv_path)),
    )

    to_wgs = Transformer.from_crs(local_crs, "EPSG:4326", always_xy=True)
    sw_lon, sw_lat = to_wgs.transform(grid.minx_m, grid.miny_m)
    ne_lon, ne_lat = to_wgs.transform(grid.maxx_m, grid.maxy_m)

    sw_x, sw_y = lonlat_to_model_ft(terrain, sw_lon, sw_lat)
    ne_x, ne_y = lonlat_to_model_ft(terrain, ne_lon, ne_lat)

    expected_x = terrain.nx * terrain.elv_dx_m * FT_PER_M
    expected_y = terrain.ny * terrain.elv_dy_m * FT_PER_M

    assert sw_x == pytest.approx(0.0, abs=1.0)
    assert sw_y == pytest.approx(0.0, abs=1.0)
    assert ne_x == pytest.approx(expected_x, rel=1e-3)
    assert ne_y == pytest.approx(expected_y, rel=1e-3)

    extent_x, extent_y = elv_extent_ft(terrain)
    assert extent_x == pytest.approx(expected_x, rel=1e-5)
    assert extent_y == pytest.approx(expected_y, rel=1e-5)
