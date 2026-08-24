"""Tests for reading AAM ``.POI`` spectral time histories."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from aam_translator.bands import band_label, band_number_for_frequency
from aam_translator.read_poi import POI_BROADBAND_COLUMNS, read_poi

FIXTURE = Path(__file__).parent / "fixtures" / "sample_two_zone.POI"


def test_read_poi_returns_one_history_per_zone() -> None:
    histories = read_poi(FIXTURE)
    assert len(histories) == 2
    assert [h.zone_index for h in histories] == [1, 2]
    assert [h.n_samples for h in histories] == [3, 2]


def test_read_poi_band_numbers_from_variables_header() -> None:
    first, second = read_poi(FIXTURE)
    assert first.band_numbers == (10, 11, 12, 13)
    assert second.band_numbers == first.band_numbers


def test_read_poi_time_and_broadband_columns() -> None:
    first = read_poi(FIXTURE)[0]
    np.testing.assert_allclose(first.time_s, [9.33, 10.47, 11.62])
    assert first.broadband_db.shape == (3, len(POI_BROADBAND_COLUMNS))
    np.testing.assert_allclose(first.broadband("dBA"), [99.80, 100.30, 100.82])
    np.testing.assert_allclose(first.broadband("SPL"), [115.13, 115.39, 115.66])


def test_read_poi_sentinel_becomes_nan() -> None:
    first = read_poi(FIXTURE)[0]
    # Row 0 has one sentinel band, row 1 has two, row 2 has none.
    assert np.isnan(first.band_levels_db[0, 3])
    assert np.count_nonzero(np.isnan(first.band_levels_db[1])) == 2
    assert not np.isnan(first.band_levels_db[2]).any()
    np.testing.assert_allclose(first.band_levels_db[2, 0], 106.051)


def test_read_poi_broadband_columns_keep_raw_values() -> None:
    # Sentinels appear only in band columns; broadband must not be masked.
    second = read_poi(FIXTURE)[1]
    assert not np.isnan(second.broadband_db).any()


def test_read_poi_preserves_non_monotonic_row_order() -> None:
    # Zone 2 has a decreasing arrival time. AAM writes rows in track order, so a
    # reader that sorted by time would silently corrupt the row-to-source mapping.
    second = read_poi(FIXTURE)[1]
    np.testing.assert_allclose(second.time_s, [7.99, 6.99])
    np.testing.assert_allclose(second.broadband("dBA"), [17.38, 59.13])


def test_read_poi_unknown_broadband_column_raises() -> None:
    first = read_poi(FIXTURE)[0]
    with pytest.raises(KeyError, match="unknown broadband column"):
        first.broadband("dBZ")


def test_read_poi_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no such .POI file"):
        read_poi(tmp_path / "absent.POI")


def test_read_poi_empty_file_raises(tmp_path: Path) -> None:
    empty = tmp_path / "scenario.POI"
    empty.write_text("")
    with pytest.raises(ValueError, match="empty .POI file"):
        read_poi(empty)


def test_read_poi_missing_variables_header_raises(tmp_path: Path) -> None:
    bad = tmp_path / "scenario.POI"
    bad.write_text('TITLE = "x"\nZONE I=   1 F=POINT\n   1.0   2.0\n')
    with pytest.raises(ValueError, match="missing VARIABLES header"):
        read_poi(bad)


def test_read_poi_truncated_zone_raises(tmp_path: Path) -> None:
    text = FIXTURE.read_text().splitlines()
    truncated = tmp_path / "scenario.POI"
    # Drop the last data row of zone 2 while leaving its I=2 declaration.
    truncated.write_text("\n".join(text[:-1]) + "\n")
    with pytest.raises(ValueError, match="declares I=2 rows but 1 were readable"):
        read_poi(truncated)


def test_read_poi_no_zones_raises(tmp_path: Path) -> None:
    bad = tmp_path / "scenario.POI"
    bad.write_text('TITLE = "x"\nVARIABLES = "Time" "f   10.0Hz"\n')
    with pytest.raises(ValueError, match="no ZONE blocks found"):
        read_poi(bad)


def test_band_number_for_frequency_matches_aam_labels() -> None:
    assert band_number_for_frequency(10.0) == 10
    assert band_number_for_frequency(12.5) == 11
    assert band_number_for_frequency(16.0) == 12
    assert band_number_for_frequency(1000.0) == 30
    assert band_number_for_frequency(10000.0) == 40


def test_band_number_for_frequency_rejects_nonpositive() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        band_number_for_frequency(0.0)


def test_band_label() -> None:
    assert band_label(12) == "16 Hz"
    assert band_label(30) == "1 kHz"
    assert band_label(31) == "1.25 kHz"
    with pytest.raises(ValueError, match="unknown ANSI band number"):
        band_label(99)
