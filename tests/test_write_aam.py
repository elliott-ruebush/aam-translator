"""Integration tests for write_terrain and write_aam_inputs."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import rasterio
from pyproj import Transformer

from aam_translator import load_terrain, write_aam_inputs, write_inp, write_terrain
from aam_translator.constants import FT_PER_M
from aam_translator.context import aoi_envelope, build_aeqd_crs, elv_extent_ft, lonlat_to_model_ft
from aam_translator.grid_spec import GridSpec
from aam_translator.nmbgf_io import read_nmbgf_header
from aam_translator.write_elv import clip_path_for_elv, write_elv_from_dem
from aam_translator.write_inp import PoiPoint, TrackPoint


def test_write_terrain_writes_elv_imp_and_clip(
    tmp_path: Path,
    tiny_dem_path,
    tiny_aoi_geom,
) -> None:
    terrain = write_terrain(str(tiny_dem_path), tiny_aoi_geom, tmp_path)

    assert Path(terrain.elv_path).is_file()
    assert terrain.imp_path is not None
    assert terrain.clip_tif_path is not None
    assert Path(terrain.imp_path).is_file()
    assert Path(terrain.clip_tif_path).is_file()

    elv_hdr = read_nmbgf_header(terrain.elv_path)
    imp_hdr = read_nmbgf_header(terrain.imp_path)
    assert (elv_hdr.ni, elv_hdr.nj) == (imp_hdr.ni, imp_hdr.nj)
    assert elv_hdr.units == "FEET"
    assert imp_hdr.units == "FEET"
    assert elv_hdr.xryr == (0.0, 0.0)
    assert imp_hdr.xryr == (0.0, 0.0)


def test_write_aam_inputs_writes_all_three_files(
    tmp_path: Path,
    tiny_dem_path,
    tiny_aoi_geom,
) -> None:
    track = [TrackPoint(-177.0, 54.1485, 500.0)]
    pois = [PoiPoint("Receiver", -177.0, 54.1485, 1.6)]

    result = write_aam_inputs(
        str(tiny_dem_path),
        tiny_aoi_geom,
        tmp_path,
        track=track,
        pois=pois,
        source_id="OMNI",
    )

    assert Path(result.terrain.elv_path).is_file()
    assert result.terrain.imp_path is not None
    assert Path(result.terrain.imp_path).is_file()
    assert Path(result.inp_path).is_file()
    assert "COMPUTEPOI" in Path(result.inp_path).read_text()


def test_write_inp_without_rewriting_terrain(
    tmp_path: Path,
    tiny_dem_path,
    tiny_aoi_geom,
) -> None:
    terrain = write_terrain(str(tiny_dem_path), tiny_aoi_geom, tmp_path)
    elv_mtime = Path(terrain.elv_path).stat().st_mtime

    inp_path = tmp_path / "regen.inp"
    write_inp(
        terrain,
        inp_path,
        track=[TrackPoint(-177.0, 54.1485, 400.0)],
        pois=[PoiPoint("Receiver", -177.0, 54.1485, 1.6)],
        source_id="OMNI",
    )

    assert inp_path.is_file()
    assert Path(terrain.elv_path).stat().st_mtime == pytest.approx(elv_mtime, abs=0.001)


def _spec_from_clip(clip_tif_path: str) -> GridSpec:
    with rasterio.open(clip_tif_path) as clip:
        return GridSpec.from_north_up_transform(
            clip.transform, clip.width, clip.height,
        )


def test_load_terrain_round_trip(
    tmp_path: Path,
    tiny_dem_path,
    tiny_aoi_geom,
) -> None:
    written = write_terrain(
        str(tiny_dem_path),
        tiny_aoi_geom,
        tmp_path,
        grid_agl_ft=12.0,
        model_cell_ft=150.0,
        cutoff_ft=50000.0,
        flow_resistivity=175.0,
    )
    loaded = load_terrain(
        written.elv_path,
        imp_path=written.imp_path,
        grid_agl_ft=written.grid_agl_ft,
        model_cell_ft=written.model_cell_ft,
        cutoff_ft=written.cutoff_ft,
    )

    clip_spec = _spec_from_clip(written.clip_tif_path)
    assert loaded.spec.cell_count_x == clip_spec.cell_count_x
    assert loaded.spec.cell_count_y == clip_spec.cell_count_y
    assert loaded.spec.cell_dx_m == pytest.approx(clip_spec.cell_dx_m)
    assert loaded.spec.cell_dy_m == pytest.approx(clip_spec.cell_dy_m)
    assert loaded.spec.grid_origin_x_m == pytest.approx(clip_spec.grid_origin_x_m)
    assert loaded.spec.grid_origin_y_m == pytest.approx(clip_spec.grid_origin_y_m)

    assert loaded.aeqd_crs.equals(written.aeqd_crs)
    assert loaded.elv_header_feet is True
    assert loaded.elv_path == written.elv_path
    assert loaded.imp_path == written.imp_path
    assert loaded.clip_tif_path == written.clip_tif_path
    assert loaded.grid_agl_ft == written.grid_agl_ft
    assert loaded.model_cell_ft == written.model_cell_ft
    assert loaded.cutoff_ft == written.cutoff_ft
    assert loaded.flow_resistivity == pytest.approx(written.flow_resistivity)


def test_load_terrain_lonlat_to_model_ft(
    tmp_path: Path,
    tiny_dem_path,
    tiny_aoi_geom,
) -> None:
    written = write_terrain(str(tiny_dem_path), tiny_aoi_geom, tmp_path)
    loaded = load_terrain(written.elv_path, imp_path=written.imp_path)

    spec = loaded.spec
    to_wgs = Transformer.from_crs(loaded.aeqd_crs, "EPSG:4326", always_xy=True)
    sw_lon, sw_lat = to_wgs.transform(spec.grid_origin_x_m, spec.grid_origin_y_m)
    ne_lon, ne_lat = to_wgs.transform(spec.grid_extent_x_m, spec.grid_extent_y_m)

    sw_x, sw_y = lonlat_to_model_ft(loaded, sw_lon, sw_lat)
    ne_x, ne_y = lonlat_to_model_ft(loaded, ne_lon, ne_lat)

    expected_x = spec.cell_count_x * spec.cell_dx_m * FT_PER_M
    expected_y = spec.cell_count_y * spec.cell_dy_m * FT_PER_M

    assert sw_x == pytest.approx(0.0, abs=1.0)
    assert sw_y == pytest.approx(0.0, abs=1.0)
    assert ne_x == pytest.approx(expected_x, rel=1e-3)
    assert ne_y == pytest.approx(expected_y, rel=1e-3)

    extent_x, extent_y = elv_extent_ft(loaded)
    assert extent_x == pytest.approx(expected_x, rel=1e-5)
    assert extent_y == pytest.approx(expected_y, rel=1e-5)


def test_load_terrain_elv_and_clip_only(
    tmp_path: Path,
    tiny_dem_path,
    tiny_aoi_geom,
) -> None:
    envelope = aoi_envelope(tiny_aoi_geom)
    aeqd_crs = build_aeqd_crs(tiny_aoi_geom)
    elv_path = tmp_path / "scenario.elv"
    write_elv_from_dem(
        str(tiny_dem_path),
        str(elv_path),
        aoi_envelope=envelope,
        crs_in="EPSG:4326",
        aeqd_crs=aeqd_crs,
    )

    loaded = load_terrain(elv_path)
    assert loaded.imp_path is None
    assert loaded.clip_tif_path == clip_path_for_elv(elv_path)
    model_x, model_y = lonlat_to_model_ft(loaded, -177.0, 54.1485)
    assert math.isfinite(model_x)
    assert math.isfinite(model_y)


def test_load_terrain_missing_elv(tmp_path: Path) -> None:
    missing = tmp_path / "missing.elv"
    with pytest.raises(FileNotFoundError, match=str(missing)):
        load_terrain(missing)


def test_load_terrain_missing_clip(
    tmp_path: Path,
    tiny_dem_path,
    tiny_aoi_geom,
) -> None:
    written = write_terrain(str(tiny_dem_path), tiny_aoi_geom, tmp_path)
    Path(written.clip_tif_path).unlink()

    with pytest.raises(FileNotFoundError, match=written.clip_tif_path):
        load_terrain(written.elv_path)


def test_load_terrain_rejects_non_aeqd_clip(
    tmp_path: Path,
    tiny_dem_path,
    tiny_aoi_geom,
) -> None:
    written = write_terrain(str(tiny_dem_path), tiny_aoi_geom, tmp_path)
    bad_clip = tmp_path / "bad_clip.tif"

    with rasterio.open(written.clip_tif_path) as src:
        data = src.read()
        profile = src.profile.copy()
        profile["crs"] = "EPSG:32607"
        with rasterio.open(bad_clip, "w", **profile) as dst:
            dst.write(data)

    with pytest.raises(ValueError, match="AEQD"):
        load_terrain(written.elv_path, clip_tif_path=bad_clip)


def test_load_terrain_to_feet_false(
    tmp_path: Path,
    tiny_dem_path,
    tiny_aoi_geom,
) -> None:
    envelope = aoi_envelope(tiny_aoi_geom)
    aeqd_crs = build_aeqd_crs(tiny_aoi_geom)
    elv_path = tmp_path / "metric.elv"
    write_elv_from_dem(
        str(tiny_dem_path),
        str(elv_path),
        aoi_envelope=envelope,
        crs_in="EPSG:4326",
        aeqd_crs=aeqd_crs,
        to_feet=False,
    )

    loaded = load_terrain(elv_path)
    assert loaded.elv_header_feet is False
    hdr = read_nmbgf_header(elv_path)
    assert hdr.units == "METR"
