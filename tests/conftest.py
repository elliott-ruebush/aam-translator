"""Shared pytest fixtures for aam_translator tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import shape

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def tiny_dem_path() -> Path:
    return FIXTURES_DIR / "tiny_dem.tif"


@pytest.fixture
def tiny_aoi_geom():
    geojson = json.loads((FIXTURES_DIR / "tiny_aoi.geojson").read_text())
    return shape(geojson["geometry"])
