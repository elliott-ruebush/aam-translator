"""Shared NMBGF binary grid header, payload, and footer I/O (ELV / IMP)."""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np

from .constants import FT_PER_M, NMBGF_FLOAT, NMBGF_TITLE_WIDTH, NMBGF_XRYR


@dataclass(frozen=True)
class NmbgfGridSpec:
    """Grid dimensions and header spacing/units for NMBGF terrain grids."""

    width: int
    height: int
    dx_out: float
    dy_out: float
    units_tag: bytes


def build_nmbgf_grid_spec(
    *,
    width: int,
    height: int,
    dx_m: float,
    dy_m: float,
    header_feet: bool,
) -> NmbgfGridSpec:
    """Header cell spacing and units tag from metric grid dimensions."""
    if header_feet:
        return NmbgfGridSpec(
            width=width,
            height=height,
            dx_out=dx_m * FT_PER_M,
            dy_out=dy_m * FT_PER_M,
            units_tag=b"FEET",
        )
    return NmbgfGridSpec(
        width=width,
        height=height,
        dx_out=dx_m,
        dy_out=dy_m,
        units_tag=b"METR",
    )


@dataclass(frozen=True)
class NmbgfHeader:
    """Parsed NMBGF header plus payload values (ZALT or FLOW).

    Prefer :class:`NmbgfGrid` and :func:`read_nmbgf_grid` when the payload is
    needed as a north-up 2D array.
    """

    version: tuple[int, int]
    title: str
    units: str
    di: float
    dj: float
    ni: int
    nj: int
    data_tag: str
    xryr: tuple[float, float]
    n_cells: int
    first_value: float | None
    last_value: float | None
    values: tuple[float, ...]


@dataclass(frozen=True)
class NmbgfGrid:
    """An NMBGF grid header plus its payload as a north-up 2D array."""

    header: NmbgfHeader
    values: np.ndarray  # shape (height, width) == (header.nj, header.ni)


def write_nmbgf_title(fp: BinaryIO) -> None:
    fp.write(b"TITL")
    fp.write(struct.pack("<i", 4))
    fp.write(b"Grid")
    fp.write(b"Vers")
    fp.write(struct.pack("<i", 1))
    fp.write(struct.pack("<i", 0))


def write_nmbgf_case_header(
    fp: BinaryIO,
    *,
    title: str,
    spec: NmbgfGridSpec,
) -> None:
    fp.write(b"CASE")
    fp.write(struct.pack("<i", 6))

    title_bytes = title.encode("ascii", errors="replace")
    title_bytes = title_bytes[:NMBGF_TITLE_WIDTH].ljust(NMBGF_TITLE_WIDTH, b" ")
    fp.write(struct.pack("<i", NMBGF_TITLE_WIDTH))
    fp.write(title_bytes)

    fp.write(b"DECM")
    fp.write(struct.pack("<i", 2))
    fp.write(b"FLOT")
    fp.write(struct.pack("<i", 1))
    fp.write(spec.units_tag)
    fp.write(struct.pack("<i", 0))
    fp.write(b"DIDJ")
    fp.write(struct.pack("<i", 2))
    fp.write(struct.pack(NMBGF_FLOAT, spec.dx_out))
    fp.write(struct.pack(NMBGF_FLOAT, spec.dy_out))
    fp.write(b"IRJR")
    fp.write(struct.pack("<i", 2))
    fp.write(struct.pack("<i", 1))
    fp.write(struct.pack("<i", 1))
    fp.write(b"NINJ")
    fp.write(struct.pack("<i", 2))
    fp.write(struct.pack("<i", spec.width))
    fp.write(struct.pack("<i", spec.height))


def write_nmbgf_metric_header(
    fp: BinaryIO,
    *,
    mtrc_tag: bytes,
    payload_tag: bytes,
    n_cells: int,
) -> None:
    """Write MTRC block opening a ZALT or FLOW payload section."""
    xr, yr = NMBGF_XRYR
    fp.write(b"MTRC")
    fp.write(struct.pack("<i", 2))
    fp.write(struct.pack("<i", 4))
    fp.write(mtrc_tag)
    fp.write(b"XRYR")
    fp.write(struct.pack("<i", 2))
    fp.write(struct.pack(NMBGF_FLOAT, xr))
    fp.write(struct.pack(NMBGF_FLOAT, yr))
    fp.write(payload_tag)
    fp.write(struct.pack("<i", n_cells))


def pack_nmbgf_payload(
    arr_2d: np.ndarray,
    *,
    to_feet: bool = False,
    scale: float = 1.0,
) -> bytes:
    """Pack ``(ny, nx)`` north-up rows into NMBGF column-major / j-reversed order."""
    data = np.asarray(arr_2d, dtype=np.float64)
    if to_feet:
        data = data * FT_PER_M
    if scale != 1.0:
        data = data * scale
    payload = np.asfortranarray(data[::-1, :], dtype="<f4").ravel(order="F")
    return payload.tobytes()


def write_nmbgf_end(fp: BinaryIO) -> None:
    fp.write(b"ENDF")
    fp.write(struct.pack("<i", 0))


def iter_grid_cells(width: int, height: int) -> Iterator[tuple[int, int]]:
    """Yield ``(i, j)`` in NMBGF column-major / j-reversed order."""
    for i in range(width):
        for j in range(height - 1, -1, -1):
            yield i, j


def read_nmbgf_header(path: str | Path) -> NmbgfHeader:
    """Parse an AAM-style NMBGF header and payload (ELV or IMP)."""
    data = Path(path).read_bytes()
    off = 0
    tag, off = _read_tag(data, off)
    if tag != "TITL":
        raise ValueError(f"expected TITL, got {tag!r}")

    titl_len, off = _read_i32(data, off)
    if titl_len < 0:
        raise ValueError(f"invalid TITL length {titl_len}")
    if data[off : off + 8] == b"GridVers":
        _ensure_bytes(data, off, 8, what="TITL GridVers")
        off += 8
        major, off = _read_i32(data, off)
        minor, off = _read_i32(data, off)
    else:
        _ensure_bytes(data, off, titl_len, what="TITL payload")
        off += titl_len
        tag, off = _read_tag(data, off)
        if tag != "Vers":
            raise ValueError(f"expected Vers after TITL, got {tag!r}")
        major, off = _read_i32(data, off)
        minor, off = _read_i32(data, off)
    version = (major, minor)

    tag, off = _read_tag(data, off)
    if tag != "CASE":
        raise ValueError(f"expected CASE, got {tag!r}")
    case_len, off = _read_i32(data, off)
    if case_len < 0:
        raise ValueError(f"invalid CASE length {case_len}")
    name_len, off = _read_i32(data, off)
    if name_len < 0:
        raise ValueError(f"invalid CASE title length {name_len}")
    _ensure_bytes(data, off, name_len, what="CASE title")
    title = data[off : off + name_len].decode("ascii", errors="replace").strip()
    off += name_len + _align4(name_len)

    units: str | None = None
    di: float | None = None
    dj: float | None = None
    ni: int | None = None
    nj: int | None = None

    while off < len(data):
        tag, off = _read_tag(data, off)
        if tag == "MTRC":
            break
        if tag in ("ZALT", "FLOW", "ENDF"):
            raise ValueError(f"unexpected top-level tag {tag!r} before MTRC")
        if tag in ("DECM", "FLOT"):
            _ensure_bytes(data, off, 4, what=f"{tag} payload")
            off += 4
        elif tag in ("METR", "FEET"):
            ln, off = _read_i32(data, off)
            if ln < 0:
                raise ValueError(f"invalid {tag} length {ln}")
            _ensure_bytes(data, off, ln * 4, what=tag)
            off += ln * 4
            units = "METR" if tag == "METR" else "FEET"
        elif tag == "DIDJ":
            ln, off = _read_i32(data, off)
            if ln < 2:
                raise ValueError(f"invalid DIDJ length {ln}")
            _ensure_bytes(data, off, ln * 4, what="DIDJ")
            di, off = _read_f32(data, off)
            dj, off = _read_f32(data, off)
            off += (ln - 2) * 4
        elif tag == "IRJR":
            ln, off = _read_i32(data, off)
            if ln < 0:
                raise ValueError(f"invalid IRJR length {ln}")
            _ensure_bytes(data, off, ln * 4, what="IRJR")
            off += ln * 4
        elif tag == "NINJ":
            ln, off = _read_i32(data, off)
            if ln < 2:
                raise ValueError(f"invalid NINJ length {ln}")
            _ensure_bytes(data, off, ln * 4, what="NINJ")
            ni, nj = struct.unpack_from("<ii", data, off)
            off += ln * 4
        else:
            raise ValueError(f"unexpected CASE sub-tag {tag!r}")

    if tag != "MTRC":
        raise ValueError(f"expected MTRC, got {tag!r}")
    mtrc_len, off = _read_i32(data, off)
    if mtrc_len < 0:
        raise ValueError(f"invalid MTRC length {mtrc_len}")
    str_len, off = _read_i32(data, off)
    if str_len < 0:
        raise ValueError(f"invalid MTRC string length {str_len}")
    _ensure_bytes(data, off, str_len, what="MTRC string")
    off += str_len

    xtag, off = _read_tag(data, off)
    if xtag != "XRYR":
        raise ValueError(f"expected XRYR in MTRC, got {xtag!r}")
    ln, off = _read_i32(data, off)
    if ln < 2:
        raise ValueError(f"invalid XRYR length {ln}")
    _ensure_bytes(data, off, ln * 4, what="XRYR")
    xr, off = _read_f32(data, off)
    yr, off = _read_f32(data, off)
    off += (ln - 2) * 4

    data_tag, off = _read_tag(data, off)
    if data_tag not in ("ZALT", "FLOW"):
        raise ValueError(f"expected ZALT or FLOW, got {data_tag!r}")

    n_cells, off = _read_i32(data, off)
    if n_cells < 0:
        raise ValueError(f"invalid n_cells {n_cells}")
    nbytes = n_cells * 4
    _ensure_bytes(data, off, nbytes, what=f"{data_tag} payload")
    values = (
        struct.unpack_from(f"<{n_cells}f", data, off) if n_cells else ()
    )
    off += nbytes

    end_tag, off = _read_tag(data, off)
    if end_tag != "ENDF":
        raise ValueError(f"expected ENDF, got {end_tag!r}")
    _, off = _read_i32(data, off)

    if units is None or di is None or dj is None or ni is None or nj is None:
        raise ValueError("incomplete grid tags")

    return NmbgfHeader(
        version=version,
        title=title,
        units=units,
        di=di,
        dj=dj,
        ni=ni,
        nj=nj,
        data_tag=data_tag,
        xryr=(xr, yr),
        n_cells=n_cells,
        first_value=values[0] if values else None,
        last_value=values[-1] if values else None,
        values=tuple(values),
    )


def read_nmbgf_grid(path: str | Path) -> NmbgfGrid:
    """Read a full NMBGF grid: header plus payload reshaped to north-up rows.

    Scoped to the ``CASE``-family NMBGF that this package writes (``.ELV`` with a
    ``ZALT`` payload and ``.IMP`` with a ``FLOW`` payload). AAM's ``COMPUTEGRD``
    ``.GRD`` output is a different NMBGF dialect (``MTRC``/``CART``/``LINS``/``GRID``
    tags, no ``CASE`` block) and is not supported here.
    """
    header = read_nmbgf_header(path)
    path_obj = Path(path)
    expected_cells = header.ni * header.nj
    if header.n_cells != expected_cells:
        raise ValueError(
            f"NMBGF cell count mismatch in {path_obj}: "
            f"n_cells={header.n_cells}, ni*nj={expected_cells}"
        )

    height = header.nj
    width = header.ni
    flat = np.asarray(header.values, dtype=np.float32)
    values = flat.reshape((height, width), order="F")[::-1, :]
    return NmbgfGrid(header=header, values=values)


def _align4(n: int) -> int:
    return (4 - (n % 4)) % 4


def _ensure_bytes(data: bytes, off: int, n: int, *, what: str) -> None:
    if off < 0 or off + n > len(data):
        raise ValueError(
            f"truncated NMBGF file while reading {what} at offset {off} "
            f"(need {n} bytes, file size {len(data)})"
        )


def _read_tag(data: bytes, off: int) -> tuple[str, int]:
    _ensure_bytes(data, off, 4, what="tag")
    tag = struct.unpack_from("4s", data, off)[0].decode("ascii")
    return tag, off + 4


def _read_i32(data: bytes, off: int) -> tuple[int, int]:
    _ensure_bytes(data, off, 4, what="i32")
    return struct.unpack_from("<i", data, off)[0], off + 4


def _read_f32(data: bytes, off: int) -> tuple[float, int]:
    _ensure_bytes(data, off, 4, what="f32")
    return struct.unpack_from(NMBGF_FLOAT, data, off)[0], off + 4
