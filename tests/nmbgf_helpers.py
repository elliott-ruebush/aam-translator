"""Shared helpers for building NMBGF test payloads."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from aam_translator.nmbgf_io import iter_grid_cells, pack_nmbgf_payload


def nmbgf_grid_from_values(
    values: Sequence[float],
    *,
    width: int,
    height: int,
) -> np.ndarray:
    """Rebuild a north-up raster from NMBGF column-major payload order."""
    arr = np.zeros((height, width), dtype=np.float64)
    for idx, (i, j) in enumerate(iter_grid_cells(width, height)):
        arr[j, i] = values[idx]
    return arr


def pack_nmbgf_test_payload(
    values: Sequence[float],
    *,
    width: int,
    height: int,
    to_feet: bool = False,
    scale: float = 1.0,
) -> bytes:
    return pack_nmbgf_payload(
        nmbgf_grid_from_values(values, width=width, height=height),
        to_feet=to_feet,
        scale=scale,
    )
