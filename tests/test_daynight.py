"""Tests for ``critter_counter.daynight``."""

import pytest

from critter_counter.daynight import DAY, NIGHT, DayNightMonitor


def test_first_reading_decides_at_once():
    """No confirmation is needed for the starting mode."""
    assert DayNightMonitor().update(lux=300) == DAY
    assert DayNightMonitor().update(lux=2) == NIGHT
    assert DayNightMonitor().update(lux=None) == DAY


def test_day_to_night_needs_confirmed_readings():
    """Dark readings must come `confirm` times in a row."""
    m = DayNightMonitor(night_below_lux=10, day_above_lux=40, confirm=3)
    m.update(lux=300)
    assert m.update(lux=5) is None
    assert m.update(lux=5) is None
    assert m.votes == 2
    assert m.update(lux=5) == NIGHT
    assert m.mode == NIGHT and m.votes == 0


def test_interrupted_votes_start_over():
    """One bright reading in between resets the count (a passing shadow)."""
    m = DayNightMonitor(confirm=2)
    m.update(lux=300)
    m.update(lux=5)
    m.update(lux=300)
    assert m.votes == 0
    assert m.update(lux=5) is None


def test_hysteresis_gap_does_not_switch():
    """Between the two thresholds neither mode wants to switch."""
    m = DayNightMonitor(night_below_lux=10, day_above_lux=40, confirm=1)
    m.update(lux=2)
    for lux in (15, 25, 39.9):
        assert m.update(lux=lux) is None
    assert m.update(lux=41) == DAY
    for lux in (39, 20, 10):
        assert m.update(lux=lux) is None
    assert m.update(lux=9) == NIGHT


def test_overexposure_switches_night_to_day():
    """At dawn an over-exposed night frame votes for day, even without Lux."""
    m = DayNightMonitor(confirm=2, overexposed_level=200)
    m.update(lux=2)
    assert m.update(lux=None, brightness=230) is None
    assert m.update(lux=None, brightness=230) == DAY


def test_brightness_ignored_by_day():
    """By day a bright frame is normal and never votes."""
    m = DayNightMonitor(confirm=1)
    m.update(lux=300)
    assert m.update(lux=300, brightness=250) is None


def test_missing_lux_by_day_never_switches():
    """Without Lux the monitor stays in day mode."""
    m = DayNightMonitor(confirm=1)
    m.update(lux=None)
    assert m.update(lux=None, brightness=5) is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"night_below_lux": -1},
        {"night_below_lux": 40, "day_above_lux": 40},
        {"confirm": 0},
        {"confirm": True},
        {"overexposed_level": 0},
        {"overexposed_level": 300},
    ],
)
def test_invalid_arguments(kwargs):
    """Out-of-range settings are rejected."""
    with pytest.raises(ValueError):
        DayNightMonitor(**kwargs)
