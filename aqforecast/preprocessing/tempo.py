"""Quality control and hourly aggregation for cached TEMPO NO2 subsets."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import xarray as xr

from aqforecast.contracts import DatasetBundle


SCIENCE_VARIABLE = "vertical_column_troposphere"


class TempoNo2Preprocessor:
    source_key = "TEMPO_NO2"

    def preprocess(
        self, dataset: DatasetBundle, configuration: Mapping[str, Any]
    ) -> DatasetBundle:
        source = configuration.get("input_data", {}).get("datasets", {}).get(
            self.source_key, {}
        )
        quality = source.get("quality_control", {})
        frames: list[xr.Dataset] = []
        statistics: list[dict[str, int]] = []
        for path in dataset.data:
            with xr.open_dataset(Path(path)) as cached:
                current = cached.load()
            if SCIENCE_VARIABLE not in current or "main_data_quality_flag" not in current:
                continue
            value = current[SCIENCE_VARIABLE].astype("float64").squeeze(drop=True)
            flag = current["main_data_quality_flag"].astype("float64").squeeze(drop=True)
            valid = np.isfinite(value) & np.isfinite(flag)
            valid &= flag <= float(quality.get("quality_flag_max", 1))
            cleaned = value.where(valid)
            timestamp = _timestamp(current)
            cleaned = cleaned.expand_dims(time=[timestamp])
            cleaned = cleaned.rename({"latitude": "lat", "longitude": "lon"})
            frames.append(cleaned.to_dataset(name=SCIENCE_VARIABLE))
            statistics.append(
                {"input_pixels": int(value.size), "qc_valid_pixels": int(valid.sum())}
            )
        if not frames:
            result = _empty_dataset(configuration)
        else:
            combined = xr.concat(frames, dim="time").sortby("time")
            valid_count = combined[SCIENCE_VARIABLE].count(dim=("lat", "lon"))
            result = combined.groupby("time").mean(dim="time", skipna=True)
            result["valid_pixel_count"] = valid_count.groupby("time").sum(dim="time")
            start = _request_timestamp(dataset.metadata.get("request_start_time"))
            end = _request_timestamp(dataset.metadata.get("request_end_time"))
            if start is not None:
                result = result.sel(time=result.time >= start)
            if end is not None:
                result = result.sel(time=result.time < end)
        result.attrs.update(
            {
                "source": "TEMPO_NO2_L3 V04",
                "preprocessing": "OpenDAP spatial subsets, quality control, hourly averaging",
                "quality_control": "finite science and flag values with main_data_quality_flag <= configured maximum; negative NO2 retained",
                "grid": "native approximately 0.02 degree latitude-longitude grid; no regridding",
                "timestamps": "UTC, aligned to the center of the hour",
            }
        )
        metadata = {
            **dataset.metadata,
            "preprocessed": True,
            "timestamps_utc": True,
            "quality_control": quality,
            "statistics": statistics,
            "hourly_aggregation": "mean after quality control; duplicate granules in an hour averaged",
        }
        return DatasetBundle(self.source_key, result, metadata, list(dataset.errors))


def _timestamp(dataset: xr.Dataset) -> pd.Timestamp:
    value = dataset.attrs.get("time_coverage_start")
    if value is None:
        value = dataset.attrs.get("time_coverage_start_since_epoch")
    if isinstance(value, (float, int)):
        timestamp = pd.Timestamp("1980-01-06", tz="UTC") + pd.to_timedelta(value, unit="s")
    else:
        timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    return (timestamp.tz_convert("UTC").floor("h") + pd.Timedelta(minutes=30)).tz_localize(None)


def _request_timestamp(value: Any) -> np.datetime64 | None:
    if value is None:
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    return np.datetime64(timestamp.tz_convert("UTC").tz_localize(None).to_datetime64())


def _empty_dataset(configuration: Mapping[str, Any]) -> xr.Dataset:
    bounds = configuration["region"]["bounds"]
    resolution = float(configuration["input_data"]["datasets"]["TEMPO_NO2"]["regridding"].get("latlon_resolution", 0.02))
    lat = bounds["latitude"][0] + (np.arange(int(np.ceil((bounds["latitude"][1] - bounds["latitude"][0]) / resolution))) + 0.5) * resolution
    lon = bounds["longitude"][0] + (np.arange(int(np.ceil((bounds["longitude"][1] - bounds["longitude"][0]) / resolution))) + 0.5) * resolution
    return xr.Dataset({SCIENCE_VARIABLE: (("time", "lat", "lon"), np.empty((0, len(lat), len(lon))))}, coords={"time": [], "lat": lat, "lon": lon})


__all__ = ["TempoNo2Preprocessor"]
