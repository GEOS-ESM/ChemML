"""Offline cross-source and cross-partition database-manager fixtures."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from aqdatafusion.contracts import DatasetBundle
from aqdatafusion.data_acquisition.base import AcquisitionError
from aqdatafusion.data_management import DatabaseManager


class SyntheticAdapter:
    """Return deterministic data for the requested half-open interval."""

    def __init__(
        self,
        source_key: str,
        *,
        fail: bool = False,
        omit_first_timestamp: bool = False,
    ) -> None:
        self.source_key = source_key
        self.fail = fail
        self.omit_first_timestamp = omit_first_timestamp
        self.calls: list[tuple[pd.Timestamp, pd.Timestamp]] = []

    def acquire(self, request, configuration):
        start = pd.Timestamp(request.start_time)
        end = pd.Timestamp(request.end_time)
        if start.tzinfo is None:
            start = start.tz_localize("UTC")
        else:
            start = start.tz_convert("UTC")
        if end.tzinfo is None:
            end = end.tz_localize("UTC")
        else:
            end = end.tz_convert("UTC")
        self.calls.append((start, end))
        if self.fail:
            raise AcquisitionError("synthetic source unavailable", retryable=True)
        times = pd.date_range(start, end, freq="1h", inclusive="left")
        if self.source_key == "points":
            data = pd.DataFrame(
                {
                    "site_id": "ATL-1",
                    "lat": 33.75,
                    "lon": -84.39,
                    "time": times,
                    "value": np.arange(len(times), dtype=float),
                }
            )
        else:
            data = xr.Dataset(
                {"grid_value": (("time", "lat", "lon"), np.arange(len(times), dtype=float)[:, None, None])},
                coords={"time": times.tz_localize(None), "lat": [33.75], "lon": [-84.39]},
            )
        if self.omit_first_timestamp and len(self.calls) == 1:
            if isinstance(data, pd.DataFrame):
                data = data.iloc[1:].reset_index(drop=True)
            else:
                data = data.isel(time=slice(1, None))
        return DatasetBundle(self.source_key, data)


def _configuration(root: Path):
    return {
        "region": {"region_code": "ATL"},
        "aqdatafusion": {"inputs": {"points": {"enabled": True}, "grid": {"enabled": True}, "broken": {"enabled": True}}},
        "filepaths": {
            "data_sources": {
                "points": str(root / "points"),
                "grid": str(root / "grid"),
                "broken": str(root / "broken"),
            }
        },
        "input_data": {
            "datasets": {
                "points": {
                    "file_template": "points_{region_code}_{month_string}.csv",
                    "variables": ["site_id", "lat", "lon", "time", "value"],
                    "site_id": "site_id",
                    "coordinate_names": {"latitude": "lat", "longitude": "lon", "time": "time"},
                    "time": {"frequency": "1h", "tolerance": "0s", "availability": {"mode": "continuous"}},
                    "storage": {"partition": "monthly", "format": "csv", "catalog_filename": "catalog.json"},
                },
                "grid": {
                    "file_template": "grid_{region_code}_{month_string}.nc",
                    "variables": ["grid_value"],
                    "coordinate_names": {"latitude": "lat", "longitude": "lon", "time": "time"},
                    "time": {"frequency": "1h", "tolerance": "0s", "availability": {"mode": "continuous"}},
                    "storage": {"partition": "monthly", "format": "netcdf", "catalog_filename": "catalog.json"},
                },
                "broken": {
                    "file_template": "broken_{region_code}_{month_string}.nc",
                    "variables": ["value"],
                    "coordinate_names": {"latitude": "lat", "longitude": "lon", "time": "time"},
                    "time": {"frequency": "1h", "tolerance": "0s", "availability": {"mode": "continuous"}},
                    "storage": {"partition": "monthly", "format": "netcdf", "catalog_filename": "catalog.json"},
                },
            }
        },
    }


def _read_point_times(path: Path) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(pd.read_csv(path)["time"], utc=True))


def test_update_isolates_source_failure_and_writes_month_boundary(tmp_path):
    configuration = _configuration(tmp_path)
    adapters = {
        "points": SyntheticAdapter("points"),
        "grid": SyntheticAdapter("grid"),
        "broken": SyntheticAdapter("broken", fail=True),
    }
    manager = DatabaseManager(configuration, data_sources=adapters)

    report = manager.update(
        "2026-01-31T23:00:00Z",
        "2026-02-01T01:00:00Z",
    )

    assert report.sources["points"]["status"] == "updated"
    assert report.sources["grid"]["status"] == "updated"
    assert report.sources["broken"]["status"] == "failed"
    assert all(
        isinstance(report.sources[key]["wall_time_seconds"], float)
        and report.sources[key]["wall_time_seconds"] >= 0
        for key in ("points", "grid", "broken")
    )
    assert report.sources["broken"]["errors"][0]["retryable"] is True
    assert not list((tmp_path / "broken" / ".tmp").iterdir())
    assert len(adapters["points"].calls) == 1
    assert len(adapters["grid"].calls) == 1
    assert (tmp_path / "points" / "points_ATL_202601.csv").exists()
    assert (tmp_path / "points" / "points_ATL_202602.csv").exists()
    assert (tmp_path / "grid" / "grid_ATL_202601.nc").exists()
    assert (tmp_path / "grid" / "grid_ATL_202602.nc").exists()
    assert report.sources["points"]["integrity"]["valid"]
    assert report.sources["grid"]["integrity"]["valid"]


def test_overlapping_updates_fill_second_month_without_duplicates(tmp_path):
    configuration = _configuration(tmp_path)
    points = SyntheticAdapter("points")
    grid = SyntheticAdapter("grid")
    manager = DatabaseManager(
        configuration,
        data_sources={"points": points, "grid": grid},
    )

    manager.update(
        "2026-01-31T23:00:00Z",
        "2026-02-01T01:00:00Z",
        source_keys=["points", "grid"],
    )
    report = manager.update(
        "2026-02-01T00:00:00Z",
        "2026-02-01T02:00:00Z",
        source_keys=["points", "grid"],
    )

    assert report.sources["points"]["status"] == "updated"
    assert report.sources["grid"]["status"] == "updated"
    point_files = sorted((tmp_path / "points").glob("*.csv"))
    point_times = pd.DatetimeIndex([])
    for path in point_files:
        point_times = point_times.append(_read_point_times(path))
    assert len(point_times) == 3
    assert point_times.is_unique
    assert set(point_times) == set(pd.date_range("2026-01-31T23:00:00Z", periods=3, freq="1h"))
    with xr.open_mfdataset(sorted((tmp_path / "grid").glob("*.nc")), combine="by_coords") as dataset:
        assert dataset.sizes["time"] == 3
        assert pd.DatetimeIndex(pd.to_datetime(dataset.time.values, utc=True)).is_unique
    assert len(points.calls) == 2
    assert len(grid.calls) == 2


def test_partial_source_gap_is_warned_then_filled_on_a_later_update(tmp_path):
    configuration = _configuration(tmp_path)
    points = SyntheticAdapter("points", omit_first_timestamp=True)
    manager = DatabaseManager(configuration, data_sources={"points": points})

    first = manager.update(
        "2026-08-04T00:00:00Z",
        "2026-08-04T04:00:00Z",
        source_keys=["points"],
    )

    assert first.sources["points"]["status"] == "updated"
    assert first.sources["points"]["integrity"]["valid"]
    assert first.sources["points"]["integrity"]["checks"]["timestamps"]["missing"]
    assert any("unavailable or missing" in warning for warning in first.warnings)

    second = manager.update(
        "2026-08-04T00:00:00Z",
        "2026-08-04T04:00:00Z",
        source_keys=["points"],
    )

    assert second.sources["points"]["status"] == "updated"
    assert not second.sources["points"]["integrity"]["checks"]["timestamps"]["missing"]
    point_times = _read_point_times(tmp_path / "points" / "points_ATL_202608.csv")
    assert len(point_times) == 4
    assert point_times.is_unique
    assert len(points.calls) == 2


def test_update_crossing_year_boundary_uses_both_year_partitions(tmp_path):
    configuration = _configuration(tmp_path)
    adapters = {"points": SyntheticAdapter("points"), "grid": SyntheticAdapter("grid")}
    manager = DatabaseManager(configuration, data_sources=adapters)

    report = manager.update(
        "2027-12-31T23:00:00Z",
        "2028-01-01T02:00:00Z",
        source_keys=["points", "grid"],
    )

    assert all(report.sources[key]["integrity"]["valid"] for key in adapters)
    assert (tmp_path / "points" / "points_ATL_202712.csv").exists()
    assert (tmp_path / "points" / "points_ATL_202801.csv").exists()
    assert (tmp_path / "grid" / "grid_ATL_202712.nc").exists()
    assert (tmp_path / "grid" / "grid_ATL_202801.nc").exists()
    point_times = pd.DatetimeIndex([])
    for path in sorted((tmp_path / "points").glob("*.csv")):
        point_times = point_times.append(_read_point_times(path))
    assert len(point_times) == 3
    assert point_times.is_unique
    assert point_times.min() == pd.Timestamp("2027-12-31T23:00:00Z")
    assert point_times.max() == pd.Timestamp("2028-01-01T01:00:00Z")


@pytest.mark.parametrize(
    ("year", "expected_count", "has_leap_day"),
    [(2028, 27, True), (2027, 3, False)],
)
def test_update_handles_leap_and_non_leap_years(
    tmp_path, year, expected_count, has_leap_day
):
    configuration = _configuration(tmp_path)
    adapters = {"points": SyntheticAdapter("points"), "grid": SyntheticAdapter("grid")}
    manager = DatabaseManager(configuration, data_sources=adapters)
    start = f"{year}-02-28T23:00:00Z"
    end = f"{year}-03-01T02:00:00Z"

    report = manager.update(start, end, source_keys=["points", "grid"])

    assert all(report.sources[key]["integrity"]["valid"] for key in adapters)
    point_times = pd.DatetimeIndex([])
    for path in sorted((tmp_path / "points").glob("*.csv")):
        point_times = point_times.append(_read_point_times(path))
    assert len(point_times) == expected_count
    assert point_times.is_unique
    if has_leap_day:
        leap_day = pd.Timestamp(f"{year}-02-29T12:00:00Z")
        assert leap_day in point_times
    else:
        assert not any(timestamp.month == 2 and timestamp.day == 29 for timestamp in point_times)
    assert (tmp_path / "points" / f"points_ATL_{year}02.csv").exists()
    assert (tmp_path / "points" / f"points_ATL_{year}03.csv").exists()
