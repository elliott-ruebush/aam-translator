"""Unit tests for NMBGF binary header and payload I/O."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from aam_translator.constants import DEFAULT_FLOW_RESISTIVITY, FT_PER_M, NMBGF_XRYR
from aam_translator.nmbgf_io import (
    NmbgfGridSpec,
    read_nmbgf_header,
    write_nmbgf_case_header,
    write_nmbgf_end,
    write_nmbgf_metric_header,
    write_nmbgf_title,
)
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
