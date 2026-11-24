"""Network-free tests for TEMPO OpenDAP acquisition and preprocessing."""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import xarray as xr

from aqdatafusion.contracts import DataRequest, DatasetBundle
from aqdatafusion.data_acquisition.tempo import SHORT_NAME, TempoNo2DataSource
from aqdatafusion.preprocessing.tempo import TempoNo2Preprocessor


def _configuration(tmp_path: Path) -> dict:
    return {
        "credentials": {"earthdata": {"username": "user", "password": "pass"}},
        "region": {
            "region_code": "ATL",
            "bounds": {"latitude": [33.0, 33.1], "longitude": [-85.0, -84.9]},
        },
        "filepaths": {"data_sources": {"TEMPO_NO2": str(tmp_path / "source")}},
        "input_data": {
            "datasets": {
                "TEMPO_NO2": {
                    "source_key": "TEMPO_NO2",
                    "quality_control": {"quality_flag_max": 1},
                    "regridding": {"latlon_resolution": 0.02},
                    "access": {
                        "collection_short_name": SHORT_NAME,
                        "concept_id": "C3685896708-LARC_CLOUD",
                        "group": "product",
                        "variables": [
                            "vertical_column_troposphere",
                            "main_data_quality_flag",
                        ],
                    },
                }
            }
        },
    }


def _request() -> DataRequest:
    return DataRequest(
        "TEMPO_NO2",
        "ATL",
        ["vertical_column_troposphere"],
        pd.Timestamp("2026-05-01", tz="UTC").to_pydatetime(),
        pd.Timestamp("2026-05-02", tz="UTC").to_pydatetime(),
    )


def _subset(start: str) -> xr.Dataset:
    return xr.Dataset(
        {
            "vertical_column_troposphere": (
                ("time", "latitude", "longitude"),
                [[[1.0, -2.0], [3.0, 4.0]]],
            ),
            "main_data_quality_flag": (
                ("time", "latitude", "longitude"),
                [[[0, 1], [2, 0]]],
            ),
        },
        coords={
            "time": [0],
            "latitude": [33.01, 33.03],
            "longitude": [-84.99, -84.97],
        },
        attrs={"time_coverage_start": start},
    )


def test_tempo_preprocessor_qc_and_hourly_aggregation(tmp_path: Path) -> None:
    first = tmp_path / "first.nc"
    second = tmp_path / "second.nc"
    _subset("2026-05-01T17:03:00Z").to_netcdf(first)
    _subset("2026-05-01T17:22:00Z").to_netcdf(second)

    result = TempoNo2Preprocessor().preprocess(
        DatasetBundle("TEMPO_NO2", [first, second], {}), _configuration(tmp_path)
    )

    assert result.data.sizes == {"time": 1, "lat": 2, "lon": 2}
    assert result.data.time.values[0] == np.datetime64("2026-05-01T17:30:00")
    assert int(result.data["vertical_column_troposphere"].notnull().sum()) == 3
    assert result.data["vertical_column_troposphere"].sel(lat=33.01, lon=-84.99).item() == 1.0
    assert result.data["valid_pixel_count"].item() == 6
    assert result.metadata["timestamps_utc"] is True


def test_tempo_acquisition_caches_open_dap_subsets(monkeypatch, tmp_path: Path) -> None:
    calls = []

    class Granule:
        def data_links(self):
            return ["https://data.example/TEMPO_NO2_L3_V04_20260501T170300Z_S001.nc"]

    fake_earthaccess = SimpleNamespace(
        login=lambda **kwargs: True,
        search_data=lambda **kwargs: [Granule()],
    )
    monkeypatch.setitem(sys.modules, "earthaccess", fake_earthaccess)

    class FakeClient:
        @classmethod
        def from_credentials(cls, credentials):
            return cls()

        def open_subset(self, url, **kwargs):
            calls.append((url, kwargs))
            return _subset("2026-05-01T17:03:00Z")

    monkeypatch.setattr(
        "aqdatafusion.data_acquisition.tempo.EarthdataOpenDAPClient", FakeClient
    )
    configuration = _configuration(tmp_path)
    source = TempoNo2DataSource()
    first = source.acquire(_request(), configuration)
    second = source.acquire(_request(), configuration)

    assert len(first.data) == len(second.data) == 1
    assert len(calls) == 1
    assert first.metadata["cached_subset_directory"].endswith("source/.tmp")

    source.cleanup(first)
    assert not list(Path(first.metadata["cached_subset_directory"]).glob("*.nc"))
