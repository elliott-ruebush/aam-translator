"""Integration tests for write_terrain and write_aam_inputs."""

from __future__ import annotations

from pathlib import Path

import pytest

from aam_translator import write_aam_inputs, write_inp, write_terrain
from aam_translator.nmbgf_io import read_nmbgf_header
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
