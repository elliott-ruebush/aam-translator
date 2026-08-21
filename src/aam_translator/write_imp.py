"""Write an AAM NMBGF ``.IMP`` ground-impedance grid matching a prior ``.ELV``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO
import logging
import struct

from .constants import DEFAULT_FLOW_RESISTIVITY, FT_PER_M
from .nmbgf_io import (
    NmbgfGridSpec,
    iter_grid_cells,
    write_nmbgf_case_header,
    write_nmbgf_end,
    write_nmbgf_metric_header,
    write_nmbgf_title,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImpGridContext:
    """ELV grid geometry required to write a matching ``.IMP`` file."""

    width: int
    height: int
    dx_m: float
    dy_m: float
    header_feet: bool = True
    default_flow_resistivity: float = DEFAULT_FLOW_RESISTIVITY


def resolve_flow_resistivity(
    constant_value: float | None,
    *,
    default: float,
) -> float:
    if constant_value is None:
        return default
    return float(constant_value)


def build_imp_grid_spec(ctx: ImpGridContext) -> NmbgfGridSpec:
    """Header spacing/units aligned with the companion ``.ELV`` grid."""
    if ctx.header_feet:
        return NmbgfGridSpec(
            width=ctx.width,
            height=ctx.height,
            dx_out=ctx.dx_m * FT_PER_M,
            dy_out=ctx.dy_m * FT_PER_M,
            units_tag=b"FEET",
        )
    return NmbgfGridSpec(
        width=ctx.width,
        height=ctx.height,
        dx_out=ctx.dx_m,
        dy_out=ctx.dy_m,
        units_tag=b"METR",
    )


def iter_flow_values(width: int, height: int, flow_resistivity: float):
    """Yield constant FLOW payload values in NMBGF cell order."""
    for _i, _j in iter_grid_cells(width, height):
        yield flow_resistivity


def write_nmbgf_imp_stream(
    fp: BinaryIO,
    *,
    title: str,
    spec: NmbgfGridSpec,
    flow_resistivity: float,
) -> int:
    """Write a complete ``.IMP`` NMBGF stream. Returns cells written."""
    write_nmbgf_title(fp)
    write_nmbgf_case_header(fp, title=title, spec=spec)
    n_cells = spec.width * spec.height
    write_nmbgf_metric_header(fp, mtrc_tag=b"Flow", payload_tag=b"FLOW", n_cells=n_cells)

    logger.debug("Expecting %d cells to be written", n_cells)
    count = 0
    for val in iter_flow_values(spec.width, spec.height, flow_resistivity):
        fp.write(struct.pack("f", val))
        count += 1
    logger.debug("Wrote %d cells", count)

    write_nmbgf_end(fp)
    return count


def write_nmbgf_imp_file(
    imp_file: str,
    *,
    title: str,
    spec: NmbgfGridSpec,
    flow_resistivity: float,
) -> None:
    with open(imp_file, "wb") as fp:
        write_nmbgf_imp_stream(
            fp, title=title, spec=spec, flow_resistivity=flow_resistivity,
        )
    logger.info(".IMP file saved to %s", imp_file)


def write_imp_for_elv_grid(
    imp_file: str,
    *,
    grid: ImpGridContext,
    title: str = "AAM impedance grid",
    constant_value: float | None = DEFAULT_FLOW_RESISTIVITY,
) -> None:
    """Write ``.IMP`` flow resistivity on the same grid as a prior ``.ELV``."""
    flow = resolve_flow_resistivity(
        constant_value, default=grid.default_flow_resistivity,
    )
    spec = build_imp_grid_spec(grid)
    write_nmbgf_imp_file(
        imp_file, title=title, spec=spec, flow_resistivity=flow,
    )
