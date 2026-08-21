"""Tests for AEQD lattice construction and DEM resampling."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from pyproj import Transformer

from aam_translator.aeqd_grid import (
    aeqd_cell_center,
    build_aeqd_grid,
    resample_dem_to_aeqd,
)
from aam_translator.context import build_aeqd_crs
from dem_fixtures import (
    TRIPLE_LAKES_LAT,
    TRIPLE_LAKES_LON,
    wgs84_box_from_utm_extent,
    write_utm_planar_ramp_dem,
)
from dem_oracle import DemOracle

GDAL_ORACLE_TOLERANCE_M = 0.05


def test_build_aeqd_grid_covers_rotated_utm_extent(tmp_path: Path) -> None:
    width_m, height_m, res_m = 9000.0, 4000.0, 30.0
    dem_path = tmp_path / "trl_dem.tif"
    write_utm_planar_ramp_dem(
        dem_path,
        center_lon=TRIPLE_LAKES_LON,
        center_lat=TRIPLE_LAKES_LAT,
        width_m=width_m,
        height_m=height_m,
        res_m=res_m,
    )
    aoi = wgs84_box_from_utm_extent(
        center_lon=TRIPLE_LAKES_LON,
        center_lat=TRIPLE_LAKES_LAT,
        width_m=width_m,
        height_m=height_m,
    )
    aeqd_crs = build_aeqd_crs(aoi)
    grid = build_aeqd_grid(aoi, aeqd_crs, res_m, dem_path=dem_path)
    spec = grid.spec

    assert spec.cell_count_x * spec.cell_dx_m >= width_m - res_m
    assert spec.cell_count_y * spec.cell_dy_m >= height_m - res_m

    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32606", always_xy=True)
    utm_to_aeqd = Transformer.from_crs("EPSG:32606", aeqd_crs, always_xy=True)
    cx, cy = to_utm.transform(TRIPLE_LAKES_LON, TRIPLE_LAKES_LAT)
    utm_corners = [
        (cx - width_m / 2, cy - height_m / 2),
        (cx + width_m / 2, cy - height_m / 2),
        (cx + width_m / 2, cy + height_m / 2),
        (cx - width_m / 2, cy + height_m / 2),
    ]
    aeqd_corners = [utm_to_aeqd.transform(x, y) for x, y in utm_corners]
    xs = [p[0] for p in aeqd_corners]
    ys = [p[1] for p in aeqd_corners]

    fake_ne = (spec.grid_origin_x_m + width_m, spec.grid_origin_y_m + height_m)
    true_ne = (max(xs), max(ys))
    offset_m = math.hypot(true_ne[0] - fake_ne[0], true_ne[1] - fake_ne[1])
    assert offset_m > 200.0

    assert spec.grid_origin_x_m <= min(xs) + 1.0
    assert spec.grid_origin_y_m <= min(ys) + 1.0
    assert grid.grid_extent_x_m >= max(xs) - 1.0
    assert grid.grid_extent_y_m >= max(ys) - 1.0


def test_resample_matches_independent_sample(tmp_path: Path) -> None:
    width_m, height_m, res_m = 3000.0, 3000.0, 30.0
    dem_path = tmp_path / "ramp.tif"
    write_utm_planar_ramp_dem(
        dem_path,
        center_lon=TRIPLE_LAKES_LON,
        center_lat=TRIPLE_LAKES_LAT,
        width_m=width_m,
        height_m=height_m,
        res_m=res_m,
        slope_e=0.2,
        slope_n=0.2,
    )
    aoi = wgs84_box_from_utm_extent(
        center_lon=TRIPLE_LAKES_LON,
        center_lat=TRIPLE_LAKES_LAT,
        width_m=width_m,
        height_m=height_m,
    )
    aeqd_crs = build_aeqd_crs(aoi)
    grid = build_aeqd_grid(aoi, aeqd_crs, res_m, dem_path=dem_path)
    spec = grid.spec
    warped = resample_dem_to_aeqd(dem_path, grid)

    with DemOracle(dem_path) as oracle:
        for row_j in (1, spec.cell_count_y // 2, spec.cell_count_y - 2):
            for col_i in (1, spec.cell_count_x // 2, spec.cell_count_x - 2):
                aeqd_x_m, aeqd_y_m = aeqd_cell_center(grid, col_i, row_j)
                expected = oracle.sample(grid, aeqd_x_m, aeqd_y_m)
                if np.isnan(expected):
                    continue
                array_row = spec.cell_count_y - 1 - row_j
                actual = float(warped[array_row, col_i])
                assert actual == pytest.approx(expected, abs=GDAL_ORACLE_TOLERANCE_M)
