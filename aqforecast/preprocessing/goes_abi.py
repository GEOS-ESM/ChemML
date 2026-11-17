"""Quality control, geolocation, regridding, and hourly GOES ABI AOD."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import xarray as xr
from netCDF4 import Dataset

from aqforecast.contracts import DatasetBundle
from aqforecast.utils.regridding import regrid_irregular_to_grid


VARIABLE = "aod550"


class GoesAbiAodPreprocessor:
    """Apply GOES AOD QC and return hourly, 0.02-degree gridded data."""

    source_key = "GOES-ABI"

    def preprocess(
        self, dataset: DatasetBundle, configuration: Mapping[str, Any]
    ) -> DatasetBundle:
        source = configuration.get("input_data", {}).get("datasets", {}).get(
            self.source_key, {}
        )
        quality = source.get("quality_control", {})
        files_by_satellite = dataset.metadata.get("files_by_satellite", {})
        if not files_by_satellite:
            files_by_satellite = {"unknown": [str(path) for path in dataset.data]}
        satellite_order = dataset.metadata.get(
            "satellite_order", list(files_by_satellite)
        )
        requested_start = _timestamp(dataset.metadata.get("requested_start_time"))
        requested_end = _timestamp(dataset.metadata.get("requested_end_time"))
        frames: list[pd.DataFrame] = []
        statistics: list[dict[str, Any]] = []
        for satellite in satellite_order:
            for file_name in files_by_satellite.get(satellite, []):
                frame, stats = _read_and_filter(
                    Path(file_name), quality, configuration, satellite
                )
                if requested_start is not None:
                    frame = frame[frame["time"] >= requested_start]
                if requested_end is not None:
                    frame = frame[frame["time"] < requested_end]
                statistics.append(stats)
                if not frame.empty:
                    frames.append(frame)

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
        combined["hour"] = combined["time"].dt.floor("h")
        # Prefer the configured satellite order for each hour. This permits a
        # later satellite to supply an hour when an earlier one has no valid
        # retrievals after QC.
        rank = {name: index for index, name in enumerate(satellite_order)}
        chosen = (
            combined.assign(__rank=combined["satellite"].map(rank).fillna(999))
            .sort_values(["hour", "__rank"])
            .groupby("hour", as_index=False, sort=True)
            .first()
        )
        # ``first`` above selects one row, not one satellite. Re-select all
        # observations belonging to the chosen satellite for each hour.
        selected = combined.merge(
            chosen[["hour", "satellite"]], on=["hour", "satellite"], how="inner"
        )
        selected["time"] = (
            selected["hour"] + pd.Timedelta(minutes=30)
        ).dt.tz_localize(None)
        gridded = regrid_irregular_to_grid(
            selected[["lat", "lon", "time", VARIABLE]],
            configuration,
            source_key=self.source_key,
        )
        grouped = gridded.groupby(["time", "lat", "lon"], as_index=False)[VARIABLE].mean()
        data = grouped.set_index(["time", "lat", "lon"])[VARIABLE].to_xarray()
        data = data.reindex(
            time=pd.DatetimeIndex(sorted(selected["time"].unique())).tz_localize(None),
            lat=_lat_centers(configuration),
            lon=_lon_centers(configuration),
        )
        result = xr.Dataset({VARIABLE: data})
        return DatasetBundle(
            self.source_key,
            result,
            {
                **dataset.metadata,
                "preprocessed": True,
                "timestamps_utc": True,
                "quality_control": quality,
                "statistics": statistics,
                "hourly_aggregation": "mean after quality control and spatial regridding",
                "timestamp_convention": "UTC center of hour",
                "satellite_fallback": "configured satellite order per UTC hour",
            },
            list(dataset.errors),
        )


def _read_and_filter(
    path: Path,
    quality: Mapping[str, Any],
    configuration: Mapping[str, Any],
    satellite: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    with Dataset(path) as root:
        aod = _array(root.variables["AOD"])
        dqf = _array(root.variables["DQF"])
        x = np.asarray(root.variables["x"][:], dtype=float)
        y = np.asarray(root.variables["y"][:], dtype=float)
        projection = root.variables["goes_imager_projection"]
        latitude, longitude = _fixed_grid_latlon(x, y, projection)
        timestamp = pd.to_datetime(
            root.getncattr("time_coverage_start"), utc=True, format="mixed"
        )
        region = _region_mask(latitude, longitude, configuration)
        dqf_max = int(quality.get("dqf_max", 1))
        aod_min = float(quality.get("aod_min", 0.0))
        aod_max = float(quality.get("aod_max", 5.0))
        mask = (
            region
            & np.isfinite(aod)
            & (dqf <= dqf_max)
            & np.isfinite(dqf)
            & (aod >= aod_min)
            & (aod <= aod_max)
        )
        stats = {
            "file": path.name,
            "satellite": satellite,
            "time": timestamp.isoformat(),
            "region_pixels": int(region.sum()),
            "qc_valid_pixels": int(mask.sum()),
        }
        if not mask.any():
            return pd.DataFrame(columns=["lat", "lon", "time", VARIABLE, "satellite"]), stats
        return pd.DataFrame(
            {
                "lat": latitude[mask],
                "lon": longitude[mask],
                "time": timestamp,
                VARIABLE: aod[mask],
                "satellite": satellite,
            }
        ), stats


def _array(variable: Any) -> np.ndarray:
    values = variable[:]
    if np.ma.isMaskedArray(values):
        values = values.astype(float).filled(np.nan)
    return np.asarray(values, dtype=float).squeeze()


def _fixed_grid_latlon(
    x: np.ndarray, y: np.ndarray, projection: Any
) -> tuple[np.ndarray, np.ndarray]:
    attrs = getattr(projection, "attrs", None) or getattr(projection, "__dict__", {})
    height = float(attrs["perspective_point_height"]) + float(attrs["semi_major_axis"])
    equatorial = float(attrs["semi_major_axis"])
    polar = float(attrs["semi_minor_axis"])
    origin = float(attrs["longitude_of_projection_origin"])
    X, Y = np.meshgrid(x, y)
    coefficient_a = np.sin(X) ** 2 + np.cos(X) ** 2 * (
        np.cos(Y) ** 2 + (equatorial**2 / polar**2) * np.sin(Y) ** 2
    )
    coefficient_b = -2 * height * np.cos(X) * np.cos(Y)
    coefficient_c = height**2 - equatorial**2
    discriminant = coefficient_b**2 - 4 * coefficient_a * coefficient_c
    with np.errstate(invalid="ignore", divide="ignore"):
        radius = np.where(
            discriminant >= 0,
            (-coefficient_b - np.sqrt(np.maximum(discriminant, 0)))
            / (2 * coefficient_a),
            np.nan,
        )
        s_x = radius * np.cos(X) * np.cos(Y)
        s_y = -radius * np.sin(X)
        s_z = radius * np.cos(X) * np.sin(Y)
        latitude = np.degrees(
            np.arctan(
                (equatorial**2 / polar**2)
                * s_z
                / np.sqrt((height - s_x) ** 2 + s_y**2)
            )
        )
        longitude = origin - np.degrees(np.arctan2(s_y, height - s_x))
    return latitude, longitude


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


def _timestamp(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _lat_centers(configuration: Mapping[str, Any]) -> np.ndarray:
    bounds = configuration["region"]["bounds"]["latitude"]
    resolution = float(configuration["input_data"]["datasets"]["GOES-ABI"]["regridding"]["latlon_resolution"])
    return bounds[0] + (np.arange(int(np.ceil((bounds[1] - bounds[0]) / resolution))) + 0.5) * resolution


def _lon_centers(configuration: Mapping[str, Any]) -> np.ndarray:
    bounds = configuration["region"]["bounds"]["longitude"]
    resolution = float(configuration["input_data"]["datasets"]["GOES-ABI"]["regridding"]["latlon_resolution"])
    return bounds[0] + (np.arange(int(np.ceil((bounds[1] - bounds[0]) / resolution))) + 0.5) * resolution


def _empty_dataset(configuration: Mapping[str, Any]) -> xr.Dataset:
    lat, lon = _lat_centers(configuration), _lon_centers(configuration)
    return xr.Dataset(
        {VARIABLE: (("time", "lat", "lon"), np.empty((0, len(lat), len(lon))))},
        coords={"time": [], "lat": lat, "lon": lon},
    )


__all__ = ["GoesAbiAodPreprocessor", "VARIABLE"]
