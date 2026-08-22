"""Read AAM's post-run ``{basename}.txt`` log.

Three things in this file are worth structuring:

* the ``READ ERROR`` banner, because AAM exits 0 even when it rejects an input
  deck and writes no results at all, so exit status is not a success signal;
* the ``Interpolated Track for analysis`` table, which is AAM's authoritative
  statement of the track it actually analyzed, one row per ``.POI`` output row;
* the ``Terrain Information`` / ``Impedance Information`` extents, which are what
  the manual's ``TERRAINCHK`` actually compares (no log line names that check).

Everything else stays available as :attr:`AamRunLog.raw_text`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_READ_ERROR_RE = re.compile(r"^\s*\*+\s*READ ERROR.*?\*+\s*$", re.MULTILINE)
_ANALYSIS_HEADER_RE = re.compile(
    r"^\s*Interpolated Track for analysis\.\s+(?P<count>\d+)\s+points.*$",
    re.MULTILINE,
)
_GRID_UNITS_RE = re.compile(r"^\s*(?:ELV|IMP) file \(X,Y\) in (?P<units>\w+)", re.M)

_ANALYSIS_COLUMNS = {
    "time_s": "time",
    "x_ft": "Xft",
    "y_ft": "Yft",
    "z_msl_ft": "Z-MSL",
    "speed_kn": "spd",
}


@dataclass(frozen=True)
class AnalysisTrackPoint:
    """One row of the ``Interpolated Track for analysis`` table."""

    time_s: float
    x_ft: float
    y_ft: float
    z_msl_ft: float
    speed_kn: float


@dataclass(frozen=True)
class GridExtent:
    """Terrain or impedance grid geometry as AAM read it, in header units."""

    title: str
    lower_left: tuple[float, float]
    spacing: tuple[float, float]
    grid_size: tuple[int, int]
    upper_right: tuple[float, float]
    units: str | None


@dataclass(frozen=True)
class AamRunLog:
    """Structured fields from an AAM run log, plus the untouched text."""

    read_error: str | None
    declared_analysis_points: int | None
    analysis_track: tuple[AnalysisTrackPoint, ...] | None
    elevation: GridExtent | None
    impedance: GridExtent | None
    raw_text: str

    @property
    def ok(self) -> bool:
        """True when AAM reported no read error."""
        return self.read_error is None


def read_run_log(path: str | Path) -> AamRunLog:
    """Parse an AAM ``{basename}.txt`` run log."""
    log_path = Path(path)
    try:
        text = log_path.read_text(errors="replace")
    except FileNotFoundError:
        raise ValueError(f"no such AAM run log: {log_path}") from None

    declared, track = _parse_analysis_track(text)
    return AamRunLog(
        read_error=_parse_read_error(text),
        declared_analysis_points=declared,
        analysis_track=track,
        elevation=_parse_grid_extent(text, "Terrain Information"),
        impedance=_parse_grid_extent(text, "Impedance Information"),
        raw_text=text,
    )


def _parse_read_error(text: str) -> str | None:
    """Return the READ ERROR banner and its detail lines, if present."""
    match = _READ_ERROR_RE.search(text)
    if match is None:
        return None

    lines = [match.group(0).strip()]
    for line in text[match.end() :].splitlines():
        stripped = line.strip()
        if not stripped:
            # Skip the blank remainder of the banner line, but stop at the first
            # blank line after the detail text has started.
            if len(lines) > 1:
                break
            continue
        lines.append(stripped)
    return "\n".join(lines)


def _parse_analysis_track(
    text: str,
) -> tuple[int | None, tuple[AnalysisTrackPoint, ...] | None]:
    """Parse the analysis-track table, mapping columns by header name."""
    match = _ANALYSIS_HEADER_RE.search(text)
    if match is None:
        return None, None

    declared = int(match.group("count"))
    lines = text[match.end() :].splitlines()
    if len(lines) < 2:
        return declared, None

    names = lines[1].split()
    try:
        indices = {
            field: names.index(column) for field, column in _ANALYSIS_COLUMNS.items()
        }
    except ValueError:
        return declared, None

    points: list[AnalysisTrackPoint] = []
    for line in lines[2:]:
        fields = line.split()
        if len(fields) <= max(indices.values()):
            break
        try:
            values = {field: float(fields[i]) for field, i in indices.items()}
        except ValueError:
            break
        points.append(AnalysisTrackPoint(**values))
    return declared, tuple(points)


def _parse_grid_extent(text: str, heading: str) -> GridExtent | None:
    """Parse one ``Terrain``/``Impedance Information`` block."""
    start = text.find(heading)
    if start < 0:
        return None
    block = text[start : start + 2000]

    title = _match_line(block, r"^\s*Title=\s*(.*)$")
    lower_left = _match_pair(block, r"^\s*LowerLeft\s*=\s*(\S+)\s+(\S+)")
    spacing = _match_pair(block, r"^\s*Spacing\s*=\s*(\S+)\s+(\S+)")
    grid_size = _match_pair(block, r"^\s*Grid Size\s*=\s*(\S+)\s+(\S+)")
    upper_right = _match_pair(block, r"^\s*UpperRight\s*=\s*(\S+)\s+(\S+)")
    if (
        lower_left is None
        or spacing is None
        or grid_size is None
        or upper_right is None
    ):
        return None

    units = _GRID_UNITS_RE.search(block)
    return GridExtent(
        title=(title or "").strip(),
        lower_left=(float(lower_left[0]), float(lower_left[1])),
        spacing=(float(spacing[0]), float(spacing[1])),
        grid_size=(int(grid_size[0]), int(grid_size[1])),
        upper_right=(float(upper_right[0]), float(upper_right[1])),
        units=units.group("units") if units else None,
    )


def _match_line(block: str, pattern: str) -> str | None:
    match = re.search(pattern, block, re.MULTILINE)
    return match.group(1) if match else None


def _match_pair(block: str, pattern: str) -> tuple[str, str] | None:
    match = re.search(pattern, block, re.MULTILINE)
    return (match.group(1), match.group(2)) if match else None
