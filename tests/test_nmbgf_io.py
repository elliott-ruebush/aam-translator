"""Unit tests for NMBGF binary header and payload I/O."""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest

from aam_translator.constants import DEFAULT_FLOW_RESISTIVITY, FT_PER_M, NMBGF_XRYR
from aam_translator.nmbgf_io import (
    NmbgfGridSpec,
    iter_grid_cells,
    read_nmbgf_grid,
    read_nmbgf_header,
    write_nmbgf_case_header,
    write_nmbgf_end,
    write_nmbgf_metric_header,
    write_nmbgf_title,
)
from aam_translator.write_elv import ElvGridSpec, write_nmbgf_elv_file
from aam_translator.write_imp import write_nmbgf_imp_file
from nmbgf_helpers import pack_nmbgf_test_payload

_TITLE_PREFIX = b"TITL\x04\x00\x00\x00GridVers\x01\x00\x00\x00\x00\x00\x00\x00"
_SPEC = NmbgfGridSpec(
    width=2,
    height=3,
    dx_out=300.0,
    dy_out=150.0,
    units_tag=b"FEET",
)
_ZALT = (10.0, 20.5, 30.0, 40.25, 50.0, 60.0)


def test_title_prefix_bytes(tmp_path: Path) -> None:
    path = tmp_path / "title.bin"
    with path.open("wb") as fp:
        write_nmbgf_title(fp)
    assert path.read_bytes() == _TITLE_PREFIX


def test_case_title_padded_to_20(tmp_path: Path) -> None:
    path = tmp_path / "title.elv"
    _write_nmbgf(
        path,
        title="short",
        spec=_SPEC,
        mtrc_tag=b"Zalt",
        payload_tag=b"ZALT",
        values=_ZALT,
    )
    data = path.read_bytes()
    name_off = _after_tag(data, b"CASE") + 4
    name_len = int.from_bytes(data[name_off : name_off + 4], "little", signed=True)
    title_bytes = data[name_off + 4 : name_off + 4 + name_len]
    assert name_len == 20
    assert title_bytes == b"short".ljust(20, b" ")
    assert read_nmbgf_header(path).title == "short"


def test_feet_didj_irjr_ninj(tmp_path: Path) -> None:
    path = tmp_path / "geom.elv"
    _write_nmbgf(
        path,
        title="geom",
        spec=_SPEC,
        mtrc_tag=b"Zalt",
        payload_tag=b"ZALT",
        values=_ZALT,
    )
    data = path.read_bytes()
    assert b"FEET" in data

    didj_off = _after_tag(data, b"DIDJ")
    ln, di, dj = struct.unpack_from("<iff", data, didj_off)
    assert ln == 2
    assert di == pytest.approx(_SPEC.dx_out)
    assert dj == pytest.approx(_SPEC.dy_out)

    irjr_off = _after_tag(data, b"IRJR")
    ln, ir, jr = struct.unpack_from("<iii", data, irjr_off)
    assert ln == 2
    assert (ir, jr) == (1, 1)

    ninj_off = _after_tag(data, b"NINJ")
    ln, ni, nj = struct.unpack_from("<iii", data, ninj_off)
    assert ln == 2
    assert (ni, nj) == (_SPEC.width, _SPEC.height)


def test_xryr_is_origin(tmp_path: Path) -> None:
    path = tmp_path / "xryr.elv"
    _write_nmbgf(
        path,
        title="xryr",
        spec=_SPEC,
        mtrc_tag=b"Zalt",
        payload_tag=b"ZALT",
        values=_ZALT,
    )
    data = path.read_bytes()
    xryr_off = _after_tag(data, b"XRYR")
    ln, xr, yr = struct.unpack_from("<iff", data, xryr_off)
    assert ln == 2
    assert (xr, yr) == NMBGF_XRYR
    assert (xr, yr) == (0.0, 0.0)


def test_endf_present(tmp_path: Path) -> None:
    path = tmp_path / "endf.elv"
    _write_nmbgf(
        path,
        title="endf",
        spec=_SPEC,
        mtrc_tag=b"Zalt",
        payload_tag=b"ZALT",
        values=_ZALT,
    )
    data = path.read_bytes()
    assert b"ENDF" in data
    assert data[-8:-4] == b"ENDF"
    assert struct.unpack_from("<i", data, len(data) - 4)[0] == 0


def test_zalt_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "tiny.elv"
    _write_nmbgf(
        path,
        title="tiny grid",
        spec=_SPEC,
        mtrc_tag=b"Zalt",
        payload_tag=b"ZALT",
        values=_ZALT,
    )
    hdr = read_nmbgf_header(path)
    assert hdr.units == "FEET"
    assert hdr.data_tag == "ZALT"
    assert (hdr.ni, hdr.nj) == (_SPEC.width, _SPEC.height)
    assert hdr.xryr == (0.0, 0.0)
    assert hdr.n_cells == len(_ZALT)
    assert hdr.first_value == pytest.approx(_ZALT[0])
    assert hdr.last_value == pytest.approx(_ZALT[-1])
    assert hdr.values == pytest.approx(_ZALT)


def test_flow_roundtrip_not_converted_to_feet(tmp_path: Path) -> None:
    values = (DEFAULT_FLOW_RESISTIVITY,) * (_SPEC.width * _SPEC.height)
    path = tmp_path / "tiny.imp"
    _write_nmbgf(
        path,
        title="tiny flow",
        spec=_SPEC,
        mtrc_tag=b"Flow",
        payload_tag=b"FLOW",
        values=values,
    )
    hdr = read_nmbgf_header(path)
    assert hdr.data_tag == "FLOW"
    assert hdr.values == pytest.approx(values)
    assert hdr.first_value == pytest.approx(DEFAULT_FLOW_RESISTIVITY)
    converted = DEFAULT_FLOW_RESISTIVITY * FT_PER_M
    assert hdr.first_value != pytest.approx(converted)
    assert all(v != pytest.approx(converted) for v in hdr.values)


def test_read_nmbgf_grid_elv_roundtrip(tmp_path: Path) -> None:
    width = 4
    height = 3
    elevation_m = np.arange(width * height, dtype=float).reshape(height, width)
    spec = ElvGridSpec(
        width=width,
        height=height,
        dx_out=300.0,
        dy_out=150.0,
        units_tag=b"FEET",
        to_feet=True,
    )
    path = tmp_path / "orient.elv"
    write_nmbgf_elv_file(path, title="orient", spec=spec, elevation_m=elevation_m)

    grid = read_nmbgf_grid(path)
    expected_ft = (elevation_m * FT_PER_M).astype(np.float32)

    assert grid.values.shape == (height, width)
    assert grid.values.dtype == np.float32
    assert grid.header.ni == width
    assert grid.header.nj == height
    assert grid.header.units == "FEET"
    assert grid.header.data_tag == "ZALT"
    # Every cell is distinct and the grid is non-square, so this comparison
    # fails on a transpose or a row flip as well as on a value error.
    np.testing.assert_allclose(grid.values, expected_ft, rtol=1e-6)


def test_read_nmbgf_grid_indexing_matches_flat_payload_order(tmp_path: Path) -> None:
    # ``iter_grid_cells`` defines the on-disk cell order, and ``test_write_elv``
    # pins that order to a north-up source raster. This ties the 2D view to the
    # same convention: ``values[j, i]`` is the cell ``iter_grid_cells`` yields,
    # so row 0 is the north edge.
    width = 5
    height = 3
    elevation_m = np.arange(width * height, dtype=float).reshape(height, width)
    spec = ElvGridSpec(
        width=width,
        height=height,
        dx_out=300.0,
        dy_out=300.0,
        units_tag=b"FEET",
        to_feet=True,
    )
    path = tmp_path / "order.elv"
    write_nmbgf_elv_file(path, title="order", spec=spec, elevation_m=elevation_m)

    grid = read_nmbgf_grid(path)
    for index, (col_i, row_j) in enumerate(iter_grid_cells(width, height)):
        assert grid.values[row_j, col_i] == pytest.approx(
            grid.header.values[index], rel=1e-6,
        )


def test_read_nmbgf_grid_imp_roundtrip(tmp_path: Path) -> None:
    width = 4
    height = 3
    spec = NmbgfGridSpec(
        width=width,
        height=height,
        dx_out=300.0,
        dy_out=150.0,
        units_tag=b"FEET",
    )
    path = tmp_path / "orient.imp"
    write_nmbgf_imp_file(
        str(path),
        title="orient flow",
        spec=spec,
        flow_resistivity=DEFAULT_FLOW_RESISTIVITY,
    )

    grid = read_nmbgf_grid(path)

    assert grid.values.shape == (height, width)
    assert grid.values.dtype == np.float32
    assert grid.header.ni == width
    assert grid.header.nj == height
    assert grid.header.data_tag == "FLOW"
    # Constant payload, so this pins the shape and units rather than orientation.
    np.testing.assert_allclose(grid.values, DEFAULT_FLOW_RESISTIVITY, rtol=1e-6)


def _write_nmbgf(
    path: Path,
    *,
    title: str,
    spec: NmbgfGridSpec,
    mtrc_tag: bytes,
    payload_tag: bytes,
    values: tuple[float, ...],
) -> None:
    with path.open("wb") as fp:
        write_nmbgf_title(fp)
        write_nmbgf_case_header(fp, title=title, spec=spec)
        write_nmbgf_metric_header(
            fp,
            mtrc_tag=mtrc_tag,
            payload_tag=payload_tag,
            n_cells=len(values),
        )
        fp.write(
            pack_nmbgf_test_payload(
                values,
                width=spec.width,
                height=spec.height,
            )
        )
        write_nmbgf_end(fp)


def _after_tag(data: bytes, tag: bytes) -> int:
    return data.index(tag) + len(tag)
