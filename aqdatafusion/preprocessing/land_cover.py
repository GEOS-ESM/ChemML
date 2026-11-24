"""Quality control, geolocation, and categorical regridding for MCD12Q1."""

from __future__ import annotations

from pathlib import Path
import re
import json
from typing import Any, Mapping

import numpy as np
import pandas as pd
import xarray as xr
from netCDF4 import Dataset

from aqdatafusion.contracts import DatasetBundle
from aqdatafusion.utils.regridding import regrid_irregular_to_grid


VARIABLE = "LC_Type1"
_RADIUS_PATTERN = re.compile(r"ProjParams=\(([-+0-9.eE]+)")
_UPPER_LEFT_PATTERN = re.compile(
    r"UpperLeftPointMtrs=\(([-+0-9.eE]+),([-+0-9.eE]+)\)"
)


class LandCoverPreprocessor:
    """Convert native sinusoidal MCD12Q1 tiles to the configured lat/lon grid."""

    source_key = "land_cover"

    def preprocess(
        self, dataset: DatasetBundle, configuration: Mapping[str, Any]
    ) -> DatasetBundle:
        source = configuration.get("input_data", {}).get("datasets", {}).get(
            self.source_key, {}
        )
        quality = source.get("quality_control", {})
        files_by_year = dataset.metadata.get("files_by_requested_year", {})
        source_years = dataset.metadata.get("source_year_by_requested_year", {})
        if not files_by_year:
            files_by_year = {
                str(_file_year(Path(path))): [str(path)] for path in dataset.data
            }
        frames: list[pd.DataFrame] = []
        statistics: list[dict[str, Any]] = []
        for requested_year, paths in files_by_year.items():
            for path in dict.fromkeys(paths):
                frame, stats = _read_tile(Path(path), quality, configuration)
                stats["requested_year"] = int(requested_year)
                statistics.append(stats)
                if frame.empty:
                    continue
                source_year = int(source_years.get(str(requested_year), requested_year))
                frame["time"] = pd.Timestamp(year=source_year, month=1, day=1)
                frames.append(frame)

        if not frames:
            result = _empty_dataset(configuration)
        else:
            gridded = regrid_irregular_to_grid(
                pd.concat(frames, ignore_index=True),
                configuration,
                source_key=self.source_key,
                categorical_variables=[VARIABLE],
            )
            result = gridded.set_index(["time", "lat", "lon"])[VARIABLE].to_xarray().to_dataset()
            result[VARIABLE] = result[VARIABLE].astype("float32")
            result = result.sortby("time")
        result.attrs.update(
            {
                "source": "MODIS/Terra+Aqua MCD12Q1 Collection 6.1",
                "preprocessing": "native sinusoidal geolocation and categorical mode regridding",
                "quality_control": "LC_Type1 finite and non-fill; LW/QC bounds are configurable and disabled by default",
                "grid": "0.005 degree latitude-longitude grid",
                "timestamps": "January 1 UTC timestamp representing the source data year",
            }
        )
        metadata = {
            **dataset.metadata,
            "preprocessed": True,
            "timestamps_utc": True,
            "quality_control": quality,
            "statistics": statistics,
            "regridding": "categorical mode from native 500 m sinusoidal pixels to 0.005 degree latitude-longitude cells",
        }
        if source_years:
            result.attrs["source_year_by_requested_year"] = json.dumps(source_years, sort_keys=True)
        return DatasetBundle(self.source_key, result, metadata, list(dataset.errors))


def _read_tile(
    path: Path, quality: Mapping[str, Any], configuration: Mapping[str, Any]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    with Dataset(path) as root:
        values = np.ma.asarray(root.variables[VARIABLE][:])
        lw = np.ma.asarray(root.variables["LW"][:])
        qc = np.ma.asarray(root.variables["QC"][:])
        lat, lon = _sinusoidal_coordinates(root, values.shape)
    values = np.asarray(np.ma.filled(values, np.nan), dtype=float)
    lw_values = np.asarray(np.ma.filled(lw, np.nan), dtype=float)
    qc_values = np.asarray(np.ma.filled(qc, np.nan), dtype=float)
    bounds = configuration["region"]["bounds"]
    region = (
        (lat >= float(bounds["latitude"][0]))
        & (lat < float(bounds["latitude"][1]))
        & (lon >= float(bounds["longitude"][0]))
        & (lon < float(bounds["longitude"][1]))
    )
    valid = region & np.isfinite(values) & ~np.isin(values, quality.get("land_cover_invalid_values", [255]))
    if quality.get("apply_lw_filter", False):
        valid &= _between(lw_values, quality.get("lw_min", 0), quality.get("lw_max", 255))
    if quality.get("apply_qc_filter", False):
        valid &= _between(qc_values, quality.get("qc_min", 0), quality.get("qc_max", 255))
    rows, columns = np.where(valid)
    frame = pd.DataFrame(
        {
            "lat": lat[rows, columns],
            "lon": lon[rows, columns],
            VARIABLE: values[rows, columns],
        }
    )
    return frame, {
        "file": path.name,
        "region_pixels": int(region.sum()),
        "qc_valid_pixels": int(valid.sum()),
        "lw_min_observed": float(np.nanmin(lw_values[region])) if region.any() else None,
        "lw_max_observed": float(np.nanmax(lw_values[region])) if region.any() else None,
        "qc_min_observed": float(np.nanmin(qc_values[region])) if region.any() else None,
        "qc_max_observed": float(np.nanmax(qc_values[region])) if region.any() else None,
    }


def _sinusoidal_coordinates(root: Any, shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    metadata = str(root.getncattr("StructMetadata.0"))
    radius_match = _RADIUS_PATTERN.search(metadata)
    upper_left_match = _UPPER_LEFT_PATTERN.search(metadata)
    if not radius_match or not upper_left_match:
        raise ValueError("MCD12Q1 granule is missing sinusoidal projection metadata")
    radius = float(radius_match.group(1))
    upper_left_x, upper_left_y = map(float, upper_left_match.groups())
    height, width = shape
    pixel_width = 1111950.519667 / width
    pixel_height = 1111950.519667 / height
    x = upper_left_x + (np.arange(width) + 0.5) * pixel_width
    y = upper_left_y - (np.arange(height) + 0.5) * pixel_height
    yy, xx = np.meshgrid(y, x, indexing="ij")
    latitude = np.degrees(yy / radius)
    longitude = np.degrees(xx / (radius * np.cos(yy / radius)))
    return latitude, longitude


def _between(values: np.ndarray, lower: Any, upper: Any) -> np.ndarray:
    return np.isfinite(values) & (values >= float(lower)) & (values <= float(upper))


def _file_year(path: Path) -> int:
    match = re.search(r"\.A(\d{4})\d{3}", path.name)
    if not match:
        raise ValueError(f"cannot determine MCD12Q1 year from {path.name}")
    return int(match.group(1))


def _empty_dataset(configuration: Mapping[str, Any]) -> xr.Dataset:
    bounds = configuration["region"]["bounds"]
    resolution = float(configuration["input_data"]["datasets"]["land_cover"]["regridding"]["latlon_resolution"])
    lat = bounds["latitude"][0] + (np.arange(int(np.ceil((bounds["latitude"][1] - bounds["latitude"][0]) / resolution))) + 0.5) * resolution
    lon = bounds["longitude"][0] + (np.arange(int(np.ceil((bounds["longitude"][1] - bounds["longitude"][0]) / resolution))) + 0.5) * resolution
    return xr.Dataset({VARIABLE: (("time", "lat", "lon"), np.empty((0, len(lat), len(lon)), dtype="float32"))}, coords={"time": [], "lat": lat, "lon": lon})


__all__ = ["LandCoverPreprocessor", "VARIABLE"]
