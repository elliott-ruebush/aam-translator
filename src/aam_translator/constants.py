"""Shared physical and format constants for AAM geospatial inputs."""

FT_PER_M = 3.28084
NMBGF_FLOAT = "<f"
NMBGF_TITLE_WIDTH = 20

# MKS rayls — not converted to feet (see docs/elv_pipeline.md).
DEFAULT_FLOW_RESISTIVITY = 200.0

# AAM model-space defaults (feet).
DEFAULT_MODEL_CELL_FT = 300.0
DEFAULT_CUTOFF_FT = 60000.0
DEFAULT_GRID_AGL_FT = 5.0

NMBGF_XRYR = (0.0, 0.0)

# AAM 3.0.0 rejects a 500-point track with a READ ERROR ("exceeds   400 You have
# entered >   500") even though the manual says "Number of flight track segments
# (500 max)". Exceeding this makes AAM exit 0 while writing no output.
MAX_TRACK_POINTS = 400

# Manual: "The maximum allowable number of points of interest is 500." Unverified.
MAX_POI_POINTS = 500

# Knots to feet per second, for track segment timing.
FT_S_PER_KN = 1.68781
