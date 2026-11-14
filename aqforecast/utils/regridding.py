"""Generic irregular-observation to latitude/longitude-grid regridding."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence, Union

import numpy as np
import pandas as pd
import xarray as xr


def regrid_irregular_to_grid(
    data: Union[pd.DataFrame, xr.Dataset],
    configuration: Mapping[str, Any],
    *,
    source_key: Optional[str] = None,
    categorical_variables: Optional[Iterable[str]] = None,
    preserve_dimensions: Optional[Sequence[str]] = None,
) -> Union[pd.DataFrame, xr.Dataset]:
    """Bin irregular observations onto a configured dataset-specific grid.

    Numeric variables use an unweighted mean and categorical/quality
    variables use their first deterministic mode. Non-spatial dimensions
    (for example time, layer, altitude, and forecast_time) are retained.
    Empty target cells remain NaN. The current design uses unweighted bins;
    a future weighting strategy can be added without changing this contract.
    """
    settings = _regridding_settings(configuration, data, source_key)
    latitude_name, longitude_name = _coordinate_names(settings)
    resolution = _resolution(settings)
    lat_centers, lon_centers = _grid_centers(_bounds(configuration), resolution)
    categorical = set(categorical_variables or settings.get("categorical_variables", []))
    preserved = list(preserve_dimensions or settings.get("preserve_dimensions", []))
    if isinstance(data, pd.DataFrame):
        return _regrid_dataframe(data, latitude_name, longitude_name, lat_centers,
                                 lon_centers, resolution, categorical, preserved, settings)
    if isinstance(data, xr.Dataset):
        return _regrid_xarray(data, latitude_name, longitude_name, lat_centers,
                              lon_centers, resolution, categorical, preserved)
    raise TypeError("regridding requires a pandas DataFrame or xarray Dataset")


def _regridding_settings(configuration, data, source_key):
    if source_key:
        selected = source_key
    elif isinstance(data, xr.Dataset):
        selected = data.attrs.get("source_key")
    else:
        selected = configuration.get("regridding_source_key")
    if not selected:
        raise ValueError("regridding requires source_key, Dataset.attrs['source_key'], or configuration['regridding_source_key']")
    settings = configuration.get("input_data", {}).get("datasets", {}).get(selected, {})
    if not isinstance(settings, Mapping):
        raise ValueError(f"no input-data configuration exists for {selected!r}")
    regridding = settings.get("regridding", {})
    if not isinstance(regridding, Mapping):
        raise ValueError(f"regridding configuration for {selected!r} must be a mapping")
    return {**settings, **regridding}


def _coordinate_names(settings):
    names = settings.get("coordinate_names", {})
    names = names if isinstance(names, Mapping) else {}
    return str(names.get("latitude", "lat")), str(names.get("longitude", "lon"))


def _resolution(settings):
    try:
        value = float(settings.get("latlon_resolution"))
    except (TypeError, ValueError) as error:
        raise ValueError("regridding.latlon_resolution must be a positive number") from error
    if not np.isfinite(value) or value <= 0:
        raise ValueError("regridding.latlon_resolution must be a positive number")
    return value


def _bounds(configuration):
    region = configuration.get("region", {})
    bounds = region.get("bounds", {}) if isinstance(region, Mapping) else {}
    latitude = bounds.get("latitude") if isinstance(bounds, Mapping) else None
    longitude = bounds.get("longitude") if isinstance(bounds, Mapping) else None
    if (not isinstance(latitude, (list, tuple)) or not isinstance(longitude, (list, tuple))
            or len(latitude) != 2 or len(longitude) != 2):
        raise ValueError("regridding requires two-number region latitude and longitude bounds")
    lat_min, lat_max = map(float, latitude)
    lon_min, lon_max = map(float, longitude)
    if lat_max <= lat_min or lon_max <= lon_min:
        raise ValueError("regridding region bounds must be increasing")
    return lat_min, lat_max, lon_min, lon_max


def _grid_centers(bounds, resolution):
    lat_min, lat_max, lon_min, lon_max = bounds
    return (lat_min + (np.arange(int(np.ceil((lat_max - lat_min) / resolution))) + 0.5) * resolution,
            lon_min + (np.arange(int(np.ceil((lon_max - lon_min) / resolution))) + 0.5) * resolution)


def _edges(centers, resolution):
    return np.concatenate(([centers[0] - resolution / 2], centers + resolution / 2))


def _mode(values):
    valid = values.dropna()
    if valid.empty:
        return np.nan
    modes = valid.mode()
    return modes.iloc[0] if not modes.empty else valid.iloc[0]


def _aggregation(values, categorical):
    return _mode(values) if categorical or not pd.api.types.is_numeric_dtype(values) else values.mean()


def _regrid_dataframe(data, latitude_name, longitude_name, lat_centers, lon_centers,
                      resolution, categorical, preserved, settings):
    missing = {latitude_name, longitude_name}.difference(data.columns)
    if missing:
        raise ValueError(f"regridding input is missing coordinate columns: {', '.join(sorted(missing))}")
    frame = data.copy()
    frame["__lat_index"] = pd.cut(pd.to_numeric(frame[latitude_name], errors="coerce"),
                                   _edges(lat_centers, resolution), labels=False, include_lowest=True)
    frame["__lon_index"] = pd.cut(pd.to_numeric(frame[longitude_name], errors="coerce"),
                                   _edges(lon_centers, resolution), labels=False, include_lowest=True)
    frame = frame.dropna(subset=["__lat_index", "__lon_index"])
    names = settings.get("coordinate_names", {})
    time_name = names.get("time", "time") if isinstance(names, Mapping) else "time"
    group_columns = [n for n in [time_name, *preserved] if n in frame.columns]
    group_columns += ["__lat_index", "__lon_index"]
    configured = settings.get("variables", [])
    excluded = {latitude_name, longitude_name, *group_columns}
    value_columns = [str(n) for n in configured if str(n) in frame.columns and str(n) not in excluded]
    if not value_columns:
        value_columns = [str(n) for n in frame.select_dtypes(include=["number"]).columns if str(n) not in excluded]
    grouped = frame.groupby(group_columns, dropna=False, observed=True)
    aggregated = grouped[value_columns].agg({n: (lambda values, n=n: _aggregation(values, n in categorical)) for n in value_columns})
    dimensions = group_columns[:-2]
    full_index = pd.MultiIndex.from_product(
        [*[frame[n].drop_duplicates().tolist() for n in dimensions],
          range(len(lat_centers)), range(len(lon_centers))],
        names=[*dimensions, "__lat_index", "__lon_index"],
    )
    result = aggregated.reindex(full_index).reset_index()
    result[latitude_name] = result.pop("__lat_index").map(lambda i: lat_centers[int(i)])
    result[longitude_name] = result.pop("__lon_index").map(lambda i: lon_centers[int(i)])
    return result[[*group_columns[:-2], latitude_name, longitude_name, *value_columns]]


def _regrid_xarray(data, latitude_name, longitude_name, lat_centers, lon_centers,
                   resolution, categorical, preserved):
    if latitude_name not in data or longitude_name not in data:
        raise ValueError("regridding input is missing latitude or longitude coordinates")
    spatial_dims = set(data[latitude_name].dims) | set(data[longitude_name].dims)
    preserve_names = [n for n in data.dims if n not in spatial_dims]
    time_name = data.attrs.get("time_name", "time")
    for name in [time_name, *preserved]:
        if name in data.coords or name in data.dims:
            preserve_names.append(name)
    preserve_names = list(dict.fromkeys(preserve_names))
    frame = data.to_dataframe().reset_index()
    frame["__lat_index"] = pd.cut(frame[latitude_name], _edges(lat_centers, resolution), labels=False, include_lowest=True)
    frame["__lon_index"] = pd.cut(frame[longitude_name], _edges(lon_centers, resolution), labels=False, include_lowest=True)
    frame = frame.dropna(subset=["__lat_index", "__lon_index"])
    group_columns = [n for n in preserve_names if n in frame.columns] + ["__lat_index", "__lon_index"]
    dimensions = group_columns[:-2]
    dimension_values = [frame[n].drop_duplicates().tolist() for n in dimensions]
    full_index = pd.MultiIndex.from_product([*dimension_values, range(len(lat_centers)), range(len(lon_centers))],
                                            names=[*dimensions, "__lat_index", "__lon_index"])
    output = {}
    for name in data.data_vars:
        if name not in frame.columns:
            continue
        values = frame.groupby(group_columns, dropna=False, observed=True)[name].agg(
            lambda series, n=name: _aggregation(series, n in categorical)).reindex(full_index)
        array = values.to_xarray().rename({"__lat_index": latitude_name, "__lon_index": longitude_name})
        output[name] = array.assign_coords({latitude_name: lat_centers, longitude_name: lon_centers})
    result = xr.Dataset(output)
    result.attrs = {**data.attrs, "regridded": True, "regridding_method": "bin_mean_or_mode",
                    "regridding_resolution_degrees": resolution,
                    "regridding_categorical_variables": sorted(categorical)}
    return result


__all__ = ["regrid_irregular_to_grid"]
