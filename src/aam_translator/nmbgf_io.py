"""Shared NMBGF binary grid header, payload, and footer I/O (ELV / IMP)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
import struct

from .constants import NMBGF_FLOAT, NMBGF_TITLE_WIDTH, NMBGF_XRYR


@dataclass(frozen=True)
class NmbgfGridSpec:
    """Grid dimensions and header spacing/units for NMBGF terrain grids."""

    width: int
    height: int
    dx_out: float
    dy_out: float
    units_tag: bytes


@dataclass(frozen=True)
class NmbgfHeader:
    """Parsed NMBGF header plus payload values (ZALT or FLOW)."""

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


def write_nmbgf_payload(fp: BinaryIO, values: Iterable[float]) -> None:
    """Write NMBGF payload floats with the same packing as AAM writers."""
    for val in values:
        fp.write(struct.pack(NMBGF_FLOAT, val))


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
    if data[off : off + 8] == b"GridVers":
        off += 8
        major, off = _read_i32(data, off)
        minor, off = _read_i32(data, off)
    else:
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
    _, off = _read_i32(data, off)
    name_len, off = _read_i32(data, off)
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
            off += 4
        elif tag in ("METR", "FEET"):
            _, off = _read_i32(data, off)
            units = "METR" if tag == "METR" else "FEET"
        elif tag == "DIDJ":
            ln, off = _read_i32(data, off)
            di, off = _read_f32(data, off)
            dj, off = _read_f32(data, off)
            extra = (ln - 2) * 4
            if extra > 0:
                off += extra
        elif tag == "IRJR":
            ln, off = _read_i32(data, off)
            off += ln * 4
        elif tag == "NINJ":
            ln, off = _read_i32(data, off)
            ni, nj = struct.unpack_from("<ii", data, off)
            off += ln * 4
        else:
            raise ValueError(f"unexpected CASE sub-tag {tag!r}")

    if tag != "MTRC":
        raise ValueError(f"expected MTRC, got {tag!r}")
    _, off = _read_i32(data, off)
    str_len, off = _read_i32(data, off)
    off += str_len

    xtag, off = _read_tag(data, off)
    if xtag != "XRYR":
        raise ValueError(f"expected XRYR in MTRC, got {xtag!r}")
    ln, off = _read_i32(data, off)
    xr, off = _read_f32(data, off)
    yr, off = _read_f32(data, off)
    extra = (ln - 2) * 4
    if extra > 0:
        off += extra

    data_tag, off = _read_tag(data, off)
    if data_tag not in ("ZALT", "FLOW"):
        raise ValueError(f"expected ZALT or FLOW, got {data_tag!r}")

    n_cells, off = _read_i32(data, off)
    nbytes = n_cells * 4
    if n_cells < 0 or off + nbytes > len(data):
        raise ValueError(f"invalid n_cells {n_cells}")
    if n_cells:
        values = struct.unpack_from(f"<{n_cells}f", data, off)
    else:
        values = ()
    off += nbytes

    end_tag, off = _read_tag(data, off)
    if end_tag != "ENDF":
        raise ValueError(f"expected ENDF, got {end_tag!r}")

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


def _align4(n: int) -> int:
    return (4 - (n % 4)) % 4


def _read_tag(data: bytes, off: int) -> tuple[str, int]:
    tag = struct.unpack_from("4s", data, off)[0].decode("ascii")
    return tag, off + 4


def _read_i32(data: bytes, off: int) -> tuple[int, int]:
    return struct.unpack_from("<i", data, off)[0], off + 4


def _read_f32(data: bytes, off: int) -> tuple[float, int]:
    return struct.unpack_from(NMBGF_FLOAT, data, off)[0], off + 4
