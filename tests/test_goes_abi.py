"""Network-free tests for GOES ABI AOD acquisition and preprocessing."""

from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
from netCDF4 import Dataset

from aqdatafusion.contracts import DataRequest, DatasetBundle
from aqdatafusion.data_acquisition.goes_abi import GoesAbiAodDataSource
from aqdatafusion.preprocessing.goes_abi import GoesAbiAodPreprocessor


def _configuration(tmp_path: Path):
    return {
        "region": {
            "region_code": "ATL",
            "bounds": {"latitude": [33.0, 34.0], "longitude": [-85.0, -84.0]},
        },
        "input_data": {
            "datasets": {
                "GOES-ABI": {
                    "source_key": "GOES-ABI",
                    "variables": ["aod550"],
                    "coordinate_names": {"latitude": "lat", "longitude": "lon", "time": "time"},
                    "quality_control": {"dqf_max": 1, "aod_min": 0.0, "aod_max": 5.0},
                    "regridding": {"latlon_resolution": 0.02},
                    "access": {
                        "product": "ABI-L2-AODC",
                        "satellite_order": ["noaa-goes19", "noaa-goes16", "noaa-goes18", "noaa-goes17"],
                    },
                }
            }
        },
    }


def _write_granule(path: Path, *, time: str, dqf_value: int, values=None) -> None:
    with Dataset(path, "w") as root:
        root.createDimension("x", 2)
        root.createDimension("y", 2)
        x = root.createVariable("x", "f8", ("x",))
        y = root.createVariable("y", "f8", ("y",))
        x[:] = [-0.02450, -0.02400]
        y[:] = [0.09520, 0.09470]
        projection = root.createVariable("goes_imager_projection", "i4")
        projection.perspective_point_height = 35786023.0
        projection.semi_major_axis = 6378137.0
        projection.semi_minor_axis = 6356752.31414
        projection.longitude_of_projection_origin = -75.0
        aod = root.createVariable("AOD", "f4", ("y", "x"), fill_value=-999.0)
        aod[:] = values if values is not None else [[0.1, 0.2], [0.3, 0.4]]
        dqf = root.createVariable("DQF", "u1", ("y", "x"), fill_value=255)
        dqf[:] = dqf_value
        root.setncattr("time_coverage_start", time)


def test_goes_preprocessing_qc_fallback_regrids_and_centers_time(tmp_path: Path) -> None:
    preferred = tmp_path / "preferred.nc"
    fallback = tmp_path / "fallback.nc"
    _write_granule(preferred, time="2026-05-01T16:01:17Z", dqf_value=3)
    _write_granule(fallback, time="2026-05-01T16:04:17Z", dqf_value=0)
    configuration = _configuration(tmp_path)
    result = GoesAbiAodPreprocessor().preprocess(
        DatasetBundle(
            "GOES-ABI",
            [preferred, fallback],
            {
                "files_by_satellite": {
                    "noaa-goes19": [str(preferred)],
                    "noaa-goes16": [str(fallback)],
                },
                "satellite_order": ["noaa-goes19", "noaa-goes16"],
                "requested_start_time": "2026-05-01T16:00:00Z",
                "requested_end_time": "2026-05-01T17:00:00Z",
            },
        ),
        configuration,
    )

    assert result.data.sizes == {"time": 1, "lat": 50, "lon": 50}
    assert result.data.time.values[0] == np.datetime64("2026-05-01T16:30:00")
    assert int(result.data.aod550.notnull().sum()) == 4
    assert np.isclose(float(result.data.aod550.max()), 0.4)


def test_goes_acquisition_tries_satellites_in_configured_order(monkeypatch, tmp_path: Path) -> None:
    calls = []

    class FakeS3:
        def __init__(self, anon):
            assert anon is True

        def glob(self, prefix):
            calls.append(prefix)
            if "noaa-goes16" in prefix:
                return [prefix.replace("/*/*.nc", "/16/sample.nc")]
            return []

        def get(self, remote, local):
            Path(local).touch()

    monkeypatch.setitem(sys.modules, "s3fs", SimpleNamespace(S3FileSystem=FakeS3))
    request = DataRequest(
        "GOES-ABI",
        "ATL",
        ["aod550"],
        pd.Timestamp("2026-05-01T16:00:00Z").to_pydatetime(),
        pd.Timestamp("2026-05-01T17:00:00Z").to_pydatetime(),
        {"temporary_directory": str(tmp_path)},
    )
    bundle = GoesAbiAodDataSource().acquire(request, _configuration(tmp_path))

    assert len(bundle.data) == 1
    assert bundle.metadata["selected_satellites"] == {"2026-05-01T16:00:00+00:00": "noaa-goes16"}
    assert "noaa-goes19/ABI-L2-AODC/2026/121" in calls[0]
    assert "noaa-goes16/ABI-L2-AODC/2026/121" in calls[1]
