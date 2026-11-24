"""OpenAQ v3 ground-monitor acquisition adapter."""

from __future__ import annotations

import logging
import time
from typing import Any, Mapping, Optional

import pandas as pd
import requests

from aqdatafusion.contracts import DataRequest, DatasetBundle
from aqdatafusion.data_acquisition.base import AcquisitionError

OPENAQ_URL = "https://api.openaq.org/v3"
POLLUTANTS = ("PM2.5", "PM10", "NO2", "O3", "SO2", "CO")
OPENAQ_PARAMETERS = {
    "pm25": "PM2.5", "pm2.5": "PM2.5", "pm10": "PM10",
    "no2": "NO2", "o3": "O3", "so2": "SO2", "co": "CO",
}


def _utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


class OpenAQDataSource:
    """Acquire OpenAQ measurements for the configured region and interval."""

    source_key = "ground_monitors"

    def __init__(
        self,
        *,
        session: Optional[requests.Session] = None,
        logger: Optional[logging.Logger] = None,
        max_retries: int = 3,
        timeout: float = 60.0,
        page_limit: int = 1000,
        retry_delay: float = 1.0,
        request_pause: float = 2.0,
    ) -> None:
        self.session = session or requests.Session()
        self.logger = logger or logging.getLogger("aqdatafusion.openaq")
        self.max_retries = max(1, max_retries)
        self.timeout = timeout
        self.page_limit = page_limit
        self.retry_delay = max(0.0, retry_delay)
        self.request_pause = max(0.0, request_pause)
        self._last_request_at: Optional[float] = None

    def acquire(self, request: DataRequest, configuration: Mapping[str, Any]) -> DatasetBundle:
        api_key = self._api_key(configuration)
        start, end = self._request_interval(request)
        settings = self._dataset_settings(configuration)
        page_limit = int(settings.get("openaq_page_limit", self.page_limit))
        self.request_pause = max(
            0.0,
            float(settings.get("openaq_request_pause_seconds", self.request_pause)),
        )
        if page_limit <= 0 or page_limit > 1000:
            raise ValueError("OpenAQ page limit must be between 1 and 1000")
        headers = {"X-API-Key": api_key}
        locations = self._discover_locations(headers, self._bbox(configuration), page_limit)
        sensors = self._select_sensors(locations, request.variables)
        records: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        request_count = 0
        for sensor in sensors:
            try:
                sensor_records, pages = self._measure_sensor(headers, sensor, start, end, page_limit)
                request_count += pages
                records.extend(sensor_records)
            except AcquisitionError as error:
                issues.append(error.issue)
                self.logger.warning("OpenAQ sensor %s acquisition failed: %s", sensor["sensor_id"], error)
        columns = ["site_id", "lat", "lon", "time", "pollutant", "value", "unit", "sensor_id", "period_start", "period_end"]
        data = pd.DataFrame(records, columns=columns)
        metadata = {
            "provider": "OpenAQ", "api_version": "v3",
            "location_count": len(locations), "sensor_count": len(sensors),
            "measurement_request_count": request_count, "raw_record_count": len(data),
            "preliminary_site_column": "site_id", "pagination_limit": page_limit,
            "timestamp_source": "period.datetimeFrom/datetimeTo midpoint",
            "request_pause_seconds": self.request_pause,
            "request_interval": {"start": start.isoformat(), "end": end.isoformat()},
        }
        return DatasetBundle(self.source_key, data, metadata, issues)

    def _api_key(self, configuration: Mapping[str, Any]) -> str:
        credentials = configuration.get("credentials", {})
        openaq = credentials.get("openaq", {}) if isinstance(credentials, Mapping) else {}
        api_key = openaq.get("api_key") if isinstance(openaq, Mapping) else None
        if not isinstance(api_key, str) or not api_key.strip() or api_key.startswith("<"):
            raise ValueError("a configured OpenAQ API key is required")
        return api_key.strip()

    def _dataset_settings(self, configuration: Mapping[str, Any]) -> Mapping[str, Any]:
        datasets = configuration.get("input_data", {}).get("datasets", {})
        settings = datasets.get(self.source_key, {}) if isinstance(datasets, Mapping) else {}
        return settings if isinstance(settings, Mapping) else {}

    def _request_interval(self, request: DataRequest) -> tuple[pd.Timestamp, pd.Timestamp]:
        if request.start_time is None or request.end_time is None:
            raise ValueError("OpenAQ acquisition requires start_time and end_time")
        start, end = _utc(request.start_time), _utc(request.end_time)
        if end <= start:
            raise ValueError("OpenAQ end_time must be after start_time")
        return start, end

    def _bbox(self, configuration: Mapping[str, Any]) -> str:
        region = configuration.get("region", {})
        bounds = region.get("bounds", {}) if isinstance(region, Mapping) else {}
        latitude = bounds.get("latitude") if isinstance(bounds, Mapping) else None
        longitude = bounds.get("longitude") if isinstance(bounds, Mapping) else None
        if not isinstance(latitude, (list, tuple)) or not isinstance(longitude, (list, tuple)) or len(latitude) != 2 or len(longitude) != 2:
            raise ValueError("OpenAQ acquisition requires region latitude and longitude bounds")
        return f"{longitude[0]},{latitude[0]},{longitude[1]},{latitude[1]}"

    def _discover_locations(self, headers: Mapping[str, str], bbox: str, page_limit: int) -> list[Mapping[str, Any]]:
        locations: list[Mapping[str, Any]] = []
        page = 1
        while True:
            payload = self._request_json("/locations", headers, {"bbox": bbox, "limit": page_limit, "page": page})
            results = payload.get("results")
            if not isinstance(results, list):
                raise AcquisitionError("OpenAQ locations response is missing a list-valued results field", kind="invalid_response")
            locations.extend(item for item in results if isinstance(item, Mapping))
            if len(results) < page_limit:
                return locations
            page += 1

    def _select_sensors(self, locations: list[Mapping[str, Any]], variables: Any) -> list[dict[str, Any]]:
        requested = {str(variable).upper() for variable in variables}
        requested_pollutants = requested.intersection(POLLUTANTS)
        sensors: list[dict[str, Any]] = []
        seen: set[int] = set()
        for location in locations:
            location_id = location.get("id")
            coordinates = location.get("coordinates", {})
            if location_id is None or not isinstance(coordinates, Mapping):
                continue
            try:
                latitude, longitude = float(coordinates["latitude"]), float(coordinates["longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            raw_sensors = location.get("sensors", [])
            if not isinstance(raw_sensors, list):
                continue
            for sensor in raw_sensors:
                if not isinstance(sensor, Mapping):
                    continue
                parameter = sensor.get("parameter", {})
                name = str(parameter.get("name", "")).casefold() if isinstance(parameter, Mapping) else ""
                pollutant = OPENAQ_PARAMETERS.get(name)
                try:
                    sensor_id = int(sensor["id"])
                except (KeyError, TypeError, ValueError):
                    continue
                if pollutant is None or (requested_pollutants and pollutant not in requested_pollutants) or sensor_id in seen:
                    continue
                seen.add(sensor_id)
                sensors.append({"sensor_id": sensor_id, "site_id": str(location_id), "lat": latitude, "lon": longitude, "pollutant": pollutant, "units": parameter.get("units") if isinstance(parameter, Mapping) else None})
        return sensors

    def _measure_sensor(self, headers: Mapping[str, str], sensor: Mapping[str, Any], start: pd.Timestamp, end: pd.Timestamp, page_limit: int) -> tuple[list[dict[str, Any]], int]:
        records: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self._request_json(f"/sensors/{sensor['sensor_id']}/measurements", headers, {"datetime_from": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "datetime_to": end.strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": page_limit, "page": page, "order_by": "datetime"})
            results = payload.get("results")
            if not isinstance(results, list):
                raise AcquisitionError(f"OpenAQ sensor {sensor['sensor_id']} response is missing results", kind="invalid_response")
            for result in results:
                record = self._measurement_record(result, sensor, start, end)
                if record is not None:
                    records.append(record)
            if len(results) < page_limit:
                return records, page
            page += 1

    def _measurement_record(self, result: Mapping[str, Any], sensor: Mapping[str, Any], start: pd.Timestamp, end: pd.Timestamp) -> Optional[dict[str, Any]]:
        period = result.get("period", {})
        period_start = period.get("datetimeFrom") if isinstance(period, Mapping) else None
        period_end = period.get("datetimeTo") if isinstance(period, Mapping) else None
        if not isinstance(period_start, Mapping) or not isinstance(period_end, Mapping):
            return None
        try:
            source_start, source_end = _utc(period_start["utc"]), _utc(period_end["utc"])
        except (KeyError, TypeError, ValueError):
            return None
        if source_start < start or source_start >= end or source_end <= source_start:
            return None
        value = result.get("value")
        try:
            value = float(value) if value is not None else None
        except (TypeError, ValueError):
            value = None
        parameter = result.get("parameter", {})
        unit = parameter.get("units") if isinstance(parameter, Mapping) else sensor.get("units")
        return {"site_id": sensor["site_id"], "lat": sensor["lat"], "lon": sensor["lon"], "time": source_start + (source_end - source_start) / 2, "pollutant": sensor["pollutant"], "value": value, "unit": unit, "sensor_id": sensor["sensor_id"], "period_start": source_start, "period_end": source_end}

    def _request_json(self, path: str, headers: Mapping[str, str], params: Mapping[str, Any]) -> Mapping[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                if self._last_request_at is not None:
                    elapsed = time.monotonic() - self._last_request_at
                    if elapsed < self.request_pause:
                        time.sleep(self.request_pause - elapsed)
                self._last_request_at = time.monotonic()
                response = self.session.get(f"{OPENAQ_URL}{path}", headers=headers, params=params, timeout=self.timeout)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < self.max_retries:
                        retry_after = response.headers.get("Retry-After")
                        try:
                            delay = float(retry_after) if retry_after is not None else max(self.retry_delay, self.request_pause) * (2 ** (attempt - 1))
                        except ValueError:
                            delay = max(self.retry_delay, self.request_pause) * (2 ** (attempt - 1))
                        time.sleep(delay)
                        continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, Mapping):
                    raise ValueError("response JSON is not an object")
                return payload
            except (requests.RequestException, ValueError) as error:
                if attempt >= self.max_retries:
                    raise AcquisitionError(f"OpenAQ request failed after {attempt} attempts: {error}", kind="api_request", retryable=isinstance(error, requests.RequestException), details={"path": path, "params": dict(params)}) from error
                time.sleep(max(self.retry_delay, self.request_pause) * (2 ** (attempt - 1)))
        raise AssertionError("unreachable")


__all__ = ["OPENAQ_URL", "OpenAQDataSource", "POLLUTANTS"]
