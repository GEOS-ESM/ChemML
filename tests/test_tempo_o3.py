"""Network-free tests for TEMPO O₃ profile acquisition and preprocessing."""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import xarray as xr

from aqforecast.contracts import DataRequest, DatasetBundle
from aqforecast.data_acquisition.tempo_o3 import SHORT_NAME, TempoO3ProfileDataSource
from aqforecast.preprocessing.tempo_o3 import TempoO3ProfilePreprocessor


def _configuration(tmp_path: Path) -> dict:
    return {
        "credentials": {"earthdata": {"username": "user", "password": "pass"}},
        "region": {"region_code": "ATL", "bounds": {"latitude": [33.0, 33.1], "longitude": [-85.0, -84.9]}},
        "filepaths": {"data_sources": {"TEMPO_O3": str(tmp_path / "source")}},
        "input_data": {"datasets": {"TEMPO_O3": {
            "source_key": "TEMPO_O3",
            "quality_control": {"cloud_fraction_max": 0.5, "solar_zenith_angle_max": 80.0, "viewing_zenith_angle_max": 80.0},
            "regridding": {"latlon_resolution": 0.04},
            "access": {"collection_short_name": SHORT_NAME, "concept_id": "C3685896402-LARC_CLOUD", "profile_layer": 24},
        }}}
    }


def _request() -> DataRequest:
    return DataRequest("TEMPO_O3", "ATL", ["ozone_profile_layer_24"], pd.Timestamp("2026-05-01", tz="UTC").to_pydatetime(), pd.Timestamp("2026-05-02", tz="UTC").to_pydatetime())


def _cached_dataset(start: str) -> xr.Dataset:
    return xr.Dataset(
        {
            "ozone_profile_layer_24": (("time", "latitude", "longitude"), [[[1.0, -2.0], [3.0, 4.0]]]),
            "eff_cloud_fraction": (("time", "latitude", "longitude"), [[[0.1, 0.6], [0.1, 0.1]]]),
            "solar_zenith_angle": (("time", "latitude", "longitude"), [[[20.0, 20.0], [81.0, 20.0]]]),
            "viewing_zenith_angle": (("time", "latitude", "longitude"), [[[20.0, 20.0], [20.0, 81.0]]]),
        },
        coords={"time": [0], "latitude": [33.02, 33.06], "longitude": [-84.98, -84.94]},
        attrs={"time_coverage_start": start, "profile_layer_number": 24},
    )


def test_tempo_o3_preprocessor_selects_qc_valid_layer_24(tmp_path: Path) -> None:
    path = tmp_path / "subset.nc"
    _cached_dataset("2026-05-01T17:03:00Z").to_netcdf(path)
    result = TempoO3ProfilePreprocessor().preprocess(DatasetBundle("TEMPO_O3", [path], {}), _configuration(tmp_path))

    assert result.data.sizes == {"time": 1, "lat": 2, "lon": 2}
    assert result.data.time.values[0] == np.datetime64("2026-05-01T17:30:00")
    assert result.data["ozone_profile_layer_24"].sel(lat=33.02, lon=-84.98).item() == 1.0
    assert int(result.data["ozone_profile_layer_24"].notnull().sum()) == 1
    assert result.data["valid_pixel_count"].item() == 1


def test_tempo_o3_preprocessor_supports_multiple_configured_layers(tmp_path: Path) -> None:
    path = tmp_path / "multi_layer_subset.nc"
    dataset = _cached_dataset("2026-05-01T17:03:00Z")
    for layer in (22, 1):
        dataset[f"ozone_profile_layer_{layer}"] = dataset["ozone_profile_layer_24"] + layer
    dataset.to_netcdf(path)
    configuration = _configuration(tmp_path)
    configuration["input_data"]["datasets"]["TEMPO_O3"]["profile_layers"] = [24, 22, 1]

    result = TempoO3ProfilePreprocessor().preprocess(
        DatasetBundle("TEMPO_O3", [path], {}), configuration
    )

    assert {"ozone_profile_layer_24", "ozone_profile_layer_22", "ozone_profile_layer_1"} <= set(result.data.data_vars)


def test_tempo_o3_acquisition_caches_three_opendap_groups(monkeypatch, tmp_path: Path) -> None:
    calls = []

    class Granule:
        def data_links(self):
            return ["https://data.example/TEMPO_O3PROF_L3_V04_20260501T170300Z_S001.nc"]

    monkeypatch.setitem(sys.modules, "earthaccess", SimpleNamespace(login=lambda **kwargs: True, search_data=lambda **kwargs: [Granule()]))

    class FakeClient:
        @classmethod
        def from_credentials(cls, credentials):
            return cls()

        def open_subset(self, url, **kwargs):
            calls.append(kwargs["group"])
            if kwargs["group"] == "product":
                return xr.Dataset({"ozone_profile": (("time", "latitude", "longitude", "layer"), np.ones((1, 2, 2, 24)))}, coords={"time": [0], "latitude": [33.02, 33.06], "longitude": [-84.98, -84.94], "layer": np.arange(24)}, attrs={"time_coverage_start": "2026-05-01T17:03:00Z"})
            names = ("eff_cloud_fraction",) if kwargs["group"] == "support_data" else ("solar_zenith_angle", "viewing_zenith_angle")
            return xr.Dataset({name: (("time", "latitude", "longitude"), np.ones((1, 2, 2))) for name in names}, coords={"time": [0], "latitude": [33.02, 33.06], "longitude": [-84.98, -84.94]}, attrs={"time_coverage_start": "2026-05-01T17:03:00Z"})

    monkeypatch.setattr("aqforecast.data_acquisition.tempo_o3.EarthdataOpenDAPClient", FakeClient)
    source = TempoO3ProfileDataSource()
    first = source.acquire(_request(), _configuration(tmp_path))
    second = source.acquire(_request(), _configuration(tmp_path))

    assert len(first.data) == len(second.data) == 1
    assert calls == ["product", "support_data", "geolocation"]
    source.cleanup(first)
    assert not list(Path(first.metadata["cached_subset_directory"]).glob("*.nc"))
