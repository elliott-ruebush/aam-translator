"""Tests for AEQD CRS and model-space coordinate transforms."""

from __future__ import annotations

from pathlib import Path

import pytest
from pyproj import Transformer

from aam_translator.constants import FT_PER_M
from aam_translator.context import (
    TerrainResult,
    aoi_envelope,
    build_aeqd_crs,
    elv_extent_ft,
    lonlat_to_model_ft,
)
from aam_translator.write_elv import write_elv_from_dem
from dem_fixtures import grid_from_elv_result


def test_build_aeqd_crs_returns_valid_crs(tiny_aoi_geom) -> None:
    crs = build_aeqd_crs(tiny_aoi_geom)
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
    envelope = aoi_envelope(tiny_aoi_geom)
    aeqd_crs = build_aeqd_crs(tiny_aoi_geom)
    elv_path = tmp_path / "scenario.elv"

    result = write_elv_from_dem(
        str(tiny_dem_path),
        str(elv_path),
        aoi_envelope=envelope,
        crs_in="EPSG:4326",
        aeqd_crs=aeqd_crs,
    )
    grid = grid_from_elv_result(result, aeqd_crs)
    spec = result.spec
    terrain = TerrainResult.from_elv_write(
        result,
        aeqd_crs=aeqd_crs,
        elv_path=str(elv_path),
    )

    to_wgs = Transformer.from_crs(aeqd_crs, "EPSG:4326", always_xy=True)
    sw_lon, sw_lat = to_wgs.transform(spec.grid_origin_x_m, spec.grid_origin_y_m)
    ne_lon, ne_lat = to_wgs.transform(grid.grid_extent_x_m, grid.grid_extent_y_m)

    sw_x, sw_y = lonlat_to_model_ft(terrain, sw_lon, sw_lat)
    ne_x, ne_y = lonlat_to_model_ft(terrain, ne_lon, ne_lat)

    expected_x = spec.cell_count_x * spec.cell_dx_m * FT_PER_M
    expected_y = spec.cell_count_y * spec.cell_dy_m * FT_PER_M

    assert sw_x == pytest.approx(0.0, abs=1.0)
    assert sw_y == pytest.approx(0.0, abs=1.0)
    assert ne_x == pytest.approx(expected_x, rel=1e-3)
    assert ne_y == pytest.approx(expected_y, rel=1e-3)

    extent_x, extent_y = elv_extent_ft(terrain)
    assert extent_x == pytest.approx(expected_x, rel=1e-5)
    assert extent_y == pytest.approx(expected_y, rel=1e-5)
