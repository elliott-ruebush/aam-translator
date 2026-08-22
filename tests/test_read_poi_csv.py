"""Unit tests for AAM ``.Single.POI.csv`` reader."""

from __future__ import annotations

from pathlib import Path

import pytest

from aam_translator.read_poi_csv import read_poi_summary_csv

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_single_poi.csv"


def test_read_poi_summary_csv_two_receivers_in_order() -> None:
    summaries = read_poi_summary_csv(_FIXTURE)
    assert len(summaries) == 2
    assert summaries[0].name == "Receiver"
    assert summaries[1].name == "Monitor"


def test_read_poi_summary_csv_coordinates() -> None:
    receiver = read_poi_summary_csv(_FIXTURE)[0]
    assert receiver.x_ft == pytest.approx(15102.12)
    assert receiver.y_ft == pytest.approx(5353.70)
    assert receiver.z_ft == pytest.approx(4.92)


def test_read_poi_summary_csv_metrics() -> None:
    receiver = read_poi_summary_csv(_FIXTURE)[0]
    assert receiver.metrics["Lmax_dBA"] == pytest.approx(59.13)
    assert receiver.metrics["SEL_dBA"] == pytest.approx(56.12)


def test_read_poi_summary_csv_op_name_not_in_metrics() -> None:
    receiver = read_poi_summary_csv(_FIXTURE)[0]
    assert "OpName" not in receiver.metrics


def test_poi_summary_metric_accessor() -> None:
    receiver = read_poi_summary_csv(_FIXTURE)[0]
    assert receiver.metric("Lmax_dBA") == pytest.approx(59.13)
    with pytest.raises(KeyError):
        receiver.metric("nope")


def test_read_poi_summary_csv_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("")
    with pytest.raises(ValueError, match="empty"):
        read_poi_summary_csv(path)


def test_read_poi_summary_csv_missing_x_column(tmp_path: Path) -> None:
    path = tmp_path / "no_x.csv"
    path.write_text("POIname,Y,Z\nReceiver,1.0,2.0\n")
    with pytest.raises(ValueError, match="missing required column"):
        read_poi_summary_csv(path)
