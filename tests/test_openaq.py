"""Network-free tests for the OpenAQ acquisition and preprocessing stages."""

from datetime import datetime, timezone

import pandas as pd

from aqforecast.contracts import DataRequest, DatasetBundle
from aqforecast.data_acquisition.openaq import OpenAQDataSource
from aqforecast.data_management import DatabaseManager
from aqforecast.preprocessing.openaq import OpenAQPreprocessor


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(response=self)

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, *, headers, params, timeout):
        self.calls.append((url, headers, params, timeout))
        return self.responses[url]


CONFIGURATION = {
    "credentials": {"openaq": {"api_key": "test-key"}},
    "region": {
        "bounds": {"latitude": [33.0, 35.0], "longitude": [-85.0, -83.0]},
        "ground_monitoring": {"provider": "OpenAQ"},
    },
    "input_data": {
        "datasets": {
            "ground_monitors": {
                "quality_control": {
                    "bounds": {
                        "PM2.5": [0.0, 500.0],
                        "PM10": [0.0, 1000.0],
                        "NO2": [0.0, 1000.0],
                        "O3": [0.0, 500.0],
                        "SO2": [0.0, 1000.0],
                        "CO": [0.0, 50000.0],
                    }
                }
            }
        }
    },
}


def _location_response():
    return {
        "meta": {"page": 1, "limit": 1000, "found": 1},
        "results": [
            {
                "id": 123,
                "coordinates": {"latitude": 33.5, "longitude": -84.5},
                "sensors": [
                    {"id": 10, "parameter": {"name": "o3", "units": "ppm"}},
                    {"id": 20, "parameter": {"name": "o3", "units": "ppm"}},
                    {"id": 30, "parameter": {"name": "pm25", "units": "µg/m³"}},
                ],
            }
        ],
    }


def _measurement(value, unit="ppm"):
    return {
        "value": value,
        "parameter": {"name": "o3", "units": unit},
        "period": {
            "datetimeFrom": {"utc": "2026-08-04T00:00:00Z"},
            "datetimeTo": {"utc": "2026-08-04T01:00:00Z"},
        },
    }


def test_openaq_acquisition_uses_sensor_endpoint_and_midpoint():
    responses = {
        "https://api.openaq.org/v3/locations": _location_response(),
        "https://api.openaq.org/v3/sensors/10/measurements": {"results": [_measurement(None)]},
        "https://api.openaq.org/v3/sensors/20/measurements": {"results": [_measurement(0.05)]},
        "https://api.openaq.org/v3/sensors/30/measurements": {"results": {"bad": True}},
    }
    source = OpenAQDataSource(
        session=FakeSession({url: FakeResponse(payload) for url, payload in responses.items()}),
        max_retries=1,
        request_pause=0.0,
    )
    request = DataRequest(
        "ground_monitors",
        "ATL",
        [],
        datetime(2026, 8, 4, tzinfo=timezone.utc),
        datetime(2026, 8, 5, tzinfo=timezone.utc),
    )

    bundle = source.acquire(request, CONFIGURATION)

    assert len(bundle.data) == 2
    assert set(bundle.data["sensor_id"]) == {10, 20}
    assert bundle.data.loc[0, "time"] == pd.Timestamp("2026-08-04 00:30:00Z")
    assert bundle.data.loc[0, "site_id"] == "123"
    assert len(bundle.errors) == 1
    assert bundle.errors[0]["kind"] == "invalid_response"
    assert all(call[0].startswith("https://api.openaq.org/v3/") for call in source.session.calls)
    assert all(call[1]["X-API-Key"] == "test-key" for call in source.session.calls)


def test_openaq_preprocessing_fills_nan_and_selects_highest_sensor_on_conflict():
    data = pd.DataFrame(
        [
            {"site_id": "123", "lat": 33.5, "lon": -84.5, "time": "2026-08-04T00:30Z", "pollutant": "O3", "value": None, "unit": "ppm", "sensor_id": 10},
            {"site_id": "123", "lat": 33.5, "lon": -84.5, "time": "2026-08-04T00:30Z", "pollutant": "O3", "value": 0.05, "unit": "ppm", "sensor_id": 20},
            {"site_id": "123", "lat": 33.5, "lon": -84.5, "time": "2026-08-04T01:30Z", "pollutant": "NO2", "value": 40.0, "unit": "ppb", "sensor_id": 20},
            {"site_id": "123", "lat": 33.5, "lon": -84.5, "time": "2026-08-04T01:30Z", "pollutant": "NO2", "value": 0.05, "unit": "ppm", "sensor_id": 30},
        ]
    )

    processed = OpenAQPreprocessor().preprocess(
        DatasetBundle("ground_monitors", data), CONFIGURATION
    )

    result = processed.data.set_index("time")
    assert result.loc[pd.Timestamp("2026-08-04 00:30:00Z"), "O3"] == 50.0
    assert result.loc[pd.Timestamp("2026-08-04 01:30:00Z"), "NO2"] == 50.0
    assert processed.metadata["competing_sensor_warning_count"] == 1
    assert processed.metadata["warnings"][0]["selected_sensor_id"] == 30


def test_openaq_provider_registers_openaq_adapters():
    manager = DatabaseManager(CONFIGURATION)

    assert isinstance(manager.data_sources["ground_monitors"], OpenAQDataSource)
    assert isinstance(manager.preprocessors["ground_monitors"], OpenAQPreprocessor)
