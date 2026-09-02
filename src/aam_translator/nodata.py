"""Nodata fill policies for elevation rasters."""

from __future__ import annotations

import warnings

import numpy as np
from scipy.ndimage import distance_transform_edt


def fill_nodata(arr, nodata, policy: str = "edge") -> np.ndarray:
    """Replace nodata cells before writing ZALT.

    Parameters
    ----------
    policy:
        ``edge`` — nearest valid neighbor (default; avoids false 0 ft MSL pockets)
        ``zero`` — legacy behavior (write 0.0)
        ``median`` — fill with median of valid cells
    """
    out = arr.astype(np.float64, copy=True)
    if nodata is not None:
        out[out == nodata] = np.nan
    invalid = np.isnan(out)
    if not invalid.any():
        return out

    if policy == "zero":
        out[invalid] = 0.0
        return out

    valid = ~invalid
    if not valid.any():
        warnings.warn(
            "ELV clip has no valid elevation cells; filling with 0.0",
            stacklevel=2,
        )
        out[invalid] = 0.0
        return out

    if policy == "median":
        fill = float(np.nanmedian(out))
        out[invalid] = fill
        return out

    if policy != "edge":
        raise ValueError(f"unknown nodata policy {policy!r}; use edge, zero, or median")

    _, indices = distance_transform_edt(invalid, return_indices=True)
    nearest = out[indices[0], indices[1]]
    out[invalid] = nearest[invalid]
    return out
