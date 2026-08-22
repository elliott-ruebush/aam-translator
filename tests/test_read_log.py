"""Tests for reading AAM's post-run ``{basename}.txt`` log."""

from __future__ import annotations

from pathlib import Path

import pytest

from aam_translator.read_log import read_run_log

FIXTURES = Path(__file__).parent / "fixtures"
CLEAN_LOG = FIXTURES / "sample_run_log.txt"
ERROR_LOG = FIXTURES / "sample_read_error_log.txt"


def test_clean_log_reports_ok() -> None:
    log = read_run_log(CLEAN_LOG)
    assert log.read_error is None
    assert log.ok is True


def test_read_error_is_captured_with_detail() -> None:
    # AAM exits 0 on this failure, so the log is the only signal it happened.
    log = read_run_log(ERROR_LOG)
    assert log.ok is False
    assert log.read_error is not None
    assert "READ ERROR" in log.read_error
    assert "exceeds   400 You have entered >   500" in log.read_error


def test_read_error_log_has_no_analysis_track() -> None:
    log = read_run_log(ERROR_LOG)
    assert log.analysis_track is None
    assert log.declared_analysis_points is None


def test_analysis_track_parsed_by_column_name() -> None:
    log = read_run_log(CLEAN_LOG)
    assert log.declared_analysis_points == 3
    assert log.analysis_track is not None
    assert len(log.analysis_track) == 3

    first = log.analysis_track[0]
    assert first.time_s == pytest.approx(0.0)
    assert first.x_ft == pytest.approx(-9842.520)
    assert first.y_ft == pytest.approx(0.0)
    assert first.z_msl_ft == pytest.approx(3280.800)
    assert first.speed_kn == pytest.approx(136.100)

    last = log.analysis_track[-1]
    assert last.time_s == pytest.approx(2.8566)
    assert last.x_ft == pytest.approx(-9186.350)


def test_terrain_and_impedance_extents() -> None:
    log = read_run_log(CLEAN_LOG)
    assert log.elevation is not None
    assert log.elevation.title == "AAM elevation grid"
    assert log.elevation.lower_left == pytest.approx((0.0, 0.0))
    assert log.elevation.spacing == pytest.approx((98.43, 98.43))
    assert log.elevation.grid_size == (304, 109)
    assert log.elevation.upper_right == pytest.approx((29921.26, 10728.35))
    assert log.elevation.units == "FEET"

    assert log.impedance is not None
    assert log.impedance.title == "AAM impedance grid"
    assert log.impedance.grid_size == (304, 109)
    assert log.impedance.units == "FEET"


def test_missing_terrain_blocks_return_none() -> None:
    log = read_run_log(ERROR_LOG)
    assert log.elevation is None
    assert log.impedance is None


def test_raw_text_is_preserved() -> None:
    log = read_run_log(CLEAN_LOG)
    assert log.raw_text == CLEAN_LOG.read_text()
    assert "POINT OF INTEREST RESULTS" in log.raw_text


def test_missing_log_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no such AAM run log"):
        read_run_log(tmp_path / "absent.txt")
