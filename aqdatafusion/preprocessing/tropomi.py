"""Quality control, regridding, and daily aggregation for TROPOMI."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
import xarray as xr
from netCDF4 import Dataset

from aqdatafusion.contracts import DatasetBundle
from aqdatafusion.utils.regridding import regrid_irregular_to_grid


VARIABLES = {
    "no2": ("tropospheric_no2_column", "nitrogendioxide_tropospheric_column"),
    "o3": ("total_o3_column", "ozone_total_vertical_column"),
}


class TropomiPreprocessor:
    """Apply configured moderate filtering and produce one daily xarray dataset."""

    source_key = "TROPOMI"

    def preprocess(
        self,
        dataset: DatasetBundle,
        configuration: Mapping[str, Any],
    ) -> DatasetBundle:
        if dataset is None:
            return dataset
        source = configuration.get("input_data", {}).get("datasets", {}).get(
            self.source_key, {}
        )
        quality = source.get("quality_control", {})
        files_by_product = dataset.metadata.get("files_by_product", {})
        if not files_by_product:
            paths = [Path(path) for path in dataset.data]
            files_by_product = {
                "no2": [str(path) for path in paths if "NO2" in path.name],
                "o3": [str(path) for path in paths if "O3" in path.name],
            }

        daily_days: set[pd.Timestamp] = set()
        valid_times: dict[pd.Timestamp, list[pd.Timestamp]] = {}
        gridded: dict[str, list[pd.DataFrame]] = {"no2": [], "o3": []}
        statistics: dict[str, list[dict[str, int]]] = {"no2": [], "o3": []}
        for product in ("no2", "o3"):
            value_name = VARIABLES[product][0]
            for file_name in files_by_product.get(product, []):
                frame, file_days, file_times, stats = _read_and_filter(
                    Path(file_name), product, quality, configuration
                )
                daily_days.update(file_days)
                for timestamp in file_times:
                    valid_times.setdefault(timestamp.normalize(), []).append(timestamp)
                statistics[product].append(stats)
                if frame.empty:
                    continue
                pass_hour = (
                    pd.Series(frame["time"])
                    .dt.floor("h")
                    .value_counts()
                    .sort_values(ascending=False)
                    .index[0]
                )
                frame["time"] = pass_hour + pd.Timedelta(minutes=30)
                gridded_frame = regrid_irregular_to_grid(
                    frame,
                    configuration,
                    source_key=self.source_key,
                )
                statistics[product][-1]["grid_cells"] = int(
                    gridded_frame[value_name].notna().sum()
                )
                gridded[product].append(gridded_frame)

        if not daily_days:
            return DatasetBundle(
                self.source_key,
                _empty_dataset(configuration),
                {**dataset.metadata, "preprocessed": True, "timestamps_utc": True},
                list(dataset.errors),
            )

        days = pd.DatetimeIndex(sorted(daily_days))
        data_arrays: dict[str, xr.DataArray] = {}
        for product, (variable, _) in VARIABLES.items():
            frames = gridded[product]
            if frames:
                combined = pd.concat(frames, ignore_index=True)
                combined["date"] = pd.to_datetime(combined["time"], utc=True).dt.normalize().dt.tz_localize(None)
                daily = (
                    combined.groupby(["date", "lat", "lon"], as_index=False)[variable]
                    .mean()
                )
                data_array = daily.set_index(["date", "lat", "lon"])[variable].to_xarray()
                data_array = data_array.reindex(date=days.tz_localize(None), lat=_lat_centers(configuration), lon=_lon_centers(configuration))
                data_arrays[variable] = data_array.rename(date="time")
            else:
                data_arrays[variable] = xr.DataArray(
                    np.full((len(days), len(_lat_centers(configuration)), len(_lon_centers(configuration))), np.nan),
                    dims=("time", "lat", "lon"),
                    coords={"time": days.tz_localize(None), "lat": _lat_centers(configuration), "lon": _lon_centers(configuration)},
                )

        timestamps = []
        for day in days:
            candidates = valid_times.get(day, [])
            if candidates:
                hour = pd.Series(candidates).dt.floor("h").value_counts().sort_values(ascending=False).index[0]
                timestamps.append((hour + pd.Timedelta(minutes=30)).tz_localize(None))
            else:
                timestamps.append(day + pd.Timedelta(hours=12, minutes=30))
        result = xr.Dataset(data_arrays).assign_coords(time=timestamps)
        metadata = {
            **dataset.metadata,
            "preprocessed": True,
            "timestamps_utc": True,
            "quality_control": quality,
            "statistics": statistics,
            "daily_aggregation": "mean after quality control and spatial regridding",
            "timestamp_selection": "UTC center of hour with most valid source pixels per day",
        }
        return DatasetBundle(self.source_key, result, metadata, list(dataset.errors))


def _read_and_filter(
    path: Path,
    product: str,
    quality: Mapping[str, Any],
    configuration: Mapping[str, Any],
) -> tuple[pd.DataFrame, set[pd.Timestamp], list[pd.Timestamp], dict[str, int]]:
    with Dataset(path) as root:
        product_group = root.groups["PRODUCT"]
        support = product_group.groups["SUPPORT_DATA"]
        geo = support.groups["GEOLOCATIONS"]
        inputs = support.groups["INPUT_DATA"]
        details = support.groups["DETAILED_RESULTS"]
        latitude = _array(product_group, "latitude")
        longitude = _array(product_group, "longitude")
        qa = _array(product_group, "qa_value")
        solar_zenith = _array(geo, "solar_zenith_angle")
        times = pd.to_datetime(
            np.asarray(product_group.variables["time_utc"][:]).reshape(-1),
            utc=True,
            format="mixed",
        )
        if product == "no2":
            value = _array(product_group, "nitrogendioxide_tropospheric_column")
            cloud = _array(details, "cloud_fraction_crb_nitrogendioxide_window")
            value_name = "tropospheric_no2_column"
            valid_value = value > float(quality.get("no2_min", -5e-5))
        else:
            value = _array(product_group, "ozone_total_vertical_column")
            cloud = _array(inputs, "cloud_fraction_crb", "cloud_fraction")
            value_name = "total_o3_column"
            valid_value = (
                (value > float(quality.get("o3_min", 0.05)))
                & (value < float(quality.get("o3_max", 0.25)))
            )
        region = _region_mask(latitude, longitude, configuration)
        qc_mask = (
            region
            & np.isfinite(value)
            & (qa > float(quality.get("qa_min", 0.5)))
            & np.isfinite(cloud)
            & (cloud < float(quality.get("cloud_fraction_max", 0.5)))
            & np.isfinite(solar_zenith)
            & (solar_zenith < float(quality.get("solar_zenith_angle_max", 80.0)))
            & valid_value
        )
        scanline = np.broadcast_to(np.arange(latitude.shape[0])[:, None], latitude.shape)
        days = {timestamp.normalize() for timestamp in times}
        selected_times = list(times[scanline[qc_mask]])
        if not selected_times:
            return pd.DataFrame(), days, [], {"region_pixels": int(region.sum()), "qc_valid_pixels": 0, "grid_cells": 0}
        frame = pd.DataFrame(
            {
                "lat": latitude[qc_mask],
                "lon": longitude[qc_mask],
                "time": selected_times,
                value_name: value[qc_mask],
            }
        )
        return frame, days, selected_times, {"region_pixels": int(region.sum()), "qc_valid_pixels": int(qc_mask.sum()), "grid_cells": 0}


def _array(group: Any, name: str, *alternate_names: str) -> np.ndarray:
    selected_name = next(
        (candidate for candidate in (name, *alternate_names) if candidate in group.variables),
        None,
    )
    if selected_name is None:
        raise KeyError(name)
    value = group.variables[selected_name][:]
    if np.ma.isMaskedArray(value):
        value = value.astype(float).filled(np.nan)
    return np.asarray(value).squeeze()


def _region_mask(latitude: np.ndarray, longitude: np.ndarray, configuration: Mapping[str, Any]) -> np.ndarray:
    bounds = configuration["region"]["bounds"]
    return (
        np.isfinite(latitude) & np.isfinite(longitude)
        & (latitude >= float(bounds["latitude"][0]))
        & (latitude < float(bounds["latitude"][1]))
        & (longitude >= float(bounds["longitude"][0]))
        & (longitude < float(bounds["longitude"][1]))
    )


def _lat_centers(configuration: Mapping[str, Any]) -> np.ndarray:
    bounds = configuration["region"]["bounds"]["latitude"]
    resolution = float(configuration["input_data"]["datasets"]["TROPOMI"]["regridding"]["latlon_resolution"])
    return bounds[0] + (np.arange(int(np.ceil((bounds[1] - bounds[0]) / resolution))) + 0.5) * resolution


def _lon_centers(configuration: Mapping[str, Any]) -> np.ndarray:
    bounds = configuration["region"]["bounds"]["longitude"]
    resolution = float(configuration["input_data"]["datasets"]["TROPOMI"]["regridding"]["latlon_resolution"])
    return bounds[0] + (np.arange(int(np.ceil((bounds[1] - bounds[0]) / resolution))) + 0.5) * resolution


def _empty_dataset(configuration: Mapping[str, Any]) -> xr.Dataset:
    lat, lon = _lat_centers(configuration), _lon_centers(configuration)
    return xr.Dataset(
        {
            variable: (("time", "lat", "lon"), np.empty((0, len(lat), len(lon))))
            for variable, _ in VARIABLES.values()
        },
        coords={"time": [], "lat": lat, "lon": lon},
    )


__all__ = ["TropomiPreprocessor"]
