"""GDAL bilinear DEM sampling helpers for test assertions."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

from aam_translator.aeqd_grid import AeqdGrid


def _sample_dem_at_aeqd_point_src(
    src: rasterio.io.DatasetReader,
    grid: AeqdGrid,
    x_m: float,
    y_m: float,
) -> float:
    """Sample ``src`` at an AEQD point using the same GDAL bilinear warp."""
    cell_transform = from_origin(
        x_m - 0.5 * grid.dx_m,
        y_m + 0.5 * grid.dy_m,
        grid.dx_m,
        grid.dy_m,
    )
    sample = np.full((1, 1), np.nan, dtype=np.float64)
    reproject(
        source=rasterio.band(src, 1),
        destination=sample,
        src_transform=src.transform,
        src_crs=src.crs,
        dst_transform=cell_transform,
        dst_crs=grid.local_crs,
        src_nodata=src.nodata,
        dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )
    return float(sample[0, 0])


class DemOracle:
    """Reusable parent-DEM sampler for tests (one GDAL open per fixture)."""

    def __init__(self, dem_path: str | Path) -> None:
        self._src = rasterio.open(dem_path)

    def close(self) -> None:
        self._src.close()

    def __enter__(self) -> DemOracle:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def sample(self, grid: AeqdGrid, x_m: float, y_m: float) -> float:
        return _sample_dem_at_aeqd_point_src(self._src, grid, x_m, y_m)


def sample_dem_at_aeqd_point(
    dem_path: str | Path,
    grid: AeqdGrid,
    x_m: float,
    y_m: float,
) -> float:
    """Sample the parent DEM at an AEQD point using the same GDAL bilinear warp."""
    with rasterio.open(dem_path) as src:
        return _sample_dem_at_aeqd_point_src(src, grid, x_m, y_m)
