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


_TRANSFORM_ATOL_M = 1e-9


@dataclass(frozen=True)
class GridSpec:
    """Regular north-up lattice: SW corner, cell size, and cell counts."""

    cell_count_x: int
    cell_count_y: int
    cell_dx_m: float
    cell_dy_m: float
    grid_origin_x_m: float
    grid_origin_y_m: float

    @classmethod
    def from_north_up_transform(
        cls,
        transform,
        width: int,
        height: int,
    ) -> GridSpec:
        """Build a ``GridSpec`` from a north-up pixel-is-area affine (inverse of ``from_origin``)."""
        if width <= 0 or height <= 0:
            raise ValueError(
                f"width and height must be positive, got width={width}, height={height}",
            )

        a = transform.a
        b = transform.b
        c = transform.c
        d = transform.d
        e = transform.e
        f = transform.f

        if abs(b) > _TRANSFORM_ATOL_M or abs(d) > _TRANSFORM_ATOL_M:
            raise ValueError("clip transform is rotated or skewed; expected north-up")
        if a <= 0:
            raise ValueError("clip transform is west-up; expected east-up (a > 0)")
        if e >= 0:
            raise ValueError("clip transform is south-up; expected north-up (e < 0)")

        return cls(
            cell_count_x=width,
            cell_count_y=height,
            cell_dx_m=a,
            cell_dy_m=-e,
            grid_origin_x_m=c,
            grid_origin_y_m=f + height * e,
        )

    @property
    def grid_extent_x_m(self) -> float:
        return self.grid_origin_x_m + self.cell_count_x * self.cell_dx_m

    @property
    def grid_extent_y_m(self) -> float:
        return self.grid_origin_y_m + self.cell_count_y * self.cell_dy_m
