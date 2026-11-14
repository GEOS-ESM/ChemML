"""AirNow historical monitor acquisition adapter."""

from __future__ import annotations

import logging
import time
from typing import Any, Mapping, Optional, Sequence

import pandas as pd
import requests

from aqforecast.contracts import DataRequest, DatasetBundle

AIRNOW_URL = "https://www.airnowapi.org/aq/data/"
POLLUTANTS = ("PM2.5", "PM10", "NO2", "O3", "SO2", "CO")
API_PARAMETERS = {
    "PM2.5": "PM25",
    "PM10": "PM10",
    "NO2": "NO2",
    "O3": "OZONE",
    "SO2": "SO2",
    "CO": "CO",
}


def _utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


class AirNowDataSource:
    """Acquire AirNow monitor data and return a preliminary flat DataFrame.

    The adapter uses the historical AirNow request parameters verified for the
    ATL region. It keeps the API's AQS identifier as ``aqs_id`` and retains a
    temporary unit column for every pollutant. The source-specific preprocessor
    converts and quality-controls those values before archiving.
    """

    source_key = "ground_monitors"

    def __init__(
        self,
        *,
        session: Optional[requests.Session] = None,
        logger: Optional[logging.Logger] = None,
        max_retries: int = 3,
        timeout: float = 60.0,
        max_query_hours: int = 168,
    ) -> None:
        self.session = session or requests.Session()
        self.logger = logger or logging.getLogger("aqforecast.airnow")
        self.max_retries = max(1, max_retries)
        self.timeout = timeout
        self.max_query_hours = max_query_hours

    def acquire(
        self,
        request: DataRequest,
        configuration: Mapping[str, Any],
    ) -> DatasetBundle:
        api_key = self._api_key(configuration)
        start, end = self._request_interval(request)
        settings = self._dataset_settings(configuration)
        chunk_hours = int(
            settings.get("max_query_hours", self.max_query_hours)
        )
        if chunk_hours <= 0:
            raise ValueError("AirNow max_query_hours must be positive")

        parameters = self._parameters(request.variables)
        bbox = self._bbox(configuration)
        records: list[Mapping[str, Any]] = []
        chunks: list[dict[str, Any]] = []
        chunk_start = start
        while chunk_start < end:
            chunk_end = min(chunk_start + pd.Timedelta(hours=chunk_hours), end)
            # ChemML uses [start, end); AirNow's endDate is inclusive and has
            # hour precision, so request the final source hour in the chunk.
            source_end = chunk_end - pd.Timedelta(hours=1)
            if source_end < chunk_start:
                raise ValueError("AirNow requests must span at least one hour")
            query = {
                "startDate": self._format_datetime(chunk_start),
                "endDate": self._format_datetime(source_end),
                "parameters": parameters,
                "BBOX": bbox,
                "dataType": "C",
                "format": "application/json",
                "monitorType": 2,
                "verbose": 1,
                "includeRawConcentrations": 0,
                "API_KEY": api_key,
            }
            payload = self._request_with_retries(query)
            records.extend(payload)
            chunks.append(
                {
                    "start": query["startDate"],
                    "end": query["endDate"],
                    "records": len(payload),
                }
            )
            chunk_start = chunk_end

        data = self._records_to_frame(records)
        metadata = {
            "provider": "AirNow",
            "request_parameters": {
                key: value for key, value in query.items() if key != "API_KEY"
            },
            "query_chunks": chunks,
            "raw_record_count": len(records),
            "preliminary_site_column": "aqs_id",
            "temporary_unit_columns": [
                f"{pollutant}_unit" for pollutant in POLLUTANTS
            ],
            "timestamps_centered_minutes": 30,
        }
        return DatasetBundle(self.source_key, data, metadata)

    def _api_key(self, configuration: Mapping[str, Any]) -> str:
        credentials = configuration.get("credentials", {})
        airnow = (
            credentials.get("airnow", {})
            if isinstance(credentials, Mapping)
            else {}
        )
        api_key = (
            airnow.get("api_key") if isinstance(airnow, Mapping) else None
        )
        if (
            not isinstance(api_key, str)
            or not api_key.strip()
            or api_key.startswith("<")
        ):
            raise ValueError("a configured AirNow API key is required")
        return api_key.strip()

    def _dataset_settings(
        self, configuration: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        datasets = configuration.get("input_data", {}).get("datasets", {})
        settings = (
            datasets.get(self.source_key, {})
            if isinstance(datasets, Mapping)
            else {}
        )
        return settings if isinstance(settings, Mapping) else {}

    def _request_interval(
        self, request: DataRequest
    ) -> tuple[pd.Timestamp, pd.Timestamp]:
        if request.start_time is None or request.end_time is None:
            raise ValueError(
                "AirNow acquisition requires start_time and end_time"
            )
        start, end = _utc(request.start_time), _utc(request.end_time)
        if end <= start:
            raise ValueError("AirNow end_time must be after start_time")
        if start != start.floor("h") or end != end.floor("h"):
            raise ValueError(
                "AirNow request times must be aligned to whole UTC hours"
            )
        return start, end

    def _parameters(self, variables: Sequence[str]) -> str:
        requested = {str(variable) for variable in variables}
        selected = [
            pollutant for pollutant in POLLUTANTS if pollutant in requested
        ]
        if not selected:
            selected = list(POLLUTANTS)
        return ",".join(API_PARAMETERS[pollutant] for pollutant in selected)

    def _bbox(self, configuration: Mapping[str, Any]) -> str:
        region = configuration.get("region", {})
        bounds = (
            region.get("bounds", {}) if isinstance(region, Mapping) else {}
        )
        latitude = (
            bounds.get("latitude") if isinstance(bounds, Mapping) else None
        )
        longitude = (
            bounds.get("longitude") if isinstance(bounds, Mapping) else None
        )
        if (
            not isinstance(latitude, Sequence)
            or not isinstance(longitude, Sequence)
            or len(latitude) != 2
            or len(longitude) != 2
        ):
            raise ValueError(
                "AirNow acquisition requires region latitude and "
                "longitude bounds"
            )
        return f"{longitude[0]},{latitude[0]},{longitude[1]},{latitude[1]}"

    @staticmethod
    def _format_datetime(value: Any) -> str:
        return _utc(value).strftime("%Y-%m-%dT%H")

    def _request_with_retries(
        self, query: Mapping[str, Any]
    ) -> list[Mapping[str, Any]]:
        public_query = {
            key: value for key, value in query.items() if key != "API_KEY"
        }
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(
                    AIRNOW_URL, params=query, timeout=self.timeout
                )
                if response.status_code in {429, 500, 502, 503, 504}:
                    response.raise_for_status()
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list):
                    raise ValueError(
                        "AirNow returned a non-list JSON response"
                    )
                return payload
            except (requests.RequestException, ValueError) as error:
                if attempt >= self.max_retries:
                    self.logger.error(
                        "AirNow request failed after %d attempts: %s",
                        attempt,
                        public_query,
                    )
                    raise RuntimeError(
                        f"AirNow request failed after {attempt} attempts: "
                        f"{error}"
                    ) from error
                delay = min(60.0, 2 ** (attempt - 1))
                self.logger.warning(
                    "AirNow request retry %d/%d after %s; waiting %.1fs",
                    attempt,
                    self.max_retries,
                    error,
                    delay,
                )
                time.sleep(delay)
        raise AssertionError("unreachable")

    def _records_to_frame(
        self, records: Sequence[Mapping[str, Any]]
    ) -> pd.DataFrame:
        rows: dict[tuple[str, pd.Timestamp], dict[str, Any]] = {}
        skipped = 0
        parameter_names = {
            "PM25": "PM2.5",
            "PM2.5": "PM2.5",
            "PM10": "PM10",
            "NO2": "NO2",
            "OZONE": "O3",
            "O3": "O3",
            "SO2": "SO2",
            "CO": "CO",
        }
        for record in records:
            site_id = record.get("FullAQSCode")
            parameter = parameter_names.get(
                str(record.get("Parameter", "")).upper()
            )
            if site_id in (None, "") or parameter is None:
                skipped += 1
                continue
            try:
                timestamp = _utc(record["UTC"]) + pd.Timedelta(minutes=30)
                latitude = float(record["Latitude"])
                longitude = float(record["Longitude"])
            except (KeyError, TypeError, ValueError):
                skipped += 1
                continue
            key = (str(site_id), timestamp)
            row = rows.setdefault(
                key,
                {
                    "aqs_id": str(site_id),
                    "lat": latitude,
                    "lon": longitude,
                    "time": timestamp,
                },
            )
            for pollutant in POLLUTANTS:
                row.setdefault(pollutant, float("nan"))
                row.setdefault(f"{pollutant}_unit", None)
            row[parameter] = record.get("Value")
            row[f"{parameter}_unit"] = record.get("Unit")
        if skipped:
            self.logger.warning(
                "Skipped %d malformed or unsupported AirNow records", skipped
            )
        columns = ["aqs_id", "lat", "lon", "time"]
        columns.extend(
            value
            for pollutant in POLLUTANTS
            for value in (pollutant, f"{pollutant}_unit")
        )
        data = pd.DataFrame(rows.values(), columns=columns)
        if not data.empty:
            data = data.sort_values(["aqs_id", "time"]).reset_index(drop=True)
        data["time"] = pd.to_datetime(data["time"], utc=True)
        return data


__all__ = ["AIRNOW_URL", "AirNowDataSource"]
