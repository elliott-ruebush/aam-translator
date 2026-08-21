"""Tests for DEM clipping and NMBGF .ELV writing."""

from __future__ import annotations

from pathlib import Path

import pytest
import rasterio

from aam_translator.constants import FT_PER_M
from aam_translator.context import aoi_clip_box, build_local_crs
from aam_translator.nmbgf_io import read_nmbgf_header
from aam_translator.write_elv import clip_path_for_elv, write_elv_from_dem


def test_write_elv_from_dem(tmp_path: Path, tiny_dem_path, tiny_aoi_geom) -> None:
    clip_box = aoi_clip_box(tiny_aoi_geom)
    local_crs = build_local_crs(tiny_aoi_geom)
    elv_path = tmp_path / "scenario.elv"
    clip_tif = clip_path_for_elv(str(elv_path))

    result = write_elv_from_dem(
        str(tiny_dem_path),
        str(elv_path),
        clip_box=clip_box,
        crs_in="EPSG:4326",
        local_crs=local_crs,
        title="tiny grid",
    )

    assert elv_path.is_file()
    assert Path(clip_tif).is_file()

    hdr = read_nmbgf_header(elv_path)
    assert hdr.units == "FEET"
    assert hdr.xryr == (0.0, 0.0)
    assert (hdr.ni, hdr.nj) == (result.nx, result.ny)
    assert hdr.di == pytest.approx(30.0 * FT_PER_M, rel=1e-5)
    assert hdr.dj == pytest.approx(30.0 * FT_PER_M, rel=1e-5)

    expected_cells = result.nx * result.ny
    assert hdr.n_cells == expected_cells
    min_bytes = 16 + expected_cells * 4 + 8
    assert elv_path.stat().st_size >= min_bytes

    with rasterio.open(str(tiny_dem_path)) as src:
        height = src.height
        sw_elev_m = float(src.read(1)[height - 1, 0])

    assert hdr.first_value == pytest.approx(sw_elev_m * FT_PER_M, rel=1e-5)
