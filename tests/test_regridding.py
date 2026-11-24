"""Tests for the shared irregular-observation regridder."""

import numpy as np
import pandas as pd
import xarray as xr

from aqdatafusion.utils.regridding import regrid_irregular_to_grid


def _configuration():
    return {
        "region": {"bounds": {"latitude": [0.0, 2.0], "longitude": [0.0, 2.0]}},
        "input_data": {
            "datasets": {
                "satellite": {
                    "coordinate_names": {"latitude": "lat", "longitude": "lon"},
                    "regridding": {"latlon_resolution": 1.0},
                }
            }
        },
    }


def test_xarray_regridding_uses_dataset_resolution_and_leaves_empty_cells_nan():
    data = xr.Dataset(
        {
            "value": ("obs", [1.0, 3.0, 10.0]),
            "quality_flag": ("obs", [1, 1, 2]),
        },
        coords={
            "lat": ("obs", [0.1, 0.4, 1.2]),
            "lon": ("obs", [0.1, 0.4, 1.2]),
        },
        attrs={"source_key": "satellite"},
    )

    result = regrid_irregular_to_grid(data, _configuration(), categorical_variables=["quality_flag"])

    assert result.sizes["lat"] == 2
    assert result.sizes["lon"] == 2
    assert result["value"].sel(lat=0.5, lon=0.5).item() == 2.0
    assert result["quality_flag"].sel(lat=0.5, lon=0.5).item() == 1
    assert np.isnan(result["value"].sel(lat=0.5, lon=1.5).item())


def test_xarray_regridding_preserves_non_spatial_dimensions():
    data = xr.Dataset(
        {"value": (("time", "layer", "obs"), np.array([[[1.0, 3.0]], [[5.0, 7.0]]]))},
        coords={
            "time": ["2026-01-01T00:00", "2026-01-01T01:00"],
            "layer": [100.0],
            "lat": ("obs", [0.1, 0.4]),
            "lon": ("obs", [0.1, 0.4]),
        },
        attrs={"source_key": "satellite"},
    )

    result = regrid_irregular_to_grid(data, _configuration())

    assert result["value"].dims == ("time", "layer", "lat", "lon")
    assert result.sizes["time"] == 2
    assert result.sizes["layer"] == 1
    assert result["value"].sel(time="2026-01-01T01:00", layer=100.0, lat=0.5, lon=0.5).item() == 6.0


def test_dataframe_regridding_supports_explicit_source_key_and_modes():
    data = pd.DataFrame(
        {
            "lat": [0.1, 0.2, 1.1], "lon": [0.1, 0.2, 1.1],
            "value": [2.0, 4.0, 8.0], "flag": [3, 3, 4],
        }
    )

    result = regrid_irregular_to_grid(
        data, _configuration(), source_key="satellite", categorical_variables=["flag"]
    )

    first = result[(result["lat"] == 0.5) & (result["lon"] == 0.5)].iloc[0]
    assert first["value"] == 3.0
    assert first["flag"] == 3
