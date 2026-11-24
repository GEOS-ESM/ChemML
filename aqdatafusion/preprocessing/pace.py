"""Quality control, regridding, and daily aggregation for PACE trace gases."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import xarray as xr
from netCDF4 import Dataset

from aqdatafusion.contracts import DatasetBundle
from aqdatafusion.utils.regridding import regrid_irregular_to_grid


VARIABLES = ("total_column_no2", "total_column_o3")


class PaceTraceGasPreprocessor:
    """Apply the PACE quality flags and produce a daily 0.02-degree dataset."""

    source_key = "PACE"

    def preprocess(
        self, dataset: DatasetBundle, configuration: Mapping[str, Any]
    ) -> DatasetBundle:
        source = configuration.get("input_data", {}).get("datasets", {}).get(
            self.source_key, {}
        )
        quality = source.get("quality_control", {})
        start_time = _optional_timestamp(dataset.metadata.get("requested_start_time"))
        end_time = _optional_timestamp(dataset.metadata.get("requested_end_time"))
        frames: list[pd.DataFrame] = []
        valid_counts: dict[pd.Timestamp, int] = {}
        statistics: list[dict[str, Any]] = []
        for file_name in dataset.data:
            frame, stats = _read_and_filter(Path(file_name), quality, configuration)
            statistics.append(stats)
            if frame.empty:
                continue
            if start_time is not None:
                frame = frame[frame["time"] >= start_time]
            if end_time is not None:
                frame = frame[frame["time"] < end_time]
            if frame.empty:
                continue
            counts = frame.groupby("time")[list(VARIABLES)].count().sum(axis=1)
            for timestamp, count in counts.items():
                valid_counts[timestamp] = int(count)
            frames.append(
                regrid_irregular_to_grid(
                    frame, configuration, source_key=self.source_key
                )
            )

        if not frames:
            return DatasetBundle(
                self.source_key,
                _empty_dataset(configuration),
                {
                    **dataset.metadata,
                    "preprocessed": True,
                    "timestamps_utc": True,
                    "quality_control": quality,
                    "statistics": statistics,
                },
                list(dataset.errors),
            )

        combined = pd.concat(frames, ignore_index=True)
        combined["date"] = (
            pd.to_datetime(combined["time"], utc=True).dt.normalize().dt.tz_localize(None)
        )
        days = pd.DatetimeIndex(sorted(combined["date"].unique()))
        daily = combined.groupby(["date", "lat", "lon"], as_index=False)[list(VARIABLES)].mean()
        arrays = {
            variable: daily.set_index(["date", "lat", "lon"])[variable]
            .to_xarray()
            .rename(date="time")
            for variable in VARIABLES
        }
        timestamps = []
        for day in days:
            candidates = [
                (count, timestamp)
                for timestamp, count in valid_counts.items()
                if timestamp.normalize().tz_localize(None) == day
            ]
            if candidates:
                timestamp = max(candidates)[1]
                timestamps.append(
                    (timestamp.floor("h") + pd.Timedelta(minutes=30)).tz_localize(None)
                )
            else:
                timestamps.append(day + pd.Timedelta(hours=12, minutes=30))
        result = xr.Dataset(arrays).assign_coords(time=timestamps).sortby("time")
        metadata = {
            **dataset.metadata,
            "preprocessed": True,
            "timestamps_utc": True,
            "quality_control": quality,
            "statistics": statistics,
            "daily_aggregation": "mean after quality control and 0.02-degree spatial regridding",
            "timestamp_selection": "UTC center of overpass hour with most combined valid source pixels per day",
        }
        return DatasetBundle(self.source_key, result, metadata, list(dataset.errors))


def _read_and_filter(
    path: Path, quality: Mapping[str, Any], configuration: Mapping[str, Any]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    with Dataset(path) as root:
        geolocation = root.groups["geolocation_data"]
        geophysical = root.groups["geophysical_data"]
        latitude = _array(geolocation, "latitude")
        longitude = _array(geolocation, "longitude")
        no2 = _array(geophysical, "total_column_no2")
        o3 = _array(geophysical, "total_column_o3")
        no2_quality = _array(geophysical, "quality_no2")
        o3_quality = _array(geophysical, "quality_o3")
        timestamp = pd.Timestamp(root.getncattr("time_coverage_start"))
    region = _region_mask(latitude, longitude, configuration)
    no2_mask = region & np.isfinite(no2) & (no2_quality == int(quality.get("no2_good_value", 0)))
    o3_mask = region & np.isfinite(o3) & (o3_quality == int(quality.get("o3_good_value", 0)))
    if not (no2_mask.any() or o3_mask.any()):
        return pd.DataFrame(), {
            "file": path.name,
            "region_pixels": int(region.sum()),
            "no2_qc_valid_pixels": int(no2_mask.sum()),
            "o3_qc_valid_pixels": int(o3_mask.sum()),
        }
    frame = pd.DataFrame(
        {
            "lat": latitude[region],
            "lon": longitude[region],
            "time": timestamp,
            "total_column_no2": np.where(no2_mask[region], no2[region], np.nan),
            "total_column_o3": np.where(o3_mask[region], o3[region], np.nan),
        }
    )
    return frame, {
        "file": path.name,
        "region_pixels": int(region.sum()),
        "no2_qc_valid_pixels": int(no2_mask.sum()),
        "o3_qc_valid_pixels": int(o3_mask.sum()),
    }


def _array(group: Any, name: str) -> np.ndarray:
    value = group.variables[name][:]
    if np.ma.isMaskedArray(value):
        value = value.astype(float).filled(np.nan)
    return np.asarray(value).squeeze()


def _optional_timestamp(value: Any) -> pd.Timestamp | None:
    return pd.Timestamp(value) if value else None


def _region_mask(
    latitude: np.ndarray, longitude: np.ndarray, configuration: Mapping[str, Any]
) -> np.ndarray:
    bounds = configuration["region"]["bounds"]
    return (
        np.isfinite(latitude)
        & np.isfinite(longitude)
        & (latitude >= float(bounds["latitude"][0]))
        & (latitude < float(bounds["latitude"][1]))
        & (longitude >= float(bounds["longitude"][0]))
        & (longitude < float(bounds["longitude"][1]))
    )


def _lat_centers(configuration: Mapping[str, Any]) -> np.ndarray:
    bounds = configuration["region"]["bounds"]["latitude"]
    resolution = float(configuration["input_data"]["datasets"]["PACE"]["regridding"]["latlon_resolution"])
    return bounds[0] + (np.arange(int(np.ceil((bounds[1] - bounds[0]) / resolution))) + 0.5) * resolution


def _lon_centers(configuration: Mapping[str, Any]) -> np.ndarray:
    bounds = configuration["region"]["bounds"]["longitude"]
    resolution = float(configuration["input_data"]["datasets"]["PACE"]["regridding"]["latlon_resolution"])
    return bounds[0] + (np.arange(int(np.ceil((bounds[1] - bounds[0]) / resolution))) + 0.5) * resolution


def _empty_dataset(configuration: Mapping[str, Any]) -> xr.Dataset:
    lat, lon = _lat_centers(configuration), _lon_centers(configuration)
    return xr.Dataset(
        {
            variable: (("time", "lat", "lon"), np.empty((0, len(lat), len(lon))))
            for variable in VARIABLES
        },
        coords={"time": [], "lat": lat, "lon": lon},
    )


__all__ = ["PaceTraceGasPreprocessor", "VARIABLES"]
