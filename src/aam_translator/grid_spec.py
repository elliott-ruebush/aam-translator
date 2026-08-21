"""Shared grid geometry for AEQD resampling and AAM model-space transforms."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BoundsM:
    """Axis-aligned bounds in a projected CRS, in meters."""

    xmin_m: float
    ymin_m: float
    xmax_m: float
    ymax_m: float

    @classmethod
    def from_tuple(cls, bounds: tuple[float, float, float, float]) -> BoundsM:
        xmin_m, ymin_m, xmax_m, ymax_m = bounds
        return cls(xmin_m, ymin_m, xmax_m, ymax_m)

    def as_tuple(self) -> tuple[float, float, float, float]:
        return self.xmin_m, self.ymin_m, self.xmax_m, self.ymax_m


def merge_bounds(*bounds: BoundsM) -> BoundsM:
    """Return the union of several axis-aligned bounds."""
    return BoundsM(
        xmin_m=min(b.xmin_m for b in bounds),
        ymin_m=min(b.ymin_m for b in bounds),
        xmax_m=max(b.xmax_m for b in bounds),
        ymax_m=max(b.ymax_m for b in bounds),
    )


@dataclass(frozen=True)
class GridSpec:
    """Regular north-up lattice: SW corner, cell size, and cell counts."""

    cell_count_x: int
    cell_count_y: int
    cell_dx_m: float
    cell_dy_m: float
    grid_origin_x_m: float
    grid_origin_y_m: float

    @property
    def grid_extent_x_m(self) -> float:
        return self.grid_origin_x_m + self.cell_count_x * self.cell_dx_m

    @property
    def grid_extent_y_m(self) -> float:
        return self.grid_origin_y_m + self.cell_count_y * self.cell_dy_m
