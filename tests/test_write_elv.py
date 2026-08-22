"""Tests for DEM clipping and NMBGF .ELV writing."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import rasterio
from pyproj import Transformer

from aam_translator.aeqd_grid import aeqd_cell_center, resample_dem_to_aeqd
from aam_translator.constants import FT_PER_M
from aam_translator.context import aoi_envelope, build_aeqd_crs
from aam_translator.nmbgf_io import iter_grid_cells, read_nmbgf_header
from aam_translator.write_elv import clip_path_for_elv, write_elv_from_dem
from dem_fixtures import (
    TRIPLE_LAKES_LAT,
    TRIPLE_LAKES_LON,
    grid_from_elv_result,
    wgs84_box_from_utm_extent,
    write_utm_planar_ramp_dem,
)
from dem_oracle import DemOracle, sample_dem_at_aeqd_point

# Spot checks against the GDAL warp oracle tolerate float32/float64 noise only.
GDAL_ORACLE_TOLERANCE_M = 0.05


def zalt_model_array_m(hdr, cell_count_x: int, cell_count_y: int) -> list[list[float]]:
    values = list(hdr.values)
    out = [[0.0] * cell_count_x for _ in range(cell_count_y)]
    for idx, (col, row) in enumerate(iter_grid_cells(cell_count_x, cell_count_y)):
        row_j = cell_count_y - 1 - row
        out[row_j][col] = values[idx] / FT_PER_M
    return out


def clip_m_at_model_cell(
    clip_data: np.ndarray,
    cell_count_y: int,
    col_i: int,
    row_j: int,
) -> float:
    array_row = cell_count_y - 1 - row_j
    return float(clip_data[array_row, col_i])


def clip_value_at_model_cell(
    clip_path: Path, cell_count_y: int, col_i: int, row_j: int,
) -> float:
    with rasterio.open(clip_path) as clip:
        return clip_m_at_model_cell(clip.read(1), cell_count_y, col_i, row_j)


def test_write_elv_from_dem(tmp_path: Path, tiny_dem_path, tiny_aoi_geom) -> None:
    envelope = aoi_envelope(tiny_aoi_geom)
    aeqd_crs = build_aeqd_crs(tiny_aoi_geom)
    elv_path = tmp_path / "scenario.elv"
    clip_tif = clip_path_for_elv(elv_path)

    result = write_elv_from_dem(
        str(tiny_dem_path),
        str(elv_path),
        aoi_envelope=envelope,
        crs_in="EPSG:4326",
        aeqd_crs=aeqd_crs,
        title="tiny grid",
    )
    spec = result.spec

    assert elv_path.is_file()
    assert Path(clip_tif).is_file()

    hdr = read_nmbgf_header(elv_path)
    assert hdr.units == "FEET"
    assert hdr.xryr == (0.0, 0.0)
    assert (hdr.ni, hdr.nj) == (spec.cell_count_x, spec.cell_count_y)
    assert hdr.di == pytest.approx(30.0 * FT_PER_M, rel=1e-5)
    assert hdr.dj == pytest.approx(30.0 * FT_PER_M, rel=1e-5)

    expected_cells = spec.cell_count_x * spec.cell_count_y
    assert hdr.n_cells == expected_cells
    min_bytes = 16 + expected_cells * 4 + 8
    assert elv_path.stat().st_size >= min_bytes

    with rasterio.open(clip_tif) as clip:
        assert clip.crs == aeqd_crs
        assert clip.width == spec.cell_count_x
        assert clip.height == spec.cell_count_y

    grid = grid_from_elv_result(result, aeqd_crs)
    col_i = min(spec.cell_count_x // 2, spec.cell_count_x - 2)
    row_j = min(spec.cell_count_y // 2, spec.cell_count_y - 2)

    zalt_m = zalt_model_array_m(hdr, spec.cell_count_x, spec.cell_count_y)
    clip_m = clip_value_at_model_cell(Path(clip_tif), spec.cell_count_y, col_i, row_j)
    assert zalt_m[row_j][col_i] == pytest.approx(clip_m, abs=0.01)

    aeqd_x_m, aeqd_y_m = aeqd_cell_center(grid, col_i, row_j)
    expected_m = sample_dem_at_aeqd_point(tiny_dem_path, grid, aeqd_x_m, aeqd_y_m)
    assert not np.isnan(expected_m)
    assert clip_m == pytest.approx(expected_m, abs=GDAL_ORACLE_TOLERANCE_M)


def test_write_elv_clip_matches_zalt_payload(
    tmp_path: Path, tiny_dem_path, tiny_aoi_geom
) -> None:
    """Every ZALT value equals scenario_clip.tif × FT_PER_M in writer cell order."""
    envelope = aoi_envelope(tiny_aoi_geom)
    aeqd_crs = build_aeqd_crs(tiny_aoi_geom)
    elv_path = tmp_path / "scenario.elv"
    clip_tif = clip_path_for_elv(elv_path)

    result = write_elv_from_dem(
        str(tiny_dem_path),
        str(elv_path),
        aoi_envelope=envelope,
        crs_in="EPSG:4326",
        aeqd_crs=aeqd_crs,
    )
    spec = result.spec

    hdr = read_nmbgf_header(elv_path)
    assert hdr.data_tag == "ZALT"
    assert len(hdr.values) == spec.cell_count_x * spec.cell_count_y

    with rasterio.open(clip_tif) as clip:
        clip_data = clip.read(1)

    cells = iter_grid_cells(spec.cell_count_x, spec.cell_count_y)
    for idx, (col, row) in enumerate(cells):
        clip_ft = float(clip_data[row, col]) * FT_PER_M
        assert hdr.values[idx] == pytest.approx(clip_ft, rel=1e-5)


def test_write_elv_raises_when_aoi_exceeds_dem(
    tmp_path: Path, tiny_dem_path, tiny_aoi_geom,
) -> None:
    envelope = aoi_envelope(tiny_aoi_geom)
    aeqd_crs = build_aeqd_crs(tiny_aoi_geom)
    oversized = envelope.buffer(0.05)  # ~5 km in degrees; tiny DEM is ~120 m across
    with pytest.raises(ValueError, match="extends beyond parent DEM"):
        write_elv_from_dem(
            str(tiny_dem_path),
            tmp_path / "scenario.elv",
            aoi_envelope=oversized,
            crs_in="EPSG:4326",
            aeqd_crs=aeqd_crs,
        )


def test_write_elv_coregisters_with_parent_dem_at_high_latitude(tmp_path: Path) -> None:
    """Large enough AOI that copying UTM pixels as AEQD would fail by meters."""
    width_m, height_m, res_m = 9000.0, 4000.0, 30.0
    dem_path = tmp_path / "trl_ramp.tif"
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
    elv_path = tmp_path / "scenario.elv"
    clip_tif = clip_path_for_elv(elv_path)

    result = write_elv_from_dem(
        dem_path,
        elv_path,
        aoi_envelope=aoi,
        crs_in="EPSG:4326",
        aeqd_crs=aeqd_crs,
    )
    spec = result.spec

    hdr = read_nmbgf_header(elv_path)
    grid = grid_from_elv_result(result, aeqd_crs)
    zalt_m = zalt_model_array_m(hdr, spec.cell_count_x, spec.cell_count_y)

    with rasterio.open(clip_tif) as clip:
        assert clip.crs == aeqd_crs
        assert clip.width == spec.cell_count_x
        assert clip.height == spec.cell_count_y
        clip_data = clip.read(1)

    parent_on_grid = resample_dem_to_aeqd(dem_path, grid)

    max_err = 0.0
    compared = 0
    for row_j in range(1, spec.cell_count_y - 1):
        for col_i in range(1, spec.cell_count_x - 1):
            clip_m = clip_m_at_model_cell(clip_data, spec.cell_count_y, col_i, row_j)
            assert zalt_m[row_j][col_i] == pytest.approx(clip_m, abs=0.01)

            array_row = spec.cell_count_y - 1 - row_j
            expected = float(parent_on_grid[array_row, col_i])
            if np.isnan(expected):
                continue
            err = abs(clip_m - expected)
            max_err = max(max_err, err)
            compared += 1
            assert err < 1.0

    assert compared > 100
    assert max_err < 1.0

    # The old UTM-copy path indexed pixels as if they sat on an AEQD lattice aligned
    # with the UTM grid. At this latitude that misplaces samples by >10 m horizontally.
    col_i, row_j = spec.cell_count_x // 2, spec.cell_count_y // 2
    aeqd_x_m, aeqd_y_m = aeqd_cell_center(grid, col_i, row_j)
    with DemOracle(dem_path) as oracle:
        expected = oracle.sample(grid, aeqd_x_m, aeqd_y_m)
        assert not np.isnan(expected)

        with rasterio.open(dem_path) as src:
            res = abs(src.transform.a)
            utm_to_aeqd = Transformer.from_crs(src.crs, aeqd_crs, always_xy=True)
            legacy_x_m, legacy_y_m = utm_to_aeqd.transform(
                src.bounds.left + (col_i + 0.5) * res,
                src.bounds.bottom + (row_j + 0.5) * res,
            )
        horiz_m = math.hypot(aeqd_x_m - legacy_x_m, aeqd_y_m - legacy_y_m)
        assert horiz_m > 10.0
        assert abs(expected - oracle.sample(grid, legacy_x_m, legacy_y_m)) > 2.0
