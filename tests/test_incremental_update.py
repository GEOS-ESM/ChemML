"""Tests for the rolling database-update orchestration helper."""

import pandas as pd
import pytest

from aqforecast.orchestration import run_incremental_database_update


class RecordingManager:
    def __init__(self, configuration, *, data_sources=None, preprocessors=None):
        self.calls = []

    def update(self, start_time, end_time, **kwargs):
        self.calls.append((start_time, end_time, kwargs))

        class Report:
            def as_dict(self):
                return {"start_time": str(start_time), "end_time": str(end_time), "sources": {}, "warnings": []}

        return Report()


def _configuration():
    return {
        "aqforecast": {
            "database": {
                "default_conflict_policy": "preserve_existing",
                "incremental_update": {
                    "lookback_days": 2,
                    "lookahead_days": 5,
                    "max_window_days": 14,
                    "timezone": "UTC",
                    "time_alignment": "hour",
                },
            }
        }
    }


def test_incremental_update_uses_aligned_rolling_window(monkeypatch):
    manager = RecordingManager(_configuration())
    monkeypatch.setattr(
        "aqforecast.orchestration.database_update.DatabaseManager",
        lambda configuration, **kwargs: manager,
    )

    result = run_incremental_database_update(
        _configuration(),
        now="2026-11-18T14:37:42-05:00",
        source_keys=["GEOS-CF"],
    )

    start, end, options = manager.calls[0]
    assert start == pd.Timestamp("2026-11-16T19:00:00Z").to_pydatetime()
    assert end == pd.Timestamp("2026-11-23T19:00:00Z").to_pydatetime()
    assert options["source_keys"] == ["GEOS-CF"]
    assert options["conflict_policy"] == "preserve_existing"
    assert result["incremental_update"]["anchor_time"] == "2026-11-18T19:00:00+00:00"


def test_incremental_update_rejects_window_over_maximum():
    configuration = _configuration()
    configuration["aqforecast"]["database"]["incremental_update"]["max_window_days"] = 6

    with pytest.raises(ValueError, match="exceeds max_window_days"):
        run_incremental_database_update(configuration, now="2026-11-18T00:00:00Z")


@pytest.mark.parametrize(
    ("setting", "value", "message"),
    [
        ("lookback_days", -1, "lookback_days"),
        ("lookahead_days", 0, "lookahead_days"),
        ("timezone", "America/New_York", "timezone"),
        ("time_alignment", "day", "time_alignment"),
    ],
)
def test_incremental_update_rejects_invalid_settings(setting, value, message):
    configuration = _configuration()
    configuration["aqforecast"]["database"]["incremental_update"][setting] = value

    with pytest.raises(ValueError, match=message):
        run_incremental_database_update(configuration, now="2026-11-18T00:00:00Z")
