"""Regression tests for site-aware point-data database management."""

import pandas as pd
import pytest
import xarray as xr

from aqdatafusion.data_management import DatabaseManager

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
    assert merged.set_index("site_id").loc["A", "value"] == 3.0
    assert merged.set_index("site_id").loc["B", "value"] == 2.0


def test_point_merge_normalizes_site_id_types_and_keeps_newest_row() -> None:
    manager = _manager()
    existing = pd.DataFrame(
        [
            {
                "site_id": 130590002,
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
                "site_id": "130590002",
                "lat": 1.0,
                "lon": 2.0,
                "time": "2025-01-01T00:00:00Z",
                "value": 9.0,
            }
        ]
    )

    merged = manager._merge(existing, incoming, SOURCE, "fill_missing")

    assert len(merged) == 1
    assert merged.iloc[0]["site_id"] == "130590002"
    assert merged.iloc[0]["value"] == 9.0


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


def test_yearly_missing_times_accept_a_fallback_source_year() -> None:
    manager = _manager()
    source = {
        "time": {"availability": {"mode": "yearly"}},
        "access": {"max_year_fallback": 2},
    }
    expected = pd.DatetimeIndex([pd.Timestamp("2026-01-01", tz="UTC")])
    observed = pd.DatetimeIndex([pd.Timestamp("2025-01-01", tz="UTC")])

    missing = manager._missing_times(expected, observed, "0s", source)

    assert len(missing) == 0


def test_yearly_partitions_use_year_start_timestamps() -> None:
    manager = _manager()
    source = {"storage": {"partition": "yearly"}}

    partitions = list(
        manager._partitions(
            pd.DatetimeIndex([pd.Timestamp("2025-08-04", tz="UTC")]), source
        )
    )

    assert partitions == [pd.Timestamp("2025-01-01", tz="UTC")]


def test_daily_grid_merge_uses_calendar_date_for_overpass_times() -> None:
    manager = _manager()
    source = {
        "coordinate_names": {"time": "time"},
        "time": {"aggregation": "daily_mean"},
    }
    existing = xr.Dataset(
        {"no2": (("time", "lat", "lon"), [[[1.0]]]), "o3": (("time", "lat", "lon"), [[[float("nan")]]])},
        coords={"time": ["2026-05-02T18:30:00"], "lat": [33.025], "lon": [-84.975]},
    )
    incoming = xr.Dataset(
        {"no2": (("time", "lat", "lon"), [[[float("nan")]]]), "o3": (("time", "lat", "lon"), [[[2.0]]])},
        coords={"time": ["2026-05-02T17:30:00"], "lat": [33.025], "lon": [-84.975]},
    )

    merged = manager._merge(existing, incoming, source, "fill_missing")

    assert merged.sizes["time"] == 1
    assert merged["no2"].item() == 1.0
    assert merged["o3"].item() == 2.0
    assert merged.time.dtype.kind == "M"


def test_daily_window_is_clipped_to_requested_utc_interval() -> None:
    manager = _manager()
    source = {
        "time": {
            "frequency": "1h",
            "timestamp_convention": "center",
            "availability": {
                "mode": "daily_window",
                "start": "07:00",
                "end": "19:00",
                "timezone": "US/Eastern",
            },
        }
    }
    start = pd.Timestamp("2026-08-04T00:00:00Z")
    end = pd.Timestamp("2026-08-08T00:00:00Z")

    expected = manager._expected_times(source, start, end)

    assert expected.min() >= start
    assert expected.max() < end
    assert not any(value.date() == pd.Timestamp("2026-08-03").date() for value in expected)


def test_xarray_merge_resolves_duplicate_incoming_timestamps() -> None:
    manager = _manager()
    source = {"coordinate_names": {"time": "time"}}
    existing = xr.Dataset(
        {"value": (("time", "lat", "lon"), [[[1.0]]])},
        coords={"time": ["2026-08-04T10:30:00"], "lat": [33.01], "lon": [-84.99]},
    )
    incoming = xr.Dataset(
        {"value": (("time", "lat", "lon"), [[[float("nan")]]])},
        coords={"time": ["2026-08-04T10:30:00"], "lat": [33.01], "lon": [-84.99]},
    )

    merged = manager._merge(existing, incoming, source, "fill_missing")

    assert merged.sizes["time"] == 1
    assert merged["value"].item() == 1.0
    assert merged.time.dtype.kind == "M"


def test_xarray_merge_normalizes_numeric_cf_time_coordinate() -> None:
    manager = _manager()
    source = {"coordinate_names": {"time": "time"}}
    existing = xr.Dataset(
        {"value": (("time", "lat", "lon"), [[[1.0]]])},
        coords={"time": [0.0], "lat": [33.01], "lon": [-84.99]},
    )
    existing.time.encoding["units"] = "days since 2026-08-04 00:00:00"
    incoming = xr.Dataset(
        {"value": (("time", "lat", "lon"), [[[2.0]]])},
        coords={"time": ["2026-08-05T00:00:00"], "lat": [33.01], "lon": [-84.99]},
    )

    merged = manager._merge(existing, incoming, source, "fill_missing")

    assert merged.time.dtype.kind == "M"
    assert list(merged.time.values) == [
        pd.Timestamp("2026-08-04T00:00:00").to_datetime64(),
        pd.Timestamp("2026-08-05T00:00:00").to_datetime64(),
    ]
