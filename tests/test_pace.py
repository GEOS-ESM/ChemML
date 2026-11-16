"""Network-free tests for PACE trace-gas acquisition and preprocessing."""

from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
from netCDF4 import Dataset

from aqforecast.contracts import DataRequest, DatasetBundle
from aqforecast.data_acquisition.pace import SHORT_NAME, PaceTraceGasDataSource
from aqforecast.preprocessing.pace import PaceTraceGasPreprocessor


def _configuration():
    return {
        "credentials": {"earthdata": {"username": "user", "password": "pass"}},
        "region": {
            "region_code": "ATL",
            "bounds": {"latitude": [33.0, 34.0], "longitude": [-85.0, -84.0]},
        },
        "input_data": {
            "datasets": {
                "PACE": {
                    "source_key": "PACE",
                    "variables": ["total_column_no2", "total_column_o3"],
                    "coordinate_names": {"latitude": "lat", "longitude": "lon", "time": "time"},
                    "quality_control": {"no2_good_value": 0, "o3_good_value": 0},
                    "regridding": {"latlon_resolution": 0.02},
                    "access": {"collection_version": "3.0"},
                }
            }
        },
    }


def _write_granule(path: Path, start_time: str, no2_quality: int = 0) -> None:
    with Dataset(path, "w") as root:
        root.createDimension("number_of_lines", 2)
        root.createDimension("pixels_per_line", 2)
        geo = root.createGroup("geolocation_data")
        science = root.createGroup("geophysical_data")
        lat = geo.createVariable("latitude", "f4", ("number_of_lines", "pixels_per_line"))
        lon = geo.createVariable("longitude", "f4", ("number_of_lines", "pixels_per_line"))
        lat[:] = [[33.10, 33.10], [33.20, 33.20]]
        lon[:] = [[-84.90, -84.80], [-84.90, -84.80]]
        no2 = science.createVariable("total_column_no2", "f4", ("number_of_lines", "pixels_per_line"), fill_value=-1e30)
        o3 = science.createVariable("total_column_o3", "f4", ("number_of_lines", "pixels_per_line"), fill_value=-1e30)
        q2 = science.createVariable("quality_no2", "i4", ("number_of_lines", "pixels_per_line"), fill_value=-32767)
        q3 = science.createVariable("quality_o3", "i4", ("number_of_lines", "pixels_per_line"), fill_value=-32767)
        no2[:] = [[1e15, 2e15], [3e15, 4e15]]
        o3[:] = [[300., 310.], [320., 330.]]
        q2[:] = [[no2_quality, no2_quality], [no2_quality, no2_quality]]
        q3[:] = 0
        root.setncattr("time_coverage_start", start_time)


def test_pace_preprocessing_applies_quality_regrids_and_aggregates(tmp_path: Path) -> None:
    first = tmp_path / "PACE_OCI.20260501T183120.L2.TRGAS.V3_0.nc"
    second = tmp_path / "PACE_OCI.20260501T190612.L2.TRGAS.V3_0.nc"
    _write_granule(first, "2026-05-01T18:31:20Z")
    _write_granule(second, "2026-05-01T19:06:12Z", no2_quality=1)
    result = PaceTraceGasPreprocessor().preprocess(
        DatasetBundle("PACE", [first, second], {}), _configuration()
    )

    assert result.data.sizes == {"time": 1, "lat": 50, "lon": 50}
    assert result.data.time.values[0] == np.datetime64("2026-05-01T18:30:00")
    assert int(result.data.total_column_no2.notnull().sum()) == 4
    assert int(result.data.total_column_o3.notnull().sum()) == 4
    assert result.metadata["timestamps_utc"] is True


def test_pace_acquisition_uses_standard_collection(monkeypatch, tmp_path: Path) -> None:
    calls = []

    class Granule:
        def data_links(self):
            return ["https://example.test/PACE_OCI.20260501T183120.L2.TRGAS.V3_0.nc"]

    fake = SimpleNamespace(login=lambda **kwargs: True)

    def search_data(**kwargs):
        calls.append(kwargs)
        return [Granule()]

    def download(granules, local_path, threads):
        path = Path(local_path) / "PACE_OCI.20260501T183120.L2.TRGAS.V3_0.nc"
        path.touch()
        return [path]

    fake.search_data = search_data
    fake.download = download
    monkeypatch.setitem(sys.modules, "earthaccess", fake)
    request = DataRequest(
        "PACE", "ATL", ["total_column_no2", "total_column_o3"],
        pd.Timestamp("2026-05-01", tz="UTC").to_pydatetime(),
        pd.Timestamp("2026-05-02", tz="UTC").to_pydatetime(),
        metadata={"temporary_directory": str(tmp_path)},
    )
    bundle = PaceTraceGasDataSource().acquire(request, _configuration())

    assert calls[0]["short_name"] == SHORT_NAME
    assert calls[0]["version"] == "3.0"
    assert bundle.data[0].name.startswith("PACE_OCI.")
