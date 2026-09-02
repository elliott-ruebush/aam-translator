"""Tests for nodata fill policies."""

import time

import numpy as np
import pytest

from aam_translator.nodata import fill_nodata


def test_zero_writes_zero():
    arr = np.array([[1.0, -9999.0], [3.0, 4.0]])
    out = fill_nodata(arr, nodata=-9999.0, policy="zero")
    assert out.dtype == np.float64
    np.testing.assert_array_equal(out, [[1.0, 0.0], [3.0, 4.0]])


def test_median_uses_valid_median():
    arr = np.array([[1.0, 3.0], [-9999.0, 5.0]])
    out = fill_nodata(arr, nodata=-9999.0, policy="median")
    np.testing.assert_array_equal(out, [[1.0, 3.0], [3.0, 5.0]])


def test_edge_copies_nearest_valid():
    arr = np.array(
        [
            [10.0, np.nan, 30.0],
            [np.nan, np.nan, np.nan],
        ]
    )
    out = fill_nodata(arr, nodata=None, policy="edge")
    assert out[0, 1] == 10.0
    assert out[1, 0] == 10.0
    assert out[1, 2] == 30.0
    assert out[1, 1] in (10.0, 30.0)
    np.testing.assert_array_equal(out[0, [0, 2]], [10.0, 30.0])


def test_edge_never_fills_zero_from_valid_neighbors():
    arr = np.array([[5.0, np.nan, 7.0], [np.nan, np.nan, np.nan]])
    out = fill_nodata(arr, nodata=None, policy="edge")
    filled = out[np.isnan(arr)]
    assert np.all(filled != 0.0)
    assert set(filled.tolist()) <= {5.0, 7.0}


def test_unknown_policy_raises():
    arr = np.array([[1.0, np.nan]])
    with pytest.raises(ValueError, match="unknown nodata policy"):
        fill_nodata(arr, nodata=None, policy="bogus")


def test_no_invalid_cells_returns_float64_copy():
    arr = np.array([[1, 2], [3, 4]], dtype=np.int32)
    out = fill_nodata(arr, nodata=-9999, policy="edge")
    assert out is not arr
    assert out.dtype == np.float64
    np.testing.assert_array_equal(out, [[1.0, 2.0], [3.0, 4.0]])


def test_all_nan_fills_zero_and_warns():
    arr = np.array([[np.nan, np.nan], [np.nan, np.nan]])
    with pytest.warns(UserWarning, match="no valid elevation cells"):
        out = fill_nodata(arr, nodata=None, policy="edge")
    np.testing.assert_array_equal(out, np.zeros((2, 2)))


def test_all_nodata_fills_zero_and_warns():
    arr = np.full((2, 2), -9999.0)
    with pytest.warns(UserWarning, match="no valid elevation cells"):
        out = fill_nodata(arr, nodata=-9999.0, policy="median")
    np.testing.assert_array_equal(out, np.zeros((2, 2)))


def test_edge_fill_performance():
    size = 400
    arr = np.arange(size * size, dtype=np.float64).reshape(size, size)
    corner = size // 4
    arr[:corner, :corner] = np.nan
    arr[-corner:, -corner:] = np.nan

    start = time.perf_counter()
    out = fill_nodata(arr, nodata=None, policy="edge")
    elapsed = time.perf_counter() - start

    assert elapsed < 2.0
    assert not np.isnan(out).any()
    valid_neighbors = arr[~np.isnan(arr)]
    filled = out[np.isnan(arr)]
    assert set(np.unique(filled).tolist()) <= set(np.unique(valid_neighbors).tolist())
