"""Reusable Cartopy-backed plots for ChemML data products.

The plotting helpers are deliberately tolerant of missing Natural Earth files:
maps remain useful with the data layer and gridlines when the optional base
layers cannot be downloaded (for example, on an offline compute node).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np
import pandas as pd


_BASE_LAYERS = (
    ("110m", "physical", "coastline"),
    ("110m", "cultural", "admin_0_boundary_lines_land"),
    ("110m", "physical", "lakes"),
    ("110m", "cultural", "admin_1_states_provinces_lines"),
)

# Cartopy/Natural Earth provides regional road layers rather than one global
# roads layer. This North American layer supports the repository's ATL example
# and remains optional for regions where it is not applicable.
_ROAD_LAYERS = (("10m", "cultural", "roads_north_america"),)


def _set_cartopy_cache(cache_directory: Path) -> None:
    """Point Cartopy at the configured cache directory."""

    import cartopy

    cache_directory.mkdir(parents=True, exist_ok=True)
    cartopy.config["data_dir"] = str(cache_directory)


def _natural_earth_path(
    cache_directory: Path, resolution: str, category: str, name: str
) -> Path:
    return (
        cache_directory
        / "shapefiles"
        / "natural_earth"
        / resolution
        / category
        / f"ne_{resolution}_{name}.shp"
    )


def prepare_cartopy_basemap(
    cache_directory: str | Path,
    *,
    download: bool = True,
    include_roads: bool = True,
    output_fn: Optional[Any] = None,
) -> dict[str, Any]:
    """Ensure standard Natural Earth layers are available in a local cache.

    Downloads are attempted by default and failures are returned as warnings
    rather than raised. This makes first-time setup safe on offline systems.
    """

    cache = Path(cache_directory).expanduser()
    result: dict[str, Any] = {"cache_directory": str(cache), "downloaded": [], "warnings": []}
    try:
        from cartopy.io import shapereader
    except ImportError as error:
        result["warnings"].append(f"Cartopy is unavailable: {error}")
        return result

    _set_cartopy_cache(cache)
    layers = _BASE_LAYERS + (_ROAD_LAYERS if include_roads else ())
    for resolution, category, name in layers:
        target = _natural_earth_path(cache, resolution, category, name)
        if target.exists():
            continue
        if not download:
            result["warnings"].append(f"Natural Earth layer is not cached: {name}")
            continue
        try:
            path = Path(
                shapereader.natural_earth(
                    resolution=resolution, category=category, name=name
                )
            )
            if path.exists():
                result["downloaded"].append(name)
        except Exception as error:  # Cartopy reports several downloader errors.
            result["warnings"].append(f"Could not cache Natural Earth layer {name}: {error}")
            if output_fn is not None:
                output_fn(result["warnings"][-1])
    return result


def _first_data_array(data: Any, variable: Optional[str]) -> Any:
    if hasattr(data, "data_vars"):
        if variable is None:
            names = list(data.data_vars)
            if len(names) != 1:
                raise ValueError("variable is required when a Dataset has multiple variables")
            variable = names[0]
        return data[variable]
    return data


def _as_utc_timestamp(value: Any) -> pd.Timestamp:
    """Return a timezone-aware UTC timestamp for comparisons."""

    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _select_frame_timestamp(frame: pd.DataFrame, timestamp: Any) -> pd.DataFrame:
    """Select all rows at the observation time nearest to ``timestamp``."""

    if timestamp is None or "time" not in frame.columns or frame.empty:
        return frame
    times = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    valid = times.notna()
    if not valid.any():
        return frame.iloc[0:0]
    target = _as_utc_timestamp(timestamp)
    differences = (times[valid] - target).abs()
    nearest_time = times[valid].loc[differences.idxmin()]
    return frame.loc[valid & (times == nearest_time)]


def _select_for_plot(
    data: Any,
    timestamp: Any,
    time_mean: bool,
    dimension_selection: Optional[Mapping[str, Any]] = None,
) -> Any:
    if timestamp is not None and "time" in data.dims:
        target = _as_utc_timestamp(timestamp)
        available = pd.to_datetime(data["time"].values, utc=True)
        if len(available) == 0:
            raise ValueError("cannot select a timestamp from an empty time coordinate")
        nearest_index = int(np.abs(available - target).argmin())
        data = data.isel(time=nearest_index)
    elif time_mean and "time" in data.dims:
        data = data.mean(dim="time", skipna=True)

    # A source can contain useful auxiliary dimensions in addition to its map
    # dimensions. GEOS-CF, for example, stores forecast lead day. A map must
    # be two-dimensional, so select an explicit label when supplied and use
    # the first value otherwise (analysis/lead day zero for GEOS-CF).
    dimension_selection = dimension_selection or {}
    for dimension in [name for name in data.dims if name not in {"lat", "lon"}]:
        if dimension in dimension_selection:
            selection = dimension_selection[dimension]
            if isinstance(selection, (int, np.integer)):
                data = data.isel({dimension: int(selection)})
            else:
                data = data.sel({dimension: selection})
        else:
            data = data.isel({dimension: 0})
    return data.squeeze(drop=True)


def _region_extent(configuration: Optional[Mapping[str, Any]]) -> Optional[tuple[float, float, float, float]]:
    if not configuration:
        return None
    bounds = configuration.get("region", {}).get("bounds", {})
    try:
        lat_min, lat_max = bounds["latitude"]
        lon_min, lon_max = bounds["longitude"]
    except (KeyError, TypeError, ValueError):
        return None
    return float(lon_min), float(lon_max), float(lat_min), float(lat_max)


def plot_data_map(
    data: Any = None,
    *,
    variable: Optional[str] = None,
    points: Any = None,
    point_variable: Optional[str] = None,
    configuration: Optional[Mapping[str, Any]] = None,
    cache_directory: Optional[str | Path] = None,
    extent: Optional[Sequence[float]] = None,
    timestamp: Any = None,
    time_mean: bool = True,
    cmap: str = "viridis",
    colorbar_label: Optional[str] = None,
    title: Optional[str] = None,
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    point_size: float = 24.0,
    add_basemap: bool = True,
    download_basemap: bool = True,
    dimension_selection: Optional[Mapping[str, Any]] = None,
    ax: Any = None,
) -> tuple[Any, Any]:
    """Plot gridded or point data on a regional map.

    ``data`` may be an xarray Dataset/DataArray or a pandas DataFrame. Point
    data are also accepted through ``points`` to overlay monitors on a grid.
    Coordinates are expected to be named ``lat`` and ``lon``. The return value
    is ``(figure, axes)`` for further annotation or saving by callers. Base
    layers are enabled by default and are loaded from, or downloaded into, the
    configured Cartopy cache; set ``download_basemap=False`` for offline-only
    plotting.
    """

    import matplotlib.pyplot as plt

    cache = cache_directory
    if cache is None and configuration:
        cache = configuration.get("filepaths", {}).get("data_sources", {}).get(
            "cartopy_cache"
        )
    has_cartopy = False
    ccrs = None
    cfeature = None
    if add_basemap:
        try:
            import cartopy.crs as ccrs_module
            import cartopy.feature as cfeature_module

            ccrs, cfeature = ccrs_module, cfeature_module
            has_cartopy = True
            if cache is None:
                import cartopy

                cache = cartopy.config["data_dir"]
            prepare_cartopy_basemap(cache, download=download_basemap)
            _set_cartopy_cache(Path(cache).expanduser())
        except ImportError:
            has_cartopy = False

    if ax is None:
        if has_cartopy:
            figure, ax = plt.subplots(subplot_kw={"projection": ccrs.PlateCarree()}, figsize=(9, 6))
        else:
            figure, ax = plt.subplots(figsize=(9, 6))
    else:
        figure = ax.figure

    map_extent = tuple(extent) if extent is not None else _region_extent(configuration)
    if has_cartopy and map_extent is not None:
        ax.set_extent(map_extent, crs=ccrs.PlateCarree())
    if has_cartopy:
        gridlines = ax.gridlines(draw_labels=True, linewidth=0.5, alpha=0.5, linestyle="--")
        gridlines.top_labels = False
        gridlines.right_labels = False
        if cache is not None:
            cache_path = Path(cache).expanduser()
            features = (
                (cfeature.COASTLINE, "coastline", "110m", "physical"),
                (cfeature.BORDERS, "admin_0_boundary_lines_land", "110m", "cultural"),
                (cfeature.LAKES, "lakes", "110m", "physical"),
                (cfeature.STATES, "admin_1_states_provinces_lines", "110m", "cultural"),
            )
            if _natural_earth_path(cache_path, "10m", "cultural", "roads_north_america").exists():
                features += (
                    (
                        cfeature.NaturalEarthFeature(
                            "cultural",
                            "roads_north_america",
                            "10m",
                            facecolor="none",
                        ),
                        "roads_north_america",
                        "10m",
                        "cultural",
                    ),
                )
            for feature, name, resolution, category in features:
                if _natural_earth_path(cache_path, resolution, category, name).exists():
                    ax.add_feature(feature, facecolor="none", edgecolor="0.35", linewidth=0.6)

    plotted = False
    if data is not None and hasattr(data, "dims"):
        data_array = _select_for_plot(
            _first_data_array(data, variable), timestamp, time_mean, dimension_selection
        )
        transform = {"transform": ccrs.PlateCarree()} if has_cartopy else {}
        plot_kwargs = {
            "ax": ax,
            "cmap": cmap,
            "vmin": vmin,
            "vmax": vmax,
            "cbar_kwargs": {"label": colorbar_label} if colorbar_label else None,
            **transform,
        }
        if {"lat", "lon"}.issubset(data_array.dims):
            data_array.plot.pcolormesh(**plot_kwargs)
        elif data_array.ndim == 1:
            # This is useful for diagnostic one-dimensional data, although
            # source maps normally contain both latitude and longitude.
            plot_kwargs.pop("cbar_kwargs", None)
            plot_kwargs.pop("cmap", None)
            plot_kwargs.pop("vmin", None)
            plot_kwargs.pop("vmax", None)
            data_array.plot.line(**plot_kwargs)
        else:
            raise ValueError(
                "map data must contain both lat and lon dimensions after "
                "time and auxiliary-dimension selection"
            )
        plotted = True
    elif data is not None and isinstance(data, pd.DataFrame):
        frame = data.copy()
        if timestamp is not None and "time" in frame:
            frame = _select_frame_timestamp(frame, timestamp)
        if time_mean and {"lat", "lon"}.issubset(frame.columns):
            value_name = variable or point_variable
            if value_name:
                frame = frame.groupby(["lat", "lon"], as_index=False)[value_name].mean()
        value_name = variable or point_variable
        if value_name and value_name in frame:
            scatter = ax.scatter(frame["lon"], frame["lat"], c=frame[value_name], s=point_size,
                                 cmap=cmap, vmin=vmin, vmax=vmax,
                                 transform=ccrs.PlateCarree() if has_cartopy else None,
                                 edgecolors="black", linewidths=0.25)
            figure.colorbar(scatter, ax=ax, label=colorbar_label)
            plotted = True

    if points is not None:
        point_frame = points
        if isinstance(point_frame, pd.DataFrame):
            point_frame = point_frame.copy()
            if timestamp is not None and "time" in point_frame:
                point_frame = _select_frame_timestamp(point_frame, timestamp)
            value_name = point_variable or variable
            if time_mean and value_name and value_name in point_frame:
                point_frame = point_frame.groupby(["lat", "lon"], as_index=False)[value_name].mean()
            if value_name and value_name in point_frame:
                values = point_frame[value_name]
            else:
                values = "black"
            ax.scatter(point_frame["lon"], point_frame["lat"], c=values, s=point_size,
                       cmap=cmap if not isinstance(values, str) else None,
                       transform=ccrs.PlateCarree() if has_cartopy else None,
                       edgecolors="black", linewidths=0.5)
            plotted = True

    if not plotted:
        raise ValueError("No plottable data were supplied")
    ax.set_title(title or "")
    return figure, ax


__all__ = ["plot_data_map", "prepare_cartopy_basemap"]
