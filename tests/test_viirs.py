"""Network-free tests for VIIRS VJ219A2 acquisition and preprocessing."""

from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
from netCDF4 import Dataset

from aqforecast.contracts import DataRequest, DatasetBundle
from aqforecast.data_acquisition.viirs import CONCEPT_ID, SHORT_NAME, ViirsAodDataSource
from aqforecast.preprocessing.viirs import ViirsAodPreprocessor


def _configuration():
    return {
        "credentials": {"earthdata": {"username": "user", "password": "pass"}},
        "region": {
            "region_code": "ATL",
            "bounds": {"latitude": [33.0, 34.0], "longitude": [-85.0, -84.0]},
        },
        "input_data": {
            "datasets": {
                "VIIRS": {
                    "source_key": "VIIRS",
                    "variables": ["optical_depth_055"],
                    "coordinate_names": {"latitude": "lat", "longitude": "lon", "time": "time"},
                    "quality_control": {
                        "qa_quality_mask": 3,
                        "qa_quality_max": 1,
                        "aod_resolution_min": 0.0,
                        "aod_resolution_max": 6.0,
                    },
                    "regridding": {"latlon_resolution": 0.05},
                    "access": {"collection_version": "002"},
                }
            }
        },
    }


def _write_granule(path: Path) -> None:
    radius = 6371007.181
    central = np.radians(-70.0)
    latitudes = np.array([33.10, 33.20])
    longitudes = np.array([-84.90, -84.80])
    x = radius * np.cos(np.radians(latitudes[0])) * (np.radians(longitudes) - central)
    y = radius * np.radians(latitudes)
    with Dataset(path, "w") as root:
        heos = root.createGroup("HDFEOS")
        grids = heos.createGroup("GRIDS")
        grid = grids.createGroup("grid750m")
        fields = grid.createGroup("Data Fields")
        heos_info = root.createGroup("HDFEOS INFORMATION")
        root.createDimension("metadata_length", 1)
        grid.createDimension("DIM_ORBIT", 2)
        grid.createDimension("YDim", 2)
        grid.createDimension("XDim", 2)
        metadata = heos_info.createVariable("StructMetadata.0", str, ("metadata_length",))
        metadata[0] = 'GROUP=GridStructure\nGRID_1\nProjParams=(6371007.181000,0,0)\nEND'
        x_var = grid.createVariable("XDim", "f8", ("XDim",))
        y_var = grid.createVariable("YDim", "f8", ("YDim",))
        x_var[:] = x
        y_var[:] = y
        science = fields.createVariable(
            "Optical_Depth_055", "i2", ("DIM_ORBIT", "YDim", "XDim"), fill_value=-28672
        )
        science.scale_factor = 0.001
        science[:] = np.array([[[0.10, 0.10], [0.10, 0.10]], [[0.30, 0.30], [0.30, 0.30]]])
        qa = fields.createVariable("AOD_QA", "u2", ("DIM_ORBIT", "YDim", "XDim"), fill_value=0)
        qa[:] = np.array([[[1, 1], [1, 1]], [[1, 3], [1, 3]]], dtype=np.uint16)
        root.setncattr("TimeStamp", "20261221720,20261221810")
        root.setncattr(
            "GRingLongitude",
            [
                np.degrees(central + x[0] / (radius * np.cos(np.radians(latitudes[0])))),
                np.degrees(central + x[1] / (radius * np.cos(np.radians(latitudes[0])))),
                np.degrees(central + x[1] / (radius * np.cos(np.radians(latitudes[1])))),
                np.degrees(central + x[0] / (radius * np.cos(np.radians(latitudes[1])))),
            ],
        )
        root.setncattr("GRingLatitude", [33.1, 33.1, 33.2, 33.2])


def test_viirs_preprocessing_filters_regrids_and_selects_timestamp(tmp_path: Path) -> None:
    granule = tmp_path / "VJ219A2.A2026122.h30v05.002.test.h5"
    _write_granule(granule)
    result = ViirsAodPreprocessor().preprocess(
        DatasetBundle("VIIRS", [granule], {}), _configuration()
    )

    assert result.data.sizes == {"time": 1, "lat": 20, "lon": 20}
    assert result.data.time.values[0] == np.datetime64("2026-05-02T17:30:00")
    assert float(result.data.optical_depth_055.max()) == 0.2
    assert int(result.data.optical_depth_055.notnull().sum()) == 4
    assert result.metadata["timestamps_utc"] is True


def test_viirs_acquisition_falls_back_to_concept_id(monkeypatch, tmp_path: Path) -> None:
    calls = []

    class Granule:
        def data_links(self):
            return ["https://example.test/VJ219A2_sample.h5"]

    fake = SimpleNamespace(login=lambda **kwargs: True)

    def search_data(**kwargs):
        calls.append(kwargs)
        return [] if "short_name" in kwargs else [Granule()]

    def download(granules, local_path, threads):
        path = Path(local_path) / "VJ219A2.A2026122.h30v05.002.test.h5"
        path.touch()
        return [path]

    fake.search_data = search_data
    fake.download = download
    monkeypatch.setitem(sys.modules, "earthaccess", fake)
    request = DataRequest(
        "VIIRS", "ATL", ["optical_depth_055"],
        pd.Timestamp("2026-05-02", tz="UTC").to_pydatetime(),
        pd.Timestamp("2026-05-03", tz="UTC").to_pydatetime(),
        metadata={"temporary_directory": str(tmp_path)},
    )
    bundle = ViirsAodDataSource().acquire(request, _configuration())

    assert calls[0]["short_name"] == SHORT_NAME
    assert calls[1]["concept_id"] == CONCEPT_ID
    assert bundle.data[0].name.startswith(SHORT_NAME)


def test_viirs_geolocation_uses_granule_projection_metadata(tmp_path: Path) -> None:
    granule = tmp_path / "VJ219A2.A2026122.h30v05.002.test.h5"
    _write_granule(granule)
    result = ViirsAodPreprocessor().preprocess(
        DatasetBundle("VIIRS", [granule], {}), _configuration()
    )

    assert result.data.lat.values[0] == np.float64(33.025)
    assert result.data.lon.values[0] == np.float64(-84.975)
