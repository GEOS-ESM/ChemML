"""Preprocessing for GEOS-CF analysis and forecast records."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd
import xarray as xr

from aqforecast.contracts import DatasetBundle


SOURCE_KEY = "GEOS-CF"
LEAD_DIMENSION = "forecast_lead_day"


class GeosCfPreprocessor:
    """Combine streams while preserving analysis/forecast lead records."""

    source_key = SOURCE_KEY

    def preprocess(
        self, dataset: DatasetBundle, configuration: Mapping[str, Any]
    ) -> DatasetBundle:
        records = dataset.data if isinstance(dataset.data, (list, tuple)) else [dataset.data]
        frames: list[xr.Dataset] = []
        statistics: list[dict[str, Any]] = []
        for record in records:
            if record is None or not isinstance(record, xr.Dataset) or "time" not in record:
                continue
            stream = str(record.attrs.get("geos_cf_stream", "ana")).casefold()
            initialization = record.attrs.get("forecast_initialization_time")
            current = record.copy(deep=True)
            if "lev" in current.dims and current.sizes["lev"] == 1:
                current = current.squeeze("lev", drop=True)
            valid_count = 0
            input_count = 0
            for name in current.data_vars:
                values = current[name]
                input_count += int(values.size)
                finite = np.isfinite(values)
                valid_count += int(finite.sum())
                current[name] = values.where(finite)
            leads = np.zeros(current.sizes["time"], dtype=int) if stream == "ana" else _forecast_leads(current.time.values, initialization)
            for lead in sorted(set(leads.tolist())):
                lead_frame = current.isel(time=leads == lead)
                lead_frame = lead_frame.expand_dims({LEAD_DIMENSION: [lead]})
                lead_frame = lead_frame.reindex({LEAD_DIMENSION: range(6)})
                frames.append(lead_frame)
                statistics.append({
                    "stream": stream,
                    "forecast_initialization_time": initialization,
                    "forecast_lead_day": int(lead),
                    "input_values": input_count,
                    "finite_values": valid_count,
                })

        if frames:
            result = _combine_by_valid_time(frames)
            start, end = _request_bounds(dataset.metadata)
            if start is not None:
                result = result.sel(time=result.time >= start)
            if end is not None:
                result = result.sel(time=result.time < end)
        else:
            result = _empty_dataset(configuration)

        result.attrs.update({
            "source": "GEOS-CF v2",
            "preprocessing": "native-grid stream merge with finite-value filtering",
            "timestamps": "UTC, hourly records normalized to center-of-hour valid time",
            "forecast_lead_day": "analysis=0; forecast lead days=1 through 5 from 09Z initialization",
            "quality_control": "retain finite values; NaN and infinite values replaced with NaN",
        })
        metadata = {
            **dataset.metadata,
            "preprocessed": True,
            "timestamps_utc": True,
            "forecast_lead_dimension": LEAD_DIMENSION,
            "statistics": statistics,
        }
        return DatasetBundle(self.source_key, result, metadata, list(dataset.errors))


def _forecast_leads(times: np.ndarray, initialization: Any) -> np.ndarray:
    if not initialization:
        raise ValueError("GEOS-CF forecast record lacks initialization metadata")
    init = pd.Timestamp(initialization)
    if init.tzinfo is None:
        init = init.tz_localize("UTC")
    valid = pd.DatetimeIndex(pd.to_datetime(times, utc=True))
    elapsed = (valid - init.tz_convert("UTC")) / pd.Timedelta(days=1)
    leads = np.floor(np.asarray(elapsed, dtype=float)).astype(int) + 1
    if np.any((leads < 1) | (leads > 5)):
        raise ValueError("GEOS-CF forecast valid time is outside lead days 1-5")
    return leads


def _combine_by_valid_time(frames: list[xr.Dataset]) -> xr.Dataset:
    combined = xr.concat(frames, dim="time").sortby("time")
    times = pd.DatetimeIndex(pd.to_datetime(combined.time.values, utc=True))
    records: list[xr.Dataset] = []
    output_times: list[pd.Timestamp] = []
    for timestamp in times.unique().sort_values():
        positions = [index for index, value in enumerate(times) if value == timestamp]
        record = combined.isel(time=positions[0], drop=True)
        for position in positions[1:]:
            record = record.combine_first(combined.isel(time=position, drop=True))
        records.append(record.expand_dims(time=[timestamp.tz_localize(None)]))
        output_times.append(timestamp.tz_localize(None))
    return xr.concat(records, dim="time").assign_coords(time=output_times).sortby("time")


def _request_bounds(metadata: Mapping[str, Any]) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    values = []
    for name in ("request_start_time", "request_end_time"):
        value = metadata.get(name)
        if value is None:
            values.append(None)
            continue
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        values.append(timestamp.tz_convert("UTC").tz_localize(None))
    return values[0], values[1]


def _empty_dataset(configuration: Mapping[str, Any]) -> xr.Dataset:
    bounds = configuration.get("region", {}).get("bounds", {})
    resolution = float(
        configuration.get("input_data", {})
        .get("datasets", {})
        .get(SOURCE_KEY, {})
        .get("regridding", {})
        .get("latlon_resolution", 0.25)
    )
    latitude = np.arange(float(bounds.get("latitude", [0, resolution])[0]), float(bounds.get("latitude", [0, resolution])[1]) + resolution / 2, resolution)
    longitude = np.arange(float(bounds.get("longitude", [0, resolution])[0]), float(bounds.get("longitude", [0, resolution])[1]) + resolution / 2, resolution)
    return xr.Dataset(
        coords={
            "time": np.array([], dtype="datetime64[ns]"),
            LEAD_DIMENSION: np.arange(6, dtype="int8"),
            "lat": latitude,
            "lon": longitude,
        }
    )


__all__ = ["GeosCfPreprocessor", "LEAD_DIMENSION"]
