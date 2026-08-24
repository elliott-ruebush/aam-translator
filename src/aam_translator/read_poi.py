"""Read AAM's ``.POI`` spectral time history (Tecplot ASCII).

A ``COMPUTEPOI`` run writes one ``ZONE`` per POI receiver, in the order the
receivers appear in the ``.INP`` ``POI`` block. Each zone holds one row per
flight-track point, in track order, with the row's ``Time`` being the *arrival*
time of sound emitted at that track point.

The file names no receivers, so zones are identified positionally. Receiver
names live in the companion ``{basename}.Single.POI.csv`` -- see
:mod:`aam_translator.read_poi_csv`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from .bands import band_number_for_frequency

if TYPE_CHECKING:  # pragma: no cover - import only for type checking
    import pandas as pd

# AAM writes this in a band cell that received no energy.
AAM_NODATA_DB = -370.0

# Columns preceding the one-third-octave bands, after the leading ``Time``.
POI_BROADBAND_COLUMNS: tuple[str, ...] = ("SPL", "dBC", "dBA", "PNL", "PNLT")

_LEADING_COLUMN_COUNT = 1 + len(POI_BROADBAND_COLUMNS)
_VARIABLES_RE = re.compile(r"^VARIABLES\s*=(.*)$", re.MULTILINE)
_QUOTED_RE = re.compile(r'"([^"]*)"')
_FREQ_RE = re.compile(r"([\d.]+)\s*Hz")
_ZONE_RE = re.compile(r"^ZONE\b(?P<attrs>.*)$", re.MULTILINE)
_ZONE_COUNT_RE = re.compile(r"\bI\s*=\s*(\d+)")


@dataclass(frozen=True)
class PoiTimeHistory:
    """Spectral time history at one POI receiver.

    ``time_s``, ``broadband_db`` and ``band_levels_db`` share a leading axis of
    one row per flight-track point, in track order. Row order is preserved
    exactly as written; ``time_s`` is *not* guaranteed to increase, because a
    later track point can be much closer to the receiver than an earlier one.
    """

    zone_index: int
    time_s: np.ndarray
    broadband_db: np.ndarray
    band_levels_db: np.ndarray
    band_numbers: tuple[int, ...]

    @property
    def n_samples(self) -> int:
        """Number of rows, i.e. the number of track points AAM analyzed."""
        return int(self.time_s.shape[0])

    def broadband(self, name: str) -> np.ndarray:
        """Return one broadband column by name, e.g. ``"dBA"``."""
        try:
            index = POI_BROADBAND_COLUMNS.index(name)
        except ValueError:
            raise KeyError(
                f"unknown broadband column {name!r}; "
                f"expected one of {POI_BROADBAND_COLUMNS}"
            ) from None
        return self.broadband_db[:, index]

    def to_dataframe(self) -> pd.DataFrame:
        """Return a DataFrame of time, broadband columns, then band numbers.

        Requires pandas, which is not a runtime dependency of this package.
        Band columns are keyed by ANSI band number; callers needing another
        labelling convention should rename them.
        """
        import pandas as pd

        frame = pd.DataFrame({"time_s": self.time_s})
        for index, name in enumerate(POI_BROADBAND_COLUMNS):
            frame[name] = self.broadband_db[:, index]
        bands = pd.DataFrame(
            self.band_levels_db,
            columns=pd.Index(self.band_numbers),
        )
        return pd.concat([frame, bands], axis=1)


def read_poi(path: str | Path) -> list[PoiTimeHistory]:
    """Parse an AAM ``.POI`` file into one entry per receiver, in file order.

    Band cells at or below :data:`AAM_NODATA_DB` become ``NaN``. Broadband
    columns are returned as written.
    """
    poi_path = Path(path)
    try:
        text = poi_path.read_text(errors="replace")
    except FileNotFoundError:
        raise ValueError(f"no such .POI file: {poi_path}") from None
    if not text.strip():
        raise ValueError(
            f"empty .POI file: {poi_path} "
            "(AAM writes no output when it rejects an input deck, "
            "so check the run log for a READ ERROR)"
        )

    band_numbers = _parse_band_numbers(text, poi_path)
    expected_columns = _LEADING_COLUMN_COUNT + len(band_numbers)

    zones = _split_zones(text, poi_path)
    histories: list[PoiTimeHistory] = []
    for zone_index, (declared, block) in enumerate(zones, start=1):
        rows = _parse_rows(block, expected_columns)
        if declared is not None and len(rows) != declared:
            raise ValueError(
                f"{poi_path}: ZONE {zone_index} declares I={declared} rows "
                f"but {len(rows)} were readable; the file may be truncated"
            )
        if not rows:
            raise ValueError(f"{poi_path}: ZONE {zone_index} has no data rows")

        table = np.asarray(rows, dtype=float)
        bands = table[:, _LEADING_COLUMN_COUNT:expected_columns]
        histories.append(
            PoiTimeHistory(
                zone_index=zone_index,
                time_s=table[:, 0],
                broadband_db=table[:, 1:_LEADING_COLUMN_COUNT],
                band_levels_db=np.where(bands <= AAM_NODATA_DB, np.nan, bands),
                band_numbers=band_numbers,
            )
        )

    if not histories:
        raise ValueError(f"{poi_path}: no ZONE blocks found")
    return histories


def _parse_band_numbers(text: str, poi_path: Path) -> tuple[int, ...]:
    """Map the ``VARIABLES`` header's band labels to ANSI band numbers."""
    match = _VARIABLES_RE.search(text)
    if match is None:
        raise ValueError(f"{poi_path}: missing VARIABLES header")

    names = _QUOTED_RE.findall(match.group(1))
    band_numbers = [
        band_number_for_frequency(float(freq.group(1)))
        for name in names
        if (freq := _FREQ_RE.search(name)) is not None
    ]
    if not band_numbers:
        raise ValueError(f"{poi_path}: no frequency bands in VARIABLES header")
    return tuple(band_numbers)


def _split_zones(text: str, poi_path: Path) -> list[tuple[int | None, str]]:
    """Return ``(declared_row_count, body)`` for each ZONE, in file order."""
    matches = list(_ZONE_RE.finditer(text))
    if not matches:
        raise ValueError(f"{poi_path}: no ZONE blocks found")

    zones: list[tuple[int | None, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        count = _ZONE_COUNT_RE.search(match.group("attrs"))
        zones.append((int(count.group(1)) if count else None, text[match.end() : end]))
    return zones


def _parse_rows(block: str, expected_columns: int) -> list[list[float]]:
    """Parse whitespace-separated float rows, skipping non-numeric lines."""
    rows: list[list[float]] = []
    for line in block.splitlines():
        fields = line.split()
        if len(fields) < expected_columns:
            continue
        try:
            rows.append([float(field) for field in fields[:expected_columns]])
        except ValueError:
            continue
    return rows
