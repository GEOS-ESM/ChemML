"""Network-free tests for TROPOMI acquisition and preprocessing."""

from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import xarray as xr
from netCDF4 import Dataset

from aqdatafusion.contracts import DataRequest, DatasetBundle
from aqdatafusion.data_acquisition.tropomi import (
    NO2_SHORT_NAME,
    O3_SHORT_NAME,
    TropomiDataSource,
)
from aqdatafusion.preprocessing.tropomi import TropomiPreprocessor


def _configuration():
    return {
        "credentials": {"earthdata": {"username": "user", "password": "pass"}},
        "region": {
            "region_code": "ATL",
            "bounds": {"latitude": [33.0, 34.0], "longitude": [-85.0, -84.0]},
        },
        "input_data": {
            "datasets": {
                "TROPOMI": {
                    "source_key": "TROPOMI",
                    "variables": ["tropospheric_no2_column", "total_o3_column"],
                    "coordinate_names": {"latitude": "lat", "longitude": "lon", "time": "time"},
                    "quality_control": {
                        "qa_min": 0.5,
                        "cloud_fraction_max": 0.5,
                        "solar_zenith_angle_max": 80.0,
                        "no2_min": -5e-5,
                        "o3_min": 0.05,
                        "o3_max": 0.25,
                    },
                    "regridding": {"latlon_resolution": 0.5},
                    "access": {"collection_version": "2"},
                }
            }
        },
    }


def _write_granule(path: Path, product: str) -> None:
    with Dataset(path, "w") as root:
        product_group = root.createGroup("PRODUCT")
        support = product_group.createGroup("SUPPORT_DATA")
        geo = support.createGroup("GEOLOCATIONS")
        inputs = support.createGroup("INPUT_DATA")
        details = support.createGroup("DETAILED_RESULTS")
        for group in (product_group, geo, inputs, details):
            group.createDimension("time", 1)
            group.createDimension("scanline", 2)
            group.createDimension("ground_pixel", 2)
        product_group.createDimension("string_length", 24)
        product_group.createDimension("corner", 4)

        def variable(group, name, dtype="f4"):
            return group.createVariable(name, dtype, ("time", "scanline", "ground_pixel"))

        latitude = variable(product_group, "latitude")
        longitude = variable(product_group, "longitude")
        latitude[:] = [[[33.1, 33.2], [33.6, 33.7]]]
        longitude[:] = [[[-84.9, -84.8], [-84.4, -84.3]]]
        qa = variable(product_group, "qa_value")
        qa[:] = 1.0
        solar = variable(geo, "solar_zenith_angle")
        solar[:] = 20.0
        cloud = variable(
            details if product == "no2" else inputs,
            "cloud_fraction_crb_nitrogendioxide_window" if product == "no2" else "cloud_fraction_crb",
        )
        cloud[:] = [[[0.1, 0.6], [0.1, 0.1]]]
        time_utc = product_group.createVariable("time_utc", str, ("time", "scanline"))
        time_utc[0, 0] = "2026-05-02T17:20:00Z"
        time_utc[0, 1] = "2026-05-02T17:21:00Z"
        science_name = (
            "nitrogendioxide_tropospheric_column"
            if product == "no2"
            else "ozone_total_vertical_column"
        )
        science = variable(product_group, science_name)
        science[:] = [[[1e-5, 2e-5], [0.12, 0.13]]] if product == "no2" else [[[0.12, 0.13], [0.14, 0.15]]]


def test_tropomi_preprocessor_qc_regrids_and_names(tmp_path: Path) -> None:
    no2 = tmp_path / "NO2.nc"
    o3 = tmp_path / "O3.nc"
    _write_granule(no2, "no2")
    _write_granule(o3, "o3")
    files = {"no2": [str(no2)], "o3": [str(o3)]}

    result = TropomiPreprocessor().preprocess(
        DatasetBundle("TROPOMI", [no2, o3], {"files_by_product": files}),
        _configuration(),
    )

    assert set(result.data.data_vars) == {"tropospheric_no2_column", "total_o3_column"}
    assert result.data.sizes == {"time": 1, "lat": 2, "lon": 2}
    assert result.data.time.values[0] == np.datetime64("2026-05-02T17:30:00")
    assert int(result.data["tropospheric_no2_column"].notnull().sum()) == 2
    assert int(result.data["total_o3_column"].notnull().sum()) == 2
    assert result.metadata["timestamps_utc"] is True


def test_tropomi_acquisition_uses_configured_short_names(monkeypatch, tmp_path: Path) -> None:
    calls = []

    class Granule:
        def __init__(self, name):
            self.name = name

        def data_links(self):
            return [f"https://example.test/{self.name}"]

        def __getitem__(self, key):
            return {"CollectionReference": {"ShortName": self.name, "Version": "2"}}[key]

    fake = SimpleNamespace()
    fake.login = lambda **kwargs: True

    def search_data(**kwargs):
        calls.append(kwargs)
        return (granule for granule in [Granule(kwargs["short_name"])])

    def download(granules, local_path, threads):
        paths = []
        for granule in granules:
            name = "NO2_sample.nc" if "NO2" in granule.name else "O3_sample.nc"
            path = Path(local_path) / name
            path.touch()
            paths.append(path)
        return paths

    fake.search_data = search_data
    fake.download = download
    monkeypatch.setitem(sys.modules, "earthaccess", fake)

    request = DataRequest(
        "TROPOMI", "ATL", start_time=pd.Timestamp("2026-08-04", tz="UTC").to_pydatetime(),
        end_time=pd.Timestamp("2026-08-05", tz="UTC").to_pydatetime(),
        metadata={"temporary_directory": str(tmp_path)},
    )
    bundle = TropomiDataSource().acquire(request, _configuration())

    assert {call["short_name"] for call in calls} == {NO2_SHORT_NAME, O3_SHORT_NAME}
    assert all(call["version"] == "2" for call in calls)
    assert set(bundle.metadata["files_by_product"]) == {"no2", "o3"}
