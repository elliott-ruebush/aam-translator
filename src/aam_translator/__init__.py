"""AAM geospatial input translator and output reader (.ELV / .IMP / .INP / .POI)."""

from .bands import AAM_BAND_NUMBERS, NOMINAL_CENTER_HZ, band_label
from .constants import FT_PER_M, MAX_POI_POINTS, MAX_TRACK_POINTS
from .context import TerrainResult, lonlat_to_model_ft
from .nmbgf_io import NmbgfGrid, read_nmbgf_grid, read_nmbgf_header
from .poi_align import arrival_time_residuals, assert_track_alignment
from .read_log import AamRunLog, AnalysisTrackPoint, GridExtent, read_run_log
from .read_poi import PoiTimeHistory, read_poi
from .read_poi_csv import PoiSummary, read_poi_summary_csv
from .write_aam import AamInputs, write_aam_inputs, write_terrain
from .write_inp import PoiPoint, TrackPoint, hop_speed_kn, write_inp

__all__ = [
    "AAM_BAND_NUMBERS",
    "AamInputs",
    "AamRunLog",
    "AnalysisTrackPoint",
    "FT_PER_M",
    "GridExtent",
    "MAX_POI_POINTS",
    "MAX_TRACK_POINTS",
    "NOMINAL_CENTER_HZ",
    "NmbgfGrid",
    "PoiPoint",
    "PoiSummary",
    "PoiTimeHistory",
    "TerrainResult",
    "TrackPoint",
    "arrival_time_residuals",
    "assert_track_alignment",
    "band_label",
    "hop_speed_kn",
    "lonlat_to_model_ft",
    "read_nmbgf_grid",
    "read_nmbgf_header",
    "read_poi",
    "read_poi_summary_csv",
    "read_run_log",
    "write_aam_inputs",
    "write_inp",
    "write_terrain",
]
