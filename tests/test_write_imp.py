"""Unit tests for NMBGF ``.IMP`` writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from aam_translator.constants import DEFAULT_FLOW_RESISTIVITY, FT_PER_M, NMBGF_XRYR
from aam_translator.grid_spec import GridSpec
from aam_translator.nmbgf_io import (
    NmbgfGridSpec,
    read_nmbgf_header,
    write_nmbgf_case_header,
    write_nmbgf_end,
    write_nmbgf_metric_header,
    write_nmbgf_title,
)
from aam_translator.write_imp import ImpGridContext, write_imp_for_elv_grid
from nmbgf_helpers import pack_nmbgf_test_payload

_GRID_SPEC = GridSpec(
    cell_count_x=4,
    cell_count_y=3,
    cell_dx_m=91.44,
    cell_dy_m=45.72,
    grid_origin_x_m=0.0,
    grid_origin_y_m=0.0,
)
_GRID = ImpGridContext(spec=_GRID_SPEC)
_DX_FT = _GRID_SPEC.cell_dx_m * FT_PER_M
_DY_FT = _GRID_SPEC.cell_dy_m * FT_PER_M
_N_CELLS = _GRID_SPEC.cell_count_x * _GRID_SPEC.cell_count_y


def _write_minimal_elv(path: Path, *, spec: NmbgfGridSpec, title: str) -> None:
    values = tuple(float(i) for i in range(spec.width * spec.height))
    with path.open("wb") as fp:
        write_nmbgf_title(fp)
        write_nmbgf_case_header(fp, title=title, spec=spec)
        write_nmbgf_metric_header(
            fp,
            mtrc_tag=b"Zalt",
            payload_tag=b"ZALT",
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


def test_write_imp_for_elv_grid_header_and_flow(tmp_path: Path) -> None:
    imp_path = tmp_path / "terrain.imp"
    write_imp_for_elv_grid(str(imp_path), grid=_GRID)

    hdr = read_nmbgf_header(imp_path)
    assert hdr.data_tag == "FLOW"
    assert hdr.units == "FEET"
    assert (hdr.ni, hdr.nj) == (_GRID_SPEC.cell_count_x, _GRID_SPEC.cell_count_y)
    assert hdr.di == pytest.approx(_DX_FT)
    assert hdr.dj == pytest.approx(_DY_FT)
    assert hdr.xryr == NMBGF_XRYR
    assert hdr.xryr == (0.0, 0.0)
    assert hdr.n_cells == _N_CELLS
    assert all(v == pytest.approx(DEFAULT_FLOW_RESISTIVITY) for v in hdr.values)


def test_write_imp_geometry_matches_companion_elv(tmp_path: Path) -> None:
    spec = NmbgfGridSpec(
        width=_GRID_SPEC.cell_count_x,
        height=_GRID_SPEC.cell_count_y,
        dx_out=_DX_FT,
        dy_out=_DY_FT,
        units_tag=b"FEET",
    )
    elv_path = tmp_path / "terrain.elv"
    imp_path = tmp_path / "terrain.imp"

    _write_minimal_elv(elv_path, spec=spec, title="companion elv")
    write_imp_for_elv_grid(str(imp_path), grid=_GRID, title="companion elv")

    elv_hdr = read_nmbgf_header(elv_path)
    imp_hdr = read_nmbgf_header(imp_path)

    assert (imp_hdr.ni, imp_hdr.nj) == (elv_hdr.ni, elv_hdr.nj)
    assert imp_hdr.di == pytest.approx(elv_hdr.di)
    assert imp_hdr.dj == pytest.approx(elv_hdr.dj)
    assert imp_hdr.units == elv_hdr.units
    assert imp_hdr.xryr == elv_hdr.xryr
