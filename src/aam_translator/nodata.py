"""Nodata fill policies for elevation rasters."""

from __future__ import annotations

import warnings

import numpy as np


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
        warnings.warn("ELV clip has no valid elevation cells; filling with 0.0", stacklevel=2)
        out[invalid] = 0.0
        return out

    if policy == "median":
        fill = float(np.nanmedian(out))
        out[invalid] = fill
        return out

    if policy != "edge":
        raise ValueError(f"unknown nodata policy {policy!r}; use edge, zero, or median")

    valid_idx = np.argwhere(valid)
    invalid_idx = np.argwhere(invalid)
    for j, i in invalid_idx:
        dists = (valid_idx[:, 0] - j) ** 2 + (valid_idx[:, 1] - i) ** 2
        nearest = valid_idx[int(np.argmin(dists))]
        out[j, i] = out[nearest[0], nearest[1]]
    return out
