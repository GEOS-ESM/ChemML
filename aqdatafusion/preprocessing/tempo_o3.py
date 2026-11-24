"""Quality control and hourly aggregation for TEMPO O₃ profile layer 24."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import xarray as xr

from aqdatafusion.contracts import DatasetBundle


class TempoO3ProfilePreprocessor:
    source_key = "TEMPO_O3"

    def preprocess(self, dataset: DatasetBundle, configuration: Mapping[str, Any]) -> DatasetBundle:
        source = configuration.get("input_data", {}).get("datasets", {}).get(self.source_key, {})
        quality = source.get("quality_control", {})
        profile_layers = _profile_layers(source)
        science_variables = [f"ozone_profile_layer_{layer}" for layer in profile_layers]
        frames: list[xr.Dataset] = []
        statistics: list[dict[str, int]] = []
        for path in dataset.data:
            with xr.open_dataset(Path(path)) as cached:
                current = cached.load()
            required = science_variables + ["eff_cloud_fraction", "solar_zenith_angle", "viewing_zenith_angle"]
            if any(name not in current for name in required):
                continue
            values = {
                name: current[name].astype("float64").squeeze(drop=True)
                for name in science_variables
            }
            cloud = current["eff_cloud_fraction"].astype("float64").squeeze(drop=True)
            solar = current["solar_zenith_angle"].astype("float64").squeeze(drop=True)
            viewing = current["viewing_zenith_angle"].astype("float64").squeeze(drop=True)
            valid = (
                np.isfinite(cloud) & np.isfinite(solar) & np.isfinite(viewing)
                & (cloud <= float(quality.get("cloud_fraction_max", 0.5)))
                & (solar <= float(quality.get("solar_zenith_angle_max", 80.0)))
                & (viewing <= float(quality.get("viewing_zenith_angle_max", 80.0)))
            )
            cleaned_variables = []
            for name, value in values.items():
                layer_valid = valid & np.isfinite(value) & (np.abs(value) < 1.0e10)
                cleaned = value.where(layer_valid).expand_dims(time=[_timestamp(current)])
                cleaned = cleaned.rename({"latitude": "lat", "longitude": "lon"})
                cleaned_variables.append(cleaned.to_dataset(name=name))
            frames.append(xr.merge(cleaned_variables))
            statistics.append({"input_pixels": int(next(iter(values.values())).size), "qc_valid_pixels": int(valid.sum())})
        if not frames:
            result = _empty_dataset(configuration)
        else:
            combined = xr.concat(frames, dim="time").sortby("time")
            valid_count = combined[science_variables[0]].count(dim=("lat", "lon"))
            result = combined.groupby("time").mean(dim="time", skipna=True)
            result["valid_pixel_count"] = valid_count.groupby("time").sum(dim="time")
            start = _request_timestamp(dataset.metadata.get("request_start_time"))
            end = _request_timestamp(dataset.metadata.get("request_end_time"))
            if start is not None:
                result = result.sel(time=result.time >= start)
            if end is not None:
                result = result.sel(time=result.time < end)
        result.attrs.update({
            "source": "TEMPO_O3PROF_L3 V04",
            "preprocessing": "OpenDAP spatial subsets, layer-24 selection, quality control, hourly averaging",
            "profile_layers": profile_layers,
            "quality_control": "finite values, fill-value removal, eff_cloud_fraction <= 0.5, solar and viewing zenith angles <= 80 degrees",
            "grid": "native approximately 0.04 degree latitude-longitude grid; no regridding",
            "timestamps": "UTC, aligned to the center of the hour",
        })
        return DatasetBundle(self.source_key, result, {
            **dataset.metadata, "preprocessed": True, "timestamps_utc": True,
            "quality_control": quality, "statistics": statistics,
            "hourly_aggregation": "mean after quality control; duplicate granules in an hour averaged",
        }, list(dataset.errors))


def _timestamp(dataset: xr.Dataset) -> pd.Timestamp:
    timestamp = pd.Timestamp(dataset.attrs["time_coverage_start"])
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
    resolution = float(configuration["input_data"]["datasets"]["TEMPO_O3"]["regridding"].get("latlon_resolution", 0.04))
    lat = bounds["latitude"][0] + (np.arange(int(np.ceil((bounds["latitude"][1] - bounds["latitude"][0]) / resolution))) + 0.5) * resolution
    lon = bounds["longitude"][0] + (np.arange(int(np.ceil((bounds["longitude"][1] - bounds["longitude"][0]) / resolution))) + 0.5) * resolution
    variables = {
        f"ozone_profile_layer_{layer}": (("time", "lat", "lon"), np.empty((0, len(lat), len(lon))))
        for layer in _profile_layers(configuration["input_data"]["datasets"]["TEMPO_O3"])
    }
    return xr.Dataset(variables, coords={"time": [], "lat": lat, "lon": lon})


def _profile_layers(source: Mapping[str, Any]) -> tuple[int, ...]:
    values = source.get("profile_layers", [24])
    layers = tuple(dict.fromkeys(int(value) for value in values))
    if not layers:
        raise ValueError("TEMPO O₃ profile_layers cannot be empty")
    return layers


__all__ = ["TempoO3ProfilePreprocessor"]
