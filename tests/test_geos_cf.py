"""Network-free GEOS-CF acquisition helpers and preprocessing tests."""

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from aqdatafusion.contracts import DatasetBundle
from aqdatafusion.data_acquisition.geos_cf import (
    _decode_geos_cf_time,
    _open_chunked_subset,
    _remote_url,
    _concatenate_local_records,
    _geos_cf_filename_time,
    _geos_cf_filename_timestamps,
    _geos_cf_local_file_is_relevant,
    _select_latest_revision_paths,
    _select_requested_variables,
)
from aqdatafusion.preprocessing.geos_cf import GeosCfPreprocessor, _filename_initialization


def _configuration(tmp_path: Path) -> dict:
    return {
        "region": {
            "region_code": "ATL",
            "bounds": {"latitude": [30.0, 35.0], "longitude": [-86.0, -80.0]},
        },
        "input_data": {
            "datasets": {
                "GEOS-CF": {"regridding": {"latlon_resolution": 0.25}}
            }
        },
    }


def _record(stream: str, times: list[str], values: list[float], initialization: str = "") -> xr.Dataset:
    return xr.Dataset(
        {"pm25_rh35": (("time", "lev", "lat", "lon"), np.asarray(values, dtype=float).reshape(len(times), 1, 1, 1))},
        coords={"time": pd.to_datetime(times), "lev": [72.0], "lat": [33.0], "lon": [-84.0]},
        attrs={"geos_cf_stream": stream, "forecast_initialization_time": initialization},
    )


def test_geos_cf_raw_time_decodes_year_one_epoch() -> None:
    values = _decode_geos_cf_time(
        np.asarray([739922.3958333334]),
        {"units": "days since 1-1-1 00:00:0.0", "minimum": "09:30z01nov2026"},
    )
    assert values[0] == np.datetime64("2026-11-01T09:30:00")


def test_geos_cf_relative_time_decodes_standard_units() -> None:
    values = _decode_geos_cf_time(
        np.asarray([0.0, 30.0, 90.0]),
        {"units": "minutes since 2026-11-29 08:30:00"},
    )

    np.testing.assert_array_equal(values, [
        np.datetime64("2026-11-29T08:30:00"),
        np.datetime64("2026-11-29T09:00:00"),
        np.datetime64("2026-11-29T10:00:00"),
    ])


def test_geos_cf_forecast_url_uses_initialization_endpoint() -> None:
    url = _remote_url(
        {"base_url": "https://example.test/v2", "forecast_endpoint": "dated"},
        "fcst",
        "aqc_tavg_1hr_glo_L1440x721_slv",
        pd.Timestamp("2026-11-01T09:00:00Z"),
    )
    assert url.endswith("/aqc_tavg_1hr_glo_L1440x721_slv.20261101_09z")


def test_geos_cf_variable_selection_is_case_insensitive() -> None:
    dataset = xr.Dataset({"PM25_RH35": (("time",), [1.0])})

    selected = _select_requested_variables(
        dataset, ["pm25_rh35"], "missing variable"
    )

    assert set(selected.data_vars) == {"pm25_rh35"}
    assert selected["pm25_rh35"].item() == 1.0


def test_geos_cf_variable_selection_uses_surface_variable_aliases() -> None:
    dataset = xr.Dataset({
        "U": (("time",), [1.0]),
        "V": (("time",), [2.0]),
        "T": (("time",), [3.0]),
        "Q": (("time",), [4.0]),
    })

    selected = _select_requested_variables(
        dataset, ["u2m", "v2m", "t2m", "q2m"], "missing variable"
    )

    assert set(selected.data_vars) == {"u2m", "v2m", "t2m", "q2m"}
    assert [selected[name].item() for name in ("u2m", "v2m", "t2m", "q2m")] == [
        1.0, 2.0, 3.0, 4.0
    ]


def test_geos_cf_selects_highest_local_revision(tmp_path: Path) -> None:
    revision_zero = tmp_path / "GEOS.cf.fcst.xgc_tavg_1hr_glo_L1440x721_slv.20261124_09z+20261129_0830z.R0.nc4"
    revision_two = tmp_path / "GEOS.cf.fcst.xgc_tavg_1hr_glo_L1440x721_slv.20261124_09z+20261129_0830z.R2.nc4"
    compressed_revision_one = tmp_path / "GEOS.cf.fcst.aqc_tavg_1hr_glo_L1440x721_slv.20261124_09z.R1.nc4.cmprs"
    for path in (revision_zero, revision_two, compressed_revision_one):
        path.touch()

    selected = _select_latest_revision_paths([
        revision_zero, revision_two, compressed_revision_one
    ])

    assert selected == [compressed_revision_one, revision_two]


def test_geos_cf_filename_time_parses_forecast_timestamp() -> None:
    path = Path(
        "GEOS.cf.fcst.xgc_tavg_1hr_glo_L1440x721_slv.20261124_09z"
        "+20261129_0730z.R0.nc4"
    )

    assert _geos_cf_filename_time(path) == pd.Timestamp("2026-11-29T07:30:00Z")
    assert _geos_cf_filename_time(Path("GEOS.cf.ana.aqc.nc4")) is None


def test_geos_cf_local_filename_filters_use_stream_specific_dates() -> None:
    start = pd.Timestamp("2026-11-22T00:00:00Z")
    end = pd.Timestamp("2026-11-24T00:00:00Z")
    analysis = Path("GEOS.cf.ana.aqc_tavg_1hr_glo_L1440x721_slv.20261122_0030z.nc4")
    forecast = Path(
        "GEOS.cf.fcst.aqc_tavg_1hr_glo_L1440x721_slv.20261118_09z"
        "+20261122_0730z.R0.nc4"
    )
    late_forecast = Path(
        "GEOS.cf.fcst.aqc_tavg_1hr_glo_L1440x721_slv.20261118_09z"
        "+20261129_0730z.R0.nc4"
    )

    assert _geos_cf_filename_timestamps(forecast) == (
        pd.Timestamp("2026-11-18T09:00:00Z"),
        pd.Timestamp("2026-11-22T07:30:00Z"),
    )
    assert _geos_cf_local_file_is_relevant(
        analysis, "ana", pd.Timestamp("2026-11-22", tz="UTC"), start, end
    )
    assert _geos_cf_local_file_is_relevant(
        forecast, "fcst", pd.Timestamp("2026-11-18", tz="UTC"), start, end
    )
    assert not _geos_cf_local_file_is_relevant(
        late_forecast, "fcst", pd.Timestamp("2026-11-18", tz="UTC"), start, end
    )


def test_geos_cf_local_records_are_concatenated_over_time() -> None:
    first = xr.Dataset(
        {"no2": (("time", "lat", "lon"), [[[1.0]]])},
        coords={"time": pd.to_datetime(["2026-11-22T00:30:00"]), "lat": [33.0], "lon": [-84.0]},
    )
    second = xr.Dataset(
        {"no2": (("time", "lat", "lon"), [[[2.0]]])},
        coords={"time": pd.to_datetime(["2026-11-22T01:30:00"]), "lat": [33.0], "lon": [-84.0]},
    )

    result = _concatenate_local_records([first, second])

    assert list(result.time.values) == [
        np.datetime64("2026-11-22T00:30:00"),
        np.datetime64("2026-11-22T01:30:00"),
    ]
    np.testing.assert_array_equal(result.no2.values[:, 0, 0], [1.0, 2.0])


def test_geos_cf_forecast_initialization_falls_back_to_filename() -> None:
    source_url = (
        "/discover/geos/fcst/GEOS.cf.fcst.xgc_tavg_1hr_glo_L1440x721_slv."
        "20261124_09z+20261129_0730z.R0.nc4"
    )

    assert _filename_initialization(source_url) == "2026-11-24T09:00:00+00:00"


def test_geos_cf_preprocessor_uses_filename_initialization(tmp_path: Path) -> None:
    record = _record(
        "fcst",
        ["2026-11-24T09:30:00", "2026-11-25T09:30:00"],
        [10.0, 20.0],
    )
    record.attrs["source_url"] = (
        "GEOS.cf.fcst.xgc_tavg_1hr_glo_L1440x721_slv.20261124_09z+"
        "20261129_0730z.R0.nc4"
    )
    bundle = DatasetBundle(
        "GEOS-CF",
        [record],
        {
            "request_start_time": "2026-11-24T09:30:00Z",
            "request_end_time": "2026-11-26T10:00:00Z",
        },
    )

    result = GeosCfPreprocessor().preprocess(bundle, _configuration(tmp_path))

    assert result.data.sizes["forecast_lead_day"] == 6


def test_geos_cf_subset_is_split_by_time_and_variable(monkeypatch) -> None:
    calls = []

    def fake_open(url, variables, bounds, start, end):
        calls.append((tuple(variables), start, end))
        return xr.Dataset(
            {variables[0]: (("time", "lat", "lon"), [[[1.0]]])},
            coords={"time": [start + pd.Timedelta(minutes=30)], "lat": [33.0], "lon": [-84.0]},
        )

    monkeypatch.setattr("aqdatafusion.data_acquisition.geos_cf._open_subset", fake_open)
    result = _open_chunked_subset(
        "https://example.test/data",
        ["co", "no2"],
        (-85.0, 33.0, -83.0, 35.0),
        pd.Timestamp("2026-11-03T00:00:00Z"),
        pd.Timestamp("2026-11-04T00:00:00Z"),
        {"request_chunk_hours": 6, "request_variable_chunk_size": 1},
    )

    assert len(calls) == 8
    assert all(len(variables) == 1 for variables, _, _ in calls)
    assert all((end - start) <= pd.Timedelta(hours=6) for _, start, end in calls)
    assert set(result.data_vars) == {"co", "no2"}


def test_geos_cf_preprocessor_preserves_analysis_and_forecast_leads(tmp_path: Path) -> None:
    analysis = _record(
        "ana", ["2026-11-01T09:30:00", "2026-11-01T10:30:00"], [1.0, np.inf]
    )
    forecast = _record(
        "fcst",
        ["2026-11-01T09:30:00", "2026-11-01T10:30:00", "2026-11-02T09:30:00"],
        [10.0, 11.0, 20.0],
        "2026-11-01T09:00:00Z",
    )
    bundle = DatasetBundle(
        "GEOS-CF",
        [analysis, forecast],
        {
            "request_start_time": "2026-11-01T09:30:00Z",
            "request_end_time": "2026-11-02T10:00:00Z",
        },
    )

    result = GeosCfPreprocessor().preprocess(bundle, _configuration(tmp_path))
    values = result.data["pm25_rh35"]

    assert result.data.sizes["forecast_lead_day"] == 6
    assert values.sel(time="2026-11-01T09:30:00", forecast_lead_day=0).item() == 1.0
    assert values.sel(time="2026-11-01T09:30:00", forecast_lead_day=1).item() == 10.0
    assert values.sel(time="2026-11-02T09:30:00", forecast_lead_day=2).item() == 20.0
    assert np.isnan(values.sel(time="2026-11-01T10:30:00", forecast_lead_day=0).item())
    assert result.metadata["timestamps_utc"] is True
