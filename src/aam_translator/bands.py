"""ANSI one-third-octave band numbers and nominal center frequencies.

AAM's ``.POI`` header names its spectral columns by nominal center frequency
(``"f   16.0Hz"``), so reading that file requires mapping those labels back to
ANSI band numbers. The exact center of band ``n`` is ``10 ** (n / 10)`` Hz; the
nominal values below are the ISO preferred roundings that AAM prints.
"""

from __future__ import annotations

import math

# ANSI band number -> ISO preferred (nominal) center frequency in Hz.
NOMINAL_CENTER_HZ: dict[int, float] = {
    10: 10.0,
    11: 12.5,
    12: 16.0,
    13: 20.0,
    14: 25.0,
    15: 31.5,
    16: 40.0,
    17: 50.0,
    18: 63.0,
    19: 80.0,
    20: 100.0,
    21: 125.0,
    22: 160.0,
    23: 200.0,
    24: 250.0,
    25: 315.0,
    26: 400.0,
    27: 500.0,
    28: 630.0,
    29: 800.0,
    30: 1000.0,
    31: 1250.0,
    32: 1600.0,
    33: 2000.0,
    34: 2500.0,
    35: 3150.0,
    36: 4000.0,
    37: 5000.0,
    38: 6300.0,
    39: 8000.0,
    40: 10000.0,
    41: 12500.0,
    42: 16000.0,
}

# Bands AAM emits in a ``.POI`` spectral time history: 10 Hz .. 10 kHz.
AAM_BAND_NUMBERS: tuple[int, ...] = tuple(range(10, 41))


def band_number_for_frequency(freq_hz: float) -> int:
    """Return the nearest ANSI band number for a center frequency in Hz."""
    if freq_hz <= 0.0:
        raise ValueError(f"band center frequency must be positive, got {freq_hz!r}")
    return int(round(10.0 * math.log10(freq_hz)))


def band_label(band_number: int) -> str:
    """Return a human-readable nominal-frequency label, e.g. ``"1.25 kHz"``."""
    freq = NOMINAL_CENTER_HZ.get(band_number)
    if freq is None:
        raise ValueError(f"unknown ANSI band number {band_number!r}")
    if freq < 1000.0:
        return f"{freq:g} Hz"
    return f"{freq / 1000.0:g} kHz"
