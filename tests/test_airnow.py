"""Network-free tests for the AirNow acquisition and preprocessing stages."""

from datetime import datetime, timezone

import pandas as pd
import requests

from aqforecast.contracts import DataRequest
from aqforecast.data_acquisition.airnow import AirNowDataSource
from aqforecast.data_management import DatabaseManager
from aqforecast.preprocessing.airnow import AirNowPreprocessor


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(response=self)

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        return FakeResponse(self.payload)


class FlakySession(FakeSession):
    """Fail once so the adapter's retry path can be tested without a network."""

    def get(self, url, *, params, timeout):
        if not self.calls:
            self.calls.append((url, params, timeout))
            raise requests.ConnectionError("temporary test failure")
        return super().get(url, params=params, timeout=timeout)


CONFIGURATION = {
    "credentials": {"airnow": {"api_key": "test-key"}},
    "region": {
        "bounds": {"latitude": [33.0, 35.0], "longitude": [-85.0, -83.0]}
    },
    "input_data": {"datasets": {"ground_monitors": {}}},
}


RESPONSE = [
    {
        "Latitude": 33.5,
        "Longitude": -84.5,
        "UTC": "2026-07-03T00:00",
        "Parameter": "OZONE",
        "Unit": "PPB",
        "Value": 40.0,
        "FullAQSCode": "130010001",
    },
    {
        "Latitude": 33.5,
        "Longitude": -84.5,
        "UTC": "2026-07-03T00:00",
        "Parameter": "CO",
        "Unit": "PPM",
        "Value": 1.2,
        "FullAQSCode": "130010001",
    },
    {
        "Latitude": 33.5,
        "Longitude": -84.5,
        "UTC": "2026-07-03T00:00",
        "Parameter": "NO2",
        "Unit": "PPB",
        "Value": -1.0,
        "FullAQSCode": "130010001",
    },
    {
        "Latitude": 34.0,
        "Longitude": -84.0,
        "UTC": "2026-07-03T01:00",
        "Parameter": "PM25",
        "Unit": "UG/M3",
        "Value": 12.5,
        "FullAQSCode": "130010002",
    },
]


def test_airnow_acquisition_uses_verified_request_and_preserves_units():
    session = FakeSession(RESPONSE)
    source = AirNowDataSource(session=session, max_query_hours=168)
    request = DataRequest(
        "ground_monitors",
        "ATL",
        [
            "site_id",
            "lat",
            "lon",
            "time",
            "PM2.5",
            "NO2",
            "O3",
            "CO",
            "SO2",
            "PM10",
        ],
        datetime(2026, 7, 3, tzinfo=timezone.utc),
        datetime(2026, 7, 8, tzinfo=timezone.utc),
    )

    bundle = source.acquire(request, CONFIGURATION)

    assert len(session.calls) == 1
    params = session.calls[0][1]
    assert params["startDate"] == "2026-07-03T00"
    assert params["endDate"] == "2026-07-07T23"
    assert params["dataType"] == "C"
    assert params["monitorType"] == 2
    assert params["includeRawConcentrations"] == 0
    assert params["parameters"] == "PM25,PM10,NO2,OZONE,SO2,CO"
    assert list(bundle.data.loc[0, ["aqs_id", "time", "CO_unit"]]) == [
        "130010001",
        pd.Timestamp("2026-07-03 00:30:00+00:00"),
        "PPM",
    ]


def test_airnow_retries_transient_request_failure(monkeypatch):
    session = FlakySession(RESPONSE)
    monkeypatch.setattr("aqforecast.data_acquisition.airnow.time.sleep", lambda _: None)
    source = AirNowDataSource(session=session, max_retries=2)
    request = DataRequest(
        "ground_monitors",
        "ATL",
        [],
        datetime(2026, 7, 3, tzinfo=timezone.utc),
        datetime(2026, 7, 3, 2, tzinfo=timezone.utc),
    )

    bundle = source.acquire(request, CONFIGURATION)

    assert not bundle.errors
    assert len(session.calls) == 2


def test_airnow_standardized_output_round_trips_through_database(tmp_path):
    configuration = {
        **CONFIGURATION,
        "region": {**CONFIGURATION["region"], "region_code": "ATL"},
        "aqforecast": {"inputs": {"ground_monitors": {"enabled": True}}},
        "filepaths": {"data_sources": {"ground_monitors": str(tmp_path / "ground_monitors")}},
        "input_data": {
            "datasets": {
                "ground_monitors": {
                    "file_template": "ground_monitors_{region_code}_{month_string}.csv",
                    "variables": ["site_id", "lat", "lon", "time", "PM2.5", "PM10", "NO2", "O3", "SO2", "CO"],
                    "site_id": "site_id",
                    "coordinate_names": {"latitude": "lat", "longitude": "lon", "time": "time"},
                    "time": {"frequency": "1h", "timestamp_convention": "center", "tolerance": "0s", "availability": {"mode": "continuous"}},
                    "storage": {"partition": "monthly", "format": "csv", "catalog_filename": "catalog.json"},
                }
            }
        },
    }
    session = FakeSession(RESPONSE)
    source = AirNowDataSource(session=session, max_query_hours=168)
    manager = DatabaseManager(
        configuration,
        data_sources={"ground_monitors": source},
        preprocessors={"ground_monitors": AirNowPreprocessor()},
    )

    report = manager.update(
        "2026-07-03T00:00:00Z",
        "2026-07-03T02:00:00Z",
        source_keys=["ground_monitors"],
    )

    assert report.sources["ground_monitors"]["status"] == "updated"
    assert report.sources["ground_monitors"]["integrity"]["valid"]
    output = tmp_path / "ground_monitors" / "ground_monitors_ATL_202607.csv"
    assert output.exists()
    archived = pd.read_csv(output)
    assert set(pd.to_datetime(archived["time"], utc=True)) == {
        pd.Timestamp("2026-07-03T00:30:00Z"),
        pd.Timestamp("2026-07-03T01:30:00Z"),
    }
    assert (tmp_path / "ground_monitors" / "catalog.json").exists()


def test_airnow_preprocessing_converts_qc_maps_site_id_and_drops_units():
    session = FakeSession(RESPONSE)
    source = AirNowDataSource(session=session)
    request = DataRequest(
        "ground_monitors",
        "ATL",
        [],
        datetime(2026, 7, 3, tzinfo=timezone.utc),
        datetime(2026, 7, 3, 2, tzinfo=timezone.utc),
    )
    acquired = source.acquire(request, CONFIGURATION)
    processed = AirNowPreprocessor().preprocess(acquired, CONFIGURATION)

    data = processed.data
    assert list(data.columns) == [
        "site_id",
        "lat",
        "lon",
        "time",
        "PM2.5",
        "PM10",
        "NO2",
        "O3",
        "SO2",
        "CO",
    ]
    row = data[data["site_id"] == "130010001"].iloc[0]
    assert row["O3"] == 40.0
    assert row["CO"] == 1200.0
    assert pd.isna(row["NO2"])
    assert "aqs_id" not in data.columns
    assert processed.metadata["unit_conversion_counts"]["CO"] == 1
    assert processed.metadata["temporary_unit_columns_removed"] is True


def test_airnow_adapters_are_registered_for_airnow_regions():
    manager = DatabaseManager(
        {"region": {"ground_monitoring": {"provider": "AirNow"}}}
    )

    assert isinstance(
        manager.data_sources["ground_monitors"], AirNowDataSource
    )
    assert isinstance(
        manager.preprocessors["ground_monitors"], AirNowPreprocessor
    )
