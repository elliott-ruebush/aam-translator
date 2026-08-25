"""Write and reload ``TerrainResult`` from DEM or on-disk ELV/IMP artifacts."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import rasterio
from pyproj import CRS
from shapely.geometry.base import BaseGeometry

from .constants import (
    DEFAULT_CUTOFF_FT,
    DEFAULT_FLOW_RESISTIVITY,
    DEFAULT_GRID_AGL_FT,
    DEFAULT_MODEL_CELL_FT,
    FT_PER_M,
)
from .context import TerrainResult, aoi_envelope, build_aeqd_crs
from .grid_spec import GridSpec
from .nmbgf_io import read_nmbgf_grid, read_nmbgf_header
from .write_elv import clip_path_for_elv, write_elv_from_dem
from .write_imp import ImpGridContext, write_imp_for_elv_grid

logger = logging.getLogger(__name__)


def write_terrain(
    dem_path: str | Path,
    aoi: BaseGeometry,
    out_dir: str | Path,
    *,
    crs_in: str = "EPSG:4326",
    elv_basename: str = "scenario.elv",
    imp_basename: str = "scenario.imp",
    elv_title: str = "AAM elevation grid",
    imp_title: str = "AAM impedance grid",
    z0: float | None = None,
    to_feet: bool = True,
    nodata_policy: str = "edge",
    flow_resistivity: float = DEFAULT_FLOW_RESISTIVITY,
    grid_agl_ft: float = DEFAULT_GRID_AGL_FT,
    model_cell_ft: float = DEFAULT_MODEL_CELL_FT,
    cutoff_ft: float = DEFAULT_CUTOFF_FT,
) -> TerrainResult:
    """Clip ``dem_path`` to ``aoi``, write matching ``.ELV`` and ``.IMP`` files."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    envelope = aoi_envelope(aoi)
    aeqd_crs = build_aeqd_crs(aoi, crs_in=crs_in)
    elv_path = out / _sanitize_basename(elv_basename, kind="elv_basename")
    imp_path = out / _sanitize_basename(imp_basename, kind="imp_basename")

    elv_result = write_elv_from_dem(
        str(dem_path),
        str(elv_path),
        aoi_envelope=envelope,
        crs_in=crs_in,
        aeqd_crs=aeqd_crs,
        title=elv_title,
        z0=z0,
        to_feet=to_feet,
        nodata_policy=nodata_policy,
    )
    write_imp_for_elv_grid(
        str(imp_path),
        grid=ImpGridContext.from_elv_write(
            elv_result, flow_resistivity=flow_resistivity,
        ),
        title=imp_title,
        constant_value=flow_resistivity,
    )

    return TerrainResult.from_elv_write(
        elv_result,
        aeqd_crs=aeqd_crs,
        elv_path=str(elv_path),
        imp_path=str(imp_path),
        grid_agl_ft=grid_agl_ft,
        model_cell_ft=model_cell_ft,
        cutoff_ft=cutoff_ft,
        flow_resistivity=flow_resistivity,
    )


def load_terrain(
    elv_path: str | Path,
    *,
    imp_path: str | Path | None = None,
    clip_tif_path: str | Path | None = None,
    grid_agl_ft: float = DEFAULT_GRID_AGL_FT,
    model_cell_ft: float = DEFAULT_MODEL_CELL_FT,
    cutoff_ft: float = DEFAULT_CUTOFF_FT,
    flow_resistivity: float | None = None,
) -> TerrainResult:
    """Rebuild ``TerrainResult`` from an on-disk ELV + clip GeoTIFF (+ optional IMP)."""
    elv_path_str = str(elv_path)
    if not Path(elv_path_str).is_file():
        raise FileNotFoundError(elv_path_str)

    if clip_tif_path is None:
        clip_tif_path = clip_path_for_elv(elv_path)
    clip_tif_path_str = str(clip_tif_path)
    if not Path(clip_tif_path_str).is_file():
        raise FileNotFoundError(clip_tif_path_str)

    imp_path_str: str | None
    if imp_path is not None:
        imp_path_str = str(imp_path)
        if not Path(imp_path_str).is_file():
            raise FileNotFoundError(imp_path_str)
    else:
        imp_path_str = None

    elv_hdr = read_nmbgf_header(elv_path_str)
    elv_header_feet = elv_hdr.units == "FEET"

    with rasterio.open(clip_tif_path_str) as clip:
        if clip.crs is None:
            raise ValueError(f"clip GeoTIFF has no CRS: {clip_tif_path_str}")
        aeqd_crs = CRS.from_user_input(clip.crs)
        _assert_aeqd_crs(aeqd_crs)

        spec = GridSpec.from_north_up_transform(
            clip.transform, clip.width, clip.height,
        )
        _assert_clip_matches_elv(elv_hdr, spec, clip.width, clip.height)

    resolved_flow = _resolve_flow_resistivity(flow_resistivity, imp_path_str)

    return TerrainResult(
        spec=spec,
        aeqd_crs=aeqd_crs,
        elv_header_feet=elv_header_feet,
        elv_path=elv_path_str,
        imp_path=imp_path_str,
        clip_tif_path=clip_tif_path_str,
        grid_agl_ft=grid_agl_ft,
        model_cell_ft=model_cell_ft,
        cutoff_ft=cutoff_ft,
        flow_resistivity=resolved_flow,
    )


def _assert_aeqd_crs(crs: CRS) -> None:
    """Raise if ``crs`` is not an azimuthal equidistant projection."""
    operation = crs.coordinate_operation
    if operation is not None and operation.method_name == "Azimuthal Equidistant":
        return
    proj4 = (crs.to_proj4() or "").lower()
    if "+proj=aeqd" in proj4:
        return
    raise ValueError("clip CRS must be azimuthal equidistant (AEQD)")


def _assert_clip_matches_elv(
    elv_hdr,
    spec: GridSpec,
    clip_width: int,
    clip_height: int,
    *,
    rel_tol: float = 1e-5,
) -> None:
    """Cross-check clip dimensions and cell size against the ELV header."""
    if (clip_width, clip_height) != (elv_hdr.ni, elv_hdr.nj):
        raise ValueError(
            "clip dimensions do not match ELV grid: "
            f"clip={clip_width}x{clip_height}, ELV={elv_hdr.ni}x{elv_hdr.nj}",
        )

    if elv_hdr.units == "FEET":
        header_dx_m = abs(elv_hdr.di) / FT_PER_M
        header_dy_m = abs(elv_hdr.dj) / FT_PER_M
    elif elv_hdr.units == "METR":
        header_dx_m = abs(elv_hdr.di)
        header_dy_m = abs(elv_hdr.dj)
    else:
        raise ValueError(f"unsupported ELV units: {elv_hdr.units!r}")

    if not np.isclose(header_dx_m, spec.cell_dx_m, rtol=rel_tol):
        raise ValueError(
            "ELV cell width does not match clip transform: "
            f"header={header_dx_m} m, clip={spec.cell_dx_m} m",
        )
    if not np.isclose(header_dy_m, spec.cell_dy_m, rtol=rel_tol):
        raise ValueError(
            "ELV cell height does not match clip transform: "
            f"header={header_dy_m} m, clip={spec.cell_dy_m} m",
        )


def _resolve_flow_resistivity(
    flow_resistivity: float | None,
    imp_path: str | None,
) -> float:
    if flow_resistivity is not None:
        return float(flow_resistivity)
    if imp_path is None:
        return DEFAULT_FLOW_RESISTIVITY

    grid = read_nmbgf_grid(imp_path)
    values = grid.values
    if values.size == 0:
        return DEFAULT_FLOW_RESISTIVITY
    if np.allclose(values, values.flat[0]):
        return float(values.flat[0])
    return DEFAULT_FLOW_RESISTIVITY


def _sanitize_basename(basename: str, *, kind: str) -> str:
    """Return a safe filename component; reject empty or path-like names."""
    if not isinstance(basename, str) or not basename.strip():
        raise ValueError(f"{kind} must be a non-empty string")
    name = basename.strip()
    if not name or name in (".", ".."):
        raise ValueError(f"invalid {kind}: {basename!r}")
    if "/" in name or "\\" in name or name != Path(name).name:
        raise ValueError(f"invalid {kind}: {basename!r}")
    return name
