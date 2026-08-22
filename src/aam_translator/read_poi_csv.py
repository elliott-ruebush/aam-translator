"""Read AAM's ``{basename}.Single.POI.csv`` per-receiver metrics summary."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

POI_CSV_NAME_FIELD = "POIname"
POI_CSV_COORD_FIELDS = ("X", "Y", "Z")

_SKIP_METRIC_FIELDS = frozenset({POI_CSV_NAME_FIELD, "OpName", *POI_CSV_COORD_FIELDS})


@dataclass(frozen=True)
class PoiSummary:
    """Event-integrated metrics for one POI receiver."""

    name: str
    x_ft: float
    y_ft: float
    z_ft: float
    metrics: dict[str, float]

    def metric(self, name: str) -> float:
        """Return one metric by column name, e.g. ``"Lmax_dBA"``."""
        return self.metrics[name]


def read_poi_summary_csv(path: str | Path) -> list[PoiSummary]:
    """Parse a ``.Single.POI.csv`` file, one entry per POI receiver in file order."""
    file_path = Path(path)
    with file_path.open(newline="") as fp:
        if not fp.read(1):
            raise ValueError(f"POI CSV file is empty: {file_path}")
        fp.seek(0)
        reader = csv.DictReader(fp)
        if reader.fieldnames is None:
            raise ValueError(f"POI CSV header row is missing: {file_path}")
        fieldnames = list(reader.fieldnames)
        _validate_required_columns(fieldnames, file_path)
        return [_parse_poi_row(row, fieldnames) for row in reader]


def _validate_required_columns(fieldnames: list[str], file_path: Path) -> None:
    missing = [
        field
        for field in (POI_CSV_NAME_FIELD, *POI_CSV_COORD_FIELDS)
        if field not in fieldnames
    ]
    if missing:
        raise ValueError(f"POI CSV missing required column(s) {missing}: {file_path}")


def _parse_poi_row(row: dict[str, str | None], fieldnames: list[str]) -> PoiSummary:
    name = _required_text(row, POI_CSV_NAME_FIELD)
    x_ft = _required_float(row, "X")
    y_ft = _required_float(row, "Y")
    z_ft = _required_float(row, "Z")
    metrics: dict[str, float] = {}
    for column in fieldnames:
        if column in _SKIP_METRIC_FIELDS:
            continue
        value = row.get(column)
        if value is None:
            continue
        stripped = value.strip()
        if not stripped:
            continue
        try:
            metrics[column] = float(stripped)
        except ValueError:
            continue
    return PoiSummary(
        name=name,
        x_ft=x_ft,
        y_ft=y_ft,
        z_ft=z_ft,
        metrics=metrics,
    )


def _required_text(row: dict[str, str | None], column: str) -> str:
    value = row.get(column)
    if value is None:
        raise ValueError(f"POI CSV row missing required column {column!r}")
    return value.strip()


def _required_float(row: dict[str, str | None], column: str) -> float:
    value = row.get(column)
    if value is None:
        raise ValueError(f"POI CSV row missing required column {column!r}")
    return float(value.strip())
