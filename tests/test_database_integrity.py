"""Tests for post-update partition and catalog integrity checks."""

import json

import numpy as np
import pandas as pd
import xarray as xr

from aqdatafusion.data_management.catalog import DatasetCatalog
from aqdatafusion.data_management.integrity import verify_database_integrity


def _grid_source():
    return {
        "variables": ["value"],
        "coordinate_names": {"latitude": "lat", "longitude": "lon", "time": "time"},
        "storage": {"format": "netcdf", "catalog_filename": "catalog.json"},
    }


def _write_grid(directory, times, *, lat=(1.0, 2.0), lon=(3.0, 4.0)):
    directory.mkdir(parents=True, exist_ok=True)
    dataset = xr.Dataset(
        {"value": (("time", "lat", "lon"), np.ones((len(times), len(lat), len(lon))))},
        coords={"time": times, "lat": np.asarray(lat), "lon": np.asarray(lon)},
    )
    dataset.to_netcdf(directory / "part.nc")
    DatasetCatalog("grid", directory, _grid_source()).rebuild()


def test_integrity_reports_expected_gaps_as_warnings(tmp_path):
    directory = tmp_path / "grid"
    observed = pd.date_range("2026-01-01T00:00:00", periods=1, freq="h")
    _write_grid(directory, observed)

    result = verify_database_integrity(
        "grid",
        directory,
        _grid_source(),
        expected_times=pd.date_range("2026-01-01T00:00:00Z", periods=2, freq="h"),
    )

    assert result["valid"]
    assert len(result["errors"]) == 0
    assert len(result["warnings"]) == 1
    assert result["checks"]["timestamps"]["missing"] == [
        "2026-01-01T01:00:00+00:00"
    ]


def test_integrity_rejects_missing_variable(tmp_path):
    directory = tmp_path / "grid"
    directory.mkdir()
    xr.Dataset(
        {"other": (("time", "lat", "lon"), [[[1.0]]])},
        coords={"time": ["2026-01-01"], "lat": [1.0], "lon": [2.0]},
    ).to_netcdf(directory / "part.nc")
    DatasetCatalog("grid", directory, _grid_source()).rebuild()

    result = verify_database_integrity("grid", directory, _grid_source())

    assert not result["valid"]
    assert any("missing variables" in error for error in result["errors"])


def test_integrity_can_report_missing_variables_as_warnings(tmp_path):
    directory = tmp_path / "grid"
    directory.mkdir()
    source = {**_grid_source(), "integrity": {"missing_variables": "warning"}}
    xr.Dataset(
        {"other": (("time", "lat", "lon"), [[[1.0]]])},
        coords={"time": ["2026-01-01"], "lat": [1.0], "lon": [2.0]},
    ).to_netcdf(directory / "part.nc")
    DatasetCatalog("grid", directory, source).rebuild()

    result = verify_database_integrity("grid", directory, source)

    assert result["valid"]
    assert result["errors"] == []
    assert any("missing variables" in warning for warning in result["warnings"])


def test_integrity_rejects_duplicate_point_records(tmp_path):
    directory = tmp_path / "points"
    directory.mkdir()
    source = {
        "variables": ["value"],
        "site_id": "site_id",
        "coordinate_names": {"latitude": "lat", "longitude": "lon", "time": "time"},
        "storage": {"format": "csv", "catalog_filename": "catalog.json"},
    }
    pd.DataFrame(
        [
            {"site_id": "A", "lat": 1.0, "lon": 2.0, "time": "2026-01-01T00:00:00Z", "value": 1.0},
            {"site_id": "A", "lat": 1.0, "lon": 2.0, "time": "2026-01-01T00:00:00Z", "value": 2.0},
        ]
    ).to_csv(directory / "part.csv", index=False)
    DatasetCatalog("points", directory, source).rebuild()

    result = verify_database_integrity("points", directory, source)

    assert not result["valid"]
    assert any("duplicate records" in error for error in result["errors"])


def test_integrity_rejects_catalog_file_mismatch(tmp_path):
    directory = tmp_path / "grid"
    _write_grid(directory, ["2026-01-01"])
    catalog_path = directory / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    catalog["files"] = []
    catalog_path.write_text(json.dumps(catalog))

    result = verify_database_integrity("grid", directory, _grid_source())

    assert not result["valid"]
    assert any("catalog file list" in error for error in result["errors"])
