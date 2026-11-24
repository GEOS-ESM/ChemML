"""Regression tests for the shared plotting helpers."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pandas as pd
import xarray as xr

from aqdatafusion.utils.plotting import plot_data_map, prepare_cartopy_basemap


def test_prepare_cartopy_basemap_offline_reports_missing_layers(tmp_path: Path) -> None:
    result = prepare_cartopy_basemap(tmp_path / "cartopy", download=False)

    assert result["cache_directory"].endswith("cartopy")
    assert result["warnings"]


def test_plot_data_map_supports_xarray_without_basemap() -> None:
    data = xr.DataArray(
        np.arange(12, dtype=float).reshape(2, 2, 3),
        dims=("forecast_lead_day", "lat", "lon"),
        coords={"forecast_lead_day": [0, 1], "lat": [33.0, 34.0], "lon": [-84.5, -83.5, -82.5]},
        name="NO2",
    )

    figure, axes = plot_data_map(
        data,
        configuration={"region": {"bounds": {"latitude": [33, 35], "longitude": [-85, -83]}}},
        add_basemap=False,
    )

    assert figure is axes.figure
    assert axes.get_title() == ""
    figure.clf()


def test_plot_data_map_selects_nearest_timezone_normalized_timestamp() -> None:
    data = xr.DataArray(
        np.arange(6, dtype=float).reshape(2, 3),
        dims=("time", "lat"),
        coords={"time": pd.date_range("2026-08-05", periods=2, freq="1h"), "lat": [33.0, 34.0, 35.0]},
        name="NO2",
    )

    figure, axes = plot_data_map(
        data,
        timestamp="2026-08-05T00:20:00Z",
        add_basemap=False,
    )

    assert figure is axes.figure
    figure.clf()


def test_plot_data_map_supports_point_data() -> None:
    data = pd.DataFrame(
        {
            "lat": [33.5, 34.0],
            "lon": [-84.5, -83.5],
            "NO2": [10.0, 20.0],
            "time": pd.to_datetime(["2026-08-04T00:00:00Z"] * 2),
        }
    )

    figure, axes = plot_data_map(data, variable="NO2", add_basemap=False)

    assert figure is axes.figure
    figure.clf()


def test_plot_data_map_uses_nearest_ground_monitor_timestamp() -> None:
    data = pd.DataFrame(
        {
            "lat": [33.5, 34.0, 33.5, 34.0],
            "lon": [-84.5, -83.5, -84.5, -83.5],
            "NO2": [10.0, 20.0, 30.0, 40.0],
            "time": pd.to_datetime(
                [
                    "2026-08-05T14:30:00Z",
                    "2026-08-05T14:30:00Z",
                    "2026-08-05T15:30:00Z",
                    "2026-08-05T15:30:00Z",
                ]
            ),
        }
    )

    figure, axes = plot_data_map(
        data,
        variable="NO2",
        timestamp="2026-08-05T15:00:00Z",
        add_basemap=False,
    )

    assert axes.collections[0].get_offsets().shape[0] == 2
    figure.clf()
