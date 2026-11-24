"""Network-free tests for MCD12Q1 acquisition and preprocessing."""

from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd

from aqdatafusion.contracts import DataRequest, DatasetBundle
from aqdatafusion.data_acquisition.land_cover import LandCoverDataSource, SHORT_NAME
from aqdatafusion.preprocessing import land_cover
from aqdatafusion.preprocessing.land_cover import LandCoverPreprocessor


def _configuration():
    return {
        "credentials": {"earthdata": {"username": "user", "password": "pass"}},
        "region": {
            "region_code": "ATL",
            "bounds": {"latitude": [33.0, 34.0], "longitude": [-85.0, -84.0]},
        },
        "input_data": {
            "datasets": {
                "land_cover": {
                    "source_key": "land_cover",
                    "variables": ["LC_Type1"],
                    "coordinate_names": {"latitude": "lat", "longitude": "lon", "time": "time"},
                    "quality_control": {
                        "apply_lw_filter": False,
                        "apply_qc_filter": False,
                        "lw_min": 0,
                        "lw_max": 255,
                        "qc_min": 0,
                        "qc_max": 255,
                        "land_cover_invalid_values": [255],
                    },
                    "regridding": {"latlon_resolution": 0.005, "categorical_variables": ["LC_Type1"]},
                    "access": {"collection_version": "061", "max_year_fallback": 2},
                }
            }
        },
    }


def test_land_cover_preprocessing_regrids_categorical_values(monkeypatch) -> None:
    def fake_read_tile(path, quality, configuration):
        return (
            pd.DataFrame(
                {
                    "lat": [33.001, 33.001, 33.006],
                    "lon": [-84.999, -84.999, -84.994],
                    "LC_Type1": [8, 8, 12],
                }
            ),
            {"file": path.name, "region_pixels": 3, "qc_valid_pixels": 3},
        )

    monkeypatch.setattr(land_cover, "_read_tile", fake_read_tile)
    result = LandCoverPreprocessor().preprocess(
        DatasetBundle(
            "land_cover",
            [Path("MCD12Q1.A2025001.h10v05.061.test.hdf")],
            {"files_by_requested_year": {"2025": ["tile.hdf"]}},
        ),
        _configuration(),
    )

    assert result.data.sizes == {"time": 1, "lat": 200, "lon": 200}
    assert result.data.time.values[0] == np.datetime64("2025-01-01")
    assert result.data["LC_Type1"].sel(lat=33.0025, lon=-84.9975).item() == 8
    assert result.data["LC_Type1"].sel(lat=33.0075, lon=-84.9925).item() == 12
    assert result.metadata["quality_control"]["apply_lw_filter"] is False


def test_land_cover_fallback_uses_source_year_timestamp(monkeypatch) -> None:
    monkeypatch.setattr(
        land_cover,
        "_read_tile",
        lambda path, quality, configuration: (
            pd.DataFrame({"lat": [33.001], "lon": [-84.999], "LC_Type1": [8]}),
            {"file": path.name, "region_pixels": 1, "qc_valid_pixels": 1},
        ),
    )
    result = LandCoverPreprocessor().preprocess(
        DatasetBundle(
            "land_cover",
            [Path("MCD12Q1.A2025001.h10v05.061.test.hdf")],
            {
                "files_by_requested_year": {"2026": ["tile.hdf"]},
                "source_year_by_requested_year": {"2026": 2025},
            },
        ),
        _configuration(),
    )

    assert result.data.time.values[0] == np.datetime64("2025-01-01")
    assert '"2026": 2025' in result.data.attrs["source_year_by_requested_year"]


def test_land_cover_acquisition_falls_back_two_years(monkeypatch, tmp_path: Path) -> None:
    calls = []

    class Granule:
        def __init__(self, identifier):
            self.identifier = identifier

        def get(self, key, default=None):
            if key == "umm":
                return {"GranuleUR": self.identifier}
            return default

    fake = SimpleNamespace(login=lambda **kwargs: True)

    def search_data(**kwargs):
        calls.append(kwargs)
        if kwargs["temporal"][0].startswith("2024"):
            return [Granule("MCD12Q1.A2024001.h10v05.061.test")]
        return []

    def download(granules, local_path, threads):
        path = Path(local_path) / "MCD12Q1.A2024001.h10v05.061.test.hdf"
        path.touch()
        return [path]

    fake.search_data = search_data
    fake.download = download
    monkeypatch.setitem(sys.modules, "earthaccess", fake)
    request = DataRequest(
        "land_cover",
        "ATL",
        ["LC_Type1"],
        pd.Timestamp("2026-08-04", tz="UTC").to_pydatetime(),
        pd.Timestamp("2026-08-10", tz="UTC").to_pydatetime(),
        metadata={"temporary_directory": str(tmp_path)},
    )

    bundle = LandCoverDataSource().acquire(request, _configuration())

    assert [call["temporal"][0][:4] for call in calls] == ["2026", "2025", "2024"]
    assert bundle.metadata["source_year_by_requested_year"] == {"2026": 2024}
    assert bundle.metadata["files_by_requested_year"]["2026"][0].endswith(".hdf")
    assert bundle.data[0].name.startswith(SHORT_NAME)


def test_sinusoidal_coordinates_use_mcd12q1_projection_metadata():
    root = SimpleNamespace(
        getncattr=lambda name: (
            "GROUP=GridStructure\n"
            "UpperLeftPointMtrs=(-8895604.157333,4447802.078667)\n"
            "ProjParams=(6371007.181000,0,0)"
        )
    )
    latitude, longitude = land_cover._sinusoidal_coordinates(root, (2400, 2400))

    assert latitude.shape == (2400, 2400)
    assert float(latitude[0, 0]) > 39.99
    assert float(longitude[0, 0]) < -104.4
