"""Regression tests for site-aware point-data database management."""

import pandas as pd
import pytest

from aqforecast.data_management import DatabaseManager

SOURCE = {
    "site_id": "site_id",
    "site_coordinate_tolerance": 1e-6,
    "coordinate_names": {
        "latitude": "lat",
        "longitude": "lon",
        "time": "time",
    },
}


def _manager() -> DatabaseManager:
    return DatabaseManager(
        {"filepaths": {"data_sources": {"stations": "/tmp/stations"}}}
    )


def test_point_merge_uses_site_id_as_identity() -> None:
    manager = _manager()
    existing = pd.DataFrame(
        [
            {
                "site_id": "A",
                "lat": 1.0,
                "lon": 2.0,
                "time": "2025-01-01T00:00:00Z",
                "value": 1.0,
            },
            {
                "site_id": "B",
                "lat": 1.0,
                "lon": 2.0,
                "time": "2025-01-01T00:00:00Z",
                "value": 2.0,
            },
        ]
    )
    incoming = pd.DataFrame(
        [
            {
                "site_id": "A",
                "lat": 1.0,
                "lon": 2.0,
                "time": "2025-01-01T00:00:00Z",
                "value": 3.0,
            }
        ]
    )

    merged = manager._merge(existing, incoming, SOURCE, "fill_missing")

    assert len(merged) == 2
    assert merged.set_index("site_id").loc["A", "value"] == 1.0
    assert merged.set_index("site_id").loc["B", "value"] == 2.0


def test_site_coordinate_mismatch_is_rejected() -> None:
    manager = _manager()
    existing = pd.DataFrame(
        [
            {
                "site_id": "A",
                "lat": 1.0,
                "lon": 2.0,
                "time": "2025-01-01T00:00:00Z",
                "value": 1.0,
            }
        ]
    )
    incoming = pd.DataFrame(
        [
            {
                "site_id": "A",
                "lat": 1.1,
                "lon": 2.0,
                "time": "2025-01-01T01:00:00Z",
                "value": 2.0,
            }
        ]
    )

    with pytest.raises(ValueError, match="coordinates do not match"):
        manager._merge(existing, incoming, SOURCE, "fill_missing")


def test_missing_times_are_identified_per_site() -> None:
    manager = _manager()
    existing = pd.DataFrame(
        [
            {
                "site_id": "A",
                "lat": 1.0,
                "lon": 2.0,
                "time": "2025-01-01T00:00:00Z",
            },
            {
                "site_id": "B",
                "lat": 1.0,
                "lon": 2.0,
                "time": "2025-01-01T00:00:00Z",
            },
        ]
    )
    expected = pd.date_range("2025-01-01T00:00:00Z", periods=2, freq="1h")

    missing, site_ids = manager._missing_site_times(
        expected, existing, SOURCE, "0s"
    )

    assert list(missing) == [pd.Timestamp("2025-01-01T01:00:00Z")]
    assert site_ids == ["A", "B"]


def test_empty_point_database_has_no_observed_times() -> None:
    manager = _manager()

    observed = manager._observed_times(pd.DataFrame(), SOURCE)

    assert observed.empty


def test_missing_times_accepts_naive_observed_timestamps() -> None:
    manager = _manager()
    expected = pd.date_range("2025-01-01T00:00:00Z", periods=2, freq="1h")
    observed = pd.DatetimeIndex([pd.Timestamp("2025-01-01 00:00:00")])

    missing = manager._missing_times(expected, observed, "0s")

    assert list(missing) == [pd.Timestamp("2025-01-01T01:00:00Z")]
