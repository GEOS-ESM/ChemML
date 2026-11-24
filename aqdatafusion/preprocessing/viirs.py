"""Quality control, RSIN geolocation, regridding, and daily VIIRS AOD aggregation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any, Mapping

import numpy as np
import pandas as pd
import xarray as xr
from netCDF4 import Dataset

from aqdatafusion.contracts import DatasetBundle
from aqdatafusion.utils.regridding import regrid_irregular_to_grid


VARIABLE = "optical_depth_055"
SOURCE_VARIABLE = "Optical_Depth_055"


class ViirsAodPreprocessor:
    """Apply configured VJ219A2 QC and produce daily gridded AOD."""

    source_key = "VIIRS"

    def preprocess(
        self, dataset: DatasetBundle, configuration: Mapping[str, Any]
    ) -> DatasetBundle:
        source = configuration.get("input_data", {}).get("datasets", {}).get(
            self.source_key, {}
        )
        quality = source.get("quality_control", {})
        requested_start = dataset.metadata.get("requested_start_time")
        requested_end = dataset.metadata.get("requested_end_time")
        start_time = pd.Timestamp(requested_start) if requested_start else None
        end_time = pd.Timestamp(requested_end) if requested_end else None
        frames: list[pd.DataFrame] = []
        valid_times: dict[pd.Timestamp, int] = {}
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
            timestamp_counts = frame.groupby("time").size()
            for timestamp, count in timestamp_counts.items():
                valid_times[timestamp] = valid_times.get(timestamp, 0) + int(count)
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
        combined["date"] = pd.to_datetime(combined["time"], utc=True).dt.normalize().dt.tz_localize(None)
        days = pd.DatetimeIndex(sorted(combined["date"].unique()))
        daily = combined.groupby(["date", "lat", "lon"], as_index=False)[VARIABLE].mean()
        data = daily.set_index(["date", "lat", "lon"])[VARIABLE].to_xarray()
        data = data.reindex(
            date=days,
            lat=_lat_centers(configuration),
            lon=_lon_centers(configuration),
        ).rename(date="time")
        timestamps = []
        for day in days:
            candidates = [
                (count, timestamp)
                for timestamp, count in valid_times.items()
                if timestamp.normalize().tz_localize(None) == day
            ]
            if candidates:
                timestamp = max(candidates)[1]
                timestamps.append(
                    (timestamp.floor("h") + pd.Timedelta(minutes=30)).tz_localize(None)
                )
            else:
                timestamps.append(day + pd.Timedelta(hours=12, minutes=30))
        result = xr.Dataset({VARIABLE: data}).assign_coords(time=timestamps)
        metadata = {
            **dataset.metadata,
            "preprocessed": True,
            "timestamps_utc": True,
            "quality_control": quality,
            "statistics": statistics,
            "daily_aggregation": "mean after quality control and 0.01-degree spatial regridding",
            "timestamp_selection": "UTC center of overpass hour with most valid source pixels per day",
        }
        return DatasetBundle(self.source_key, result, metadata, list(dataset.errors))


def _read_and_filter(
    path: Path, quality: Mapping[str, Any], configuration: Mapping[str, Any]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    with Dataset(path) as root:
        grid = root.groups["HDFEOS"].groups["GRIDS"].groups["grid750m"]
        x = np.asarray(grid.variables["XDim"][:])
        y = np.asarray(grid.variables["YDim"][:])
        radius, central_meridian = _rsin_parameters(root, x, y)
        xx, yy = np.meshgrid(x, y)
        latitude = np.degrees(yy / radius)
        longitude = np.degrees(central_meridian + xx / (radius * np.cos(yy / radius)))
        values = np.ma.asarray(grid.groups["Data Fields"].variables[SOURCE_VARIABLE][:])
        qa = np.ma.asarray(grid.groups["Data Fields"].variables["AOD_QA"][:])
        timestamps = _timestamps(root)

    resolution = float(quality.get("aod_resolution_min", 0.0))
    maximum = float(quality.get("aod_resolution_max", 6.0))
    qa_mask = int(quality.get("qa_quality_mask", 3))
    qa_max = int(quality.get("qa_quality_max", 1))
    region = _region_mask(latitude, longitude, configuration)
    frames: list[pd.DataFrame] = []
    region_count = int(region.sum()) * values.shape[0]
    qc_count = 0
    for orbit in range(values.shape[0]):
        value = np.asarray(np.ma.filled(values[orbit], np.nan), dtype=float) * 1.0
        quality_value = np.asarray(np.ma.filled(qa[orbit], 0), dtype=np.uint16)
        mask = (
            region
            & np.isfinite(value)
            & (value >= resolution)
            & (value <= maximum)
            & ((quality_value & qa_mask) <= qa_max)
        )
        qc_count += int(mask.sum())
        if not mask.any():
            continue
        lat_values, lon_values = latitude[mask], longitude[mask]
        frames.append(
            pd.DataFrame(
                {
                    "lat": lat_values,
                    "lon": lon_values,
                    "time": pd.Timestamp(timestamps[orbit]),
                    VARIABLE: value[mask],
                }
            )
        )
    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return frame, {
        "file": path.name,
        "region_pixels": region_count,
        "qc_valid_pixels": qc_count,
        "orbit_count": len(timestamps),
    }


def _timestamps(root: Any) -> list[pd.Timestamp]:
    values = str(root.getncattr("TimeStamp")).split(",")
    output = []
    for value in values:
        year, day, hour, minute = int(value[:4]), int(value[4:7]), int(value[7:9]), int(value[9:11])
        timestamp = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(
            days=day - 1, hours=hour, minutes=minute
        )
        output.append(pd.Timestamp(timestamp))
    return output


def _rsin_parameters(root: Any, x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Return the granule-specific RSIN sphere radius and central meridian.

    VJ219A2 stores projected cell-center coordinates relative to a zonal
    central meridian.  The meridian is recovered from the four granule corner
    coordinates rather than inferred from a particular tile or region.
    """
    projection = root.groups["HDFEOS INFORMATION"].variables["StructMetadata.0"][:]
    if isinstance(projection, np.ndarray):
        projection = projection.item()
    match = re.search(r"ProjParams=\(([-+0-9.]+)", str(projection))
    if not match:
        raise ValueError("VIIRS granule is missing the RSIN projection radius")
    radius = float(match.group(1))
    longitude = np.asarray(root.getncattr("GRingLongitude"), dtype=float)
    latitude = np.asarray(root.getncattr("GRingLatitude"), dtype=float)
    if longitude.size != 4 or latitude.size != 4:
        raise ValueError("VIIRS granule must provide four geolocation corners")
    x_corners = np.array([x[0], x[-1], x[-1], x[0]])
    central = np.radians(longitude) - x_corners / (radius * np.cos(np.radians(latitude)))
    # GRing longitudes are stored at limited decimal precision, so allow the
    # resulting small corner spread while still rejecting malformed metadata.
    if not np.all(np.isfinite(central)) or np.ptp(central) > 5.0e-4:
        raise ValueError("VIIRS granule corner metadata is inconsistent with RSIN coordinates")
    return radius, float(np.nanmean(central))


def _region_mask(latitude: np.ndarray, longitude: np.ndarray, configuration: Mapping[str, Any]) -> np.ndarray:
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
    resolution = float(configuration["input_data"]["datasets"]["VIIRS"]["regridding"]["latlon_resolution"])
    return bounds[0] + (np.arange(int(np.ceil((bounds[1] - bounds[0]) / resolution))) + 0.5) * resolution


def _lon_centers(configuration: Mapping[str, Any]) -> np.ndarray:
    bounds = configuration["region"]["bounds"]["longitude"]
    resolution = float(configuration["input_data"]["datasets"]["VIIRS"]["regridding"]["latlon_resolution"])
    return bounds[0] + (np.arange(int(np.ceil((bounds[1] - bounds[0]) / resolution))) + 0.5) * resolution


def _empty_dataset(configuration: Mapping[str, Any]) -> xr.Dataset:
    lat, lon = _lat_centers(configuration), _lon_centers(configuration)
    return xr.Dataset(
        {VARIABLE: (("time", "lat", "lon"), np.empty((0, len(lat), len(lon))))},
        coords={"time": [], "lat": lat, "lon": lon},
    )


__all__ = ["ViirsAodPreprocessor", "VARIABLE"]
