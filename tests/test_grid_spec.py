"""Tests for shared grid geometry helpers."""

from __future__ import annotations

import pytest
from rasterio.transform import Affine, from_origin

from aam_translator.grid_spec import GridSpec


def test_from_north_up_transform_inverts_from_origin() -> None:
    west, north, dx, dy = -100.0, 500.0, 30.0, 30.0
    width, height = 12, 8
    transform = from_origin(west, north, dx, dy)

    spec = GridSpec.from_north_up_transform(transform, width, height)

    assert spec.cell_count_x == width
    assert spec.cell_count_y == height
    assert spec.cell_dx_m == pytest.approx(dx)
    assert spec.cell_dy_m == pytest.approx(dy)
    assert spec.grid_origin_x_m == pytest.approx(west)
    assert spec.grid_origin_y_m == pytest.approx(north - height * dy)


def test_from_north_up_transform_rejects_rotation() -> None:
    transform = Affine(30.0, 1.0, 0.0, 0.0, -30.0, 500.0)
    with pytest.raises(ValueError, match="rotated or skewed"):
        GridSpec.from_north_up_transform(transform, 10, 10)


def test_from_north_up_transform_rejects_west_up() -> None:
    transform = Affine(-30.0, 0.0, 0.0, 0.0, -30.0, 500.0)
    with pytest.raises(ValueError, match="west-up"):
        GridSpec.from_north_up_transform(transform, 10, 10)


def test_from_north_up_transform_rejects_south_up() -> None:
    transform = Affine(30.0, 0.0, 0.0, 0.0, 30.0, 500.0)
    with pytest.raises(ValueError, match="south-up"):
        GridSpec.from_north_up_transform(transform, 10, 10)


def test_from_north_up_transform_rejects_non_positive_size() -> None:
    transform = from_origin(0.0, 100.0, 30.0, 30.0)
    with pytest.raises(ValueError, match="width and height must be positive"):
        GridSpec.from_north_up_transform(transform, 0, 10)
