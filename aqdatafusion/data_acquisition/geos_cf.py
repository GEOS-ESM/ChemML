"""GEOS-CF analysis and forecast acquisition.

The public GEOS-CF service is an unauthenticated DAP2 service.  This module
keeps its access deliberately separate from the authenticated Earthdata DAP4
client used by satellite products.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from pathlib import Path
from typing import Any, Mapping, Sequence
import logging
import time

import numpy as np
import pandas as pd
import requests
import xarray as xr

from aqdatafusion.contracts import DataRequest, DatasetBundle
from aqdatafusion.data_acquisition.base import AcquisitionError
from aqdatafusion.data_acquisition.generic import RemoteDataSource


SOURCE_KEY = "GEOS-CF"
DEFAULT_BASE_URL = "https://opendap.nccs.nasa.gov/dods/gmao/geos-cf/v2"
DEFAULT_COLLECTIONS = {
    "aqc": ("co", "no2", "o3", "pm10_rh35", "pm25_rh35", "so2"),
    "chm": (
        "pm25bc_rh35", "pm25du_rh35", "pm25nh4_rh35", "pm25nit_rh35",
        "pm25oc_rh35", "pm25soa_rh35", "pm25ss_rh35", "pm25su_rh35",
    ),
    "met": (
        "q", "cldtt", "phis", "ps", "rh", "slp", "t", "tprec",
        "troppb", "ts", "u", "v", "zl", "zpbl",
    ),
    "xgc": (
        "aod550_bc", "aod550_dust", "aod550_oc", "aod550_psc",
        "aod550_sla", "aod550_sna", "aod550_ss", "pblcol_no2",
        "pblcol_o3", "totcol_no2", "totcol_o3", "tropcol_no2",
        "tropcol_o3",
    ),
}
COLLECTION_NAMES = tuple(DEFAULT_COLLECTIONS)


class GeosCfDataSource(RemoteDataSource):
    """Acquire regional GEOS-CF analysis and forecast subsets."""

    source_key = SOURCE_KEY

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("aqdatafusion.geos_cf")
        self._forecast_catalog_cache: dict[str, set[str] | None] = {}
        super().__init__(self.source_key, self._acquire)

    def _acquire(
        self, request: DataRequest, configuration: Mapping[str, Any]
    ) -> DatasetBundle:
        source = _source_configuration(configuration)
        access = source.get("access", {})
        mode = str(access.get("mode", "remote")).casefold()
        bounds = _bounding_box(configuration)
        collections = _requested_collections(source)
        start = _as_utc(request.start_time)
        end = _as_utc(request.end_time)
        if start is None or end is None:
            raise AcquisitionError("GEOS-CF acquisition requires start and end times", kind="configuration")

        records: list[xr.Dataset] = []
        warnings: list[dict[str, Any]] = []
        if mode == "local":
            records.extend(self._local_records(start, end, bounds, collections, source, access, warnings))
        elif mode in {"remote", "opendap"}:
            records.extend(self._analysis_records(start, end, bounds, collections, source, access, warnings))
            records.extend(self._forecast_records(start, end, bounds, collections, source, access, warnings))
        else:
            raise AcquisitionError(
                f"unsupported GEOS-CF access mode: {mode}", kind="configuration"
            )

        if warnings:
            for warning in warnings:
                self.logger.warning("GEOS-CF acquisition warning: %s", warning["message"])
        if not records and mode != "local":
            raise AcquisitionError(
                "No GEOS-CF analysis or forecast records were available",
                kind="availability", retryable=True, details=warnings,
            )
        metadata = {
            "access_mode": mode,
            "collections": list(collections),
            "bounding_box": bounds,
            "request_start_time": start.isoformat(),
            "request_end_time": end.isoformat(),
            "forecast_cycle_hour_utc": int(access.get("forecast_cycle_hour_utc", 9)),
            "warnings": warnings,
            "records": len(records),
        }
        return DatasetBundle(self.source_key, records, metadata, [])

    def _analysis_records(
        self, start: pd.Timestamp, end: pd.Timestamp, bounds: tuple[float, float, float, float],
        collections: Mapping[str, Sequence[str]], source: Mapping[str, Any],
        access: Mapping[str, Any], warnings: list[dict[str, Any]],
    ) -> list[xr.Dataset]:
        datasets = self._open_stream(
            "ana", None, start, end, bounds, collections, source, access, warnings
        )
        return [datasets] if datasets is not None else []

    def _forecast_records(
        self, start: pd.Timestamp, end: pd.Timestamp, bounds: tuple[float, float, float, float],
        collections: Mapping[str, Sequence[str]], source: Mapping[str, Any],
        access: Mapping[str, Any], warnings: list[dict[str, Any]],
    ) -> list[xr.Dataset]:
        lookback = int(access.get("forecast_lookback_days", 6))
        first = (start - pd.Timedelta(days=lookback)).normalize()
        last = end.normalize()
        records: list[xr.Dataset] = []
        for day in pd.date_range(first, last, freq="1D"):
            initialization = day + pd.Timedelta(hours=int(access.get("forecast_cycle_hour_utc", 9)))
            available = {
                collection: self._forecast_initializations(collection, access)
                for collection in collections
            }
            dataset = self._open_stream(
                "fcst", initialization, start, end, bounds, collections,
                source, access, warnings, available,
            )
            if dataset is not None:
                records.append(dataset)
        return records

    def _open_stream(
        self, stream: str, initialization: pd.Timestamp | None,
        start: pd.Timestamp, end: pd.Timestamp,
        bounds: tuple[float, float, float, float], collections: Mapping[str, Sequence[str]],
        source: Mapping[str, Any], access: Mapping[str, Any],
        warnings: list[dict[str, Any]], available: Mapping[str, set[str] | None] | None = None,
    ) -> xr.Dataset | None:
        opened: list[xr.Dataset] = []
        for collection, variables in collections.items():
            if not variables:
                self.logger.info("Skipping GEOS-CF %s collection: no variables configured", collection)
                continue
            name = f"{collection}_tavg_1hr_glo_L1440x721_slv"
            if stream == "fcst" and available is not None:
                initialization_key = initialization.strftime("%Y%m%d") if initialization is not None else ""
                dates = available.get(collection)
                if dates is not None and initialization_key not in dates:
                    warnings.append({
                        "kind": "availability",
                        "stream": stream,
                        "collection": collection,
                        "initialization_time": initialization.isoformat() if initialization is not None else None,
                        "message": f"GEOS-CF {stream}/{collection} initialization {initialization_key} is not retained by the public service",
                    })
                    continue
            url = _remote_url(access, stream, name, initialization)
            dataset = None
            error: Exception | None = None
            retries = max(1, int(access.get("request_retries", 3)))
            for attempt in range(retries):
                try:
                    dataset = _open_chunked_subset(
                        url, variables, bounds, start, end, access
                    )
                    error = None
                    break
                except Exception as caught:
                    error = caught
                    if attempt + 1 < retries:
                        self.logger.warning(
                            "Retrying GEOS-CF %s/%s request (%d/%d): %s",
                            stream, collection, attempt + 2, retries, caught,
                        )
                        time.sleep(float(access.get("retry_pause_seconds", 1.0)))
            if error is not None or dataset is None:
                warning = {
                    "kind": "availability",
                    "stream": stream,
                    "collection": collection,
                    "initialization_time": initialization.isoformat() if initialization is not None else None,
                    "url": url,
                    "message": f"GEOS-CF {stream}/{collection} is unavailable: {error}",
                }
                warnings.append(warning)
                if stream == "ana":
                    self.logger.warning("%s", warning["message"])
                continue
            dataset.attrs.update({
                "geos_cf_stream": stream,
                "forecast_initialization_time": initialization.isoformat() if initialization is not None else "",
                "source_url": url,
            })
            opened.append(dataset)
        if not opened:
            return None
        return xr.merge(opened, compat="override", join="outer")

    def _forecast_initializations(
        self, collection: str, access: Mapping[str, Any]
    ) -> set[str] | None:
        """Return catalogued forecast dates, or None when discovery fails."""

        if collection in self._forecast_catalog_cache:
            return self._forecast_catalog_cache[collection]
        name = f"{collection}_tavg_1hr_glo_L1440x721_slv"
        url = f"{str(access.get('base_url', DEFAULT_BASE_URL)).rstrip('/')}/fcst/{name}"
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            dates = set(re.findall(rf"{re.escape(name)}\.(\d{{8}})_\d{{2}}z\.info", response.text))
        except (OSError, requests.RequestException) as error:
            self.logger.warning("Could not discover GEOS-CF %s forecast availability: %s", collection, error)
            dates = None
        self._forecast_catalog_cache[collection] = dates
        return dates

    def _local_records(
        self, start: pd.Timestamp, end: pd.Timestamp, bounds: tuple[float, float, float, float],
        collections: Mapping[str, Sequence[str]], source: Mapping[str, Any],
        access: Mapping[str, Any], warnings: list[dict[str, Any]],
    ) -> list[xr.Dataset]:
        root_value = access.get("local_root")
        if not root_value:
            raise AcquisitionError("GEOS-CF local mode requires access.local_root", kind="configuration")
        root = Path(str(root_value)).expanduser()
        records: list[xr.Dataset] = []
        # Local operational files are organized by day.  Glob rather than
        # inventing a cycle-specific filename so both .nc4 and .nc4.cmprs
        # layouts can be used on NCCS.
        for day in pd.date_range(start.normalize(), end.normalize(), freq="1D"):
            for stream in ("ana", "fcst"):
                opened: list[xr.Dataset] = []
                for collection, variables in collections.items():
                    pattern = f"{stream}*/Y{day.year:04d}/M{day.month:02d}/D{day.day:02d}/*{collection}_tavg_1hr_glo_L1440x721_slv*"
                    paths = sorted(root.glob(pattern))
                    if not paths:
                        warnings.append({
                            "kind": "availability", "stream": stream, "collection": collection,
                            "message": f"No local GEOS-CF files found for {stream}/{collection} on {day.date()}",
                        })
                        continue
                    for path in paths:
                        try:
                            opened.append(_open_local_subset(path, variables, bounds, start, end))
                        except (OSError, ValueError, RuntimeError) as error:
                            warnings.append({"kind": "availability", "stream": stream, "collection": collection, "path": str(path), "message": str(error)})
                if opened:
                    merged = xr.merge(opened, compat="override", join="outer")
                    merged.attrs["geos_cf_stream"] = stream
                    records.append(merged)
        return records


def _open_subset(
    url: str, variables: Sequence[str], bounds: tuple[float, float, float, float],
    start: pd.Timestamp, end: pd.Timestamp,
) -> xr.Dataset:
    with xr.open_dataset(url, engine="pydap", decode_times=False) as opened:
        dataset = _select_requested_variables(
            opened, variables,
            "none of the requested variables are exposed by the collection",
        )
        indexers = _coordinate_indexers(dataset, bounds)
        raw_times = np.asarray(dataset["time"].values)
        decoded = _decode_geos_cf_time(raw_times, dataset["time"].attrs)
        start_naive = start.tz_localize(None)
        end_naive = end.tz_localize(None)
        mask = (decoded >= start_naive.to_datetime64()) & (decoded < end_naive.to_datetime64())
        if not mask.any():
            raise ValueError("collection has no records in the requested interval")
        indices = np.flatnonzero(mask)
        dataset = dataset.isel(time=slice(int(indices[0]), int(indices[-1]) + 1), **indexers)
        dataset = dataset.assign_coords(time=("time", decoded[indices]))
        return dataset.load()


def _open_chunked_subset(
    url: str,
    variables: Sequence[str],
    bounds: tuple[float, float, float, float],
    start: pd.Timestamp,
    end: pd.Timestamp,
    access: Mapping[str, Any],
) -> xr.Dataset:
    """Load a collection in bounded time and variable requests.

    The public GrADS DAP service can become unreliable when a request asks for
    many variables and a long time interval at once.  Each chunk is loaded
    eagerly before the next request, then chunks are concatenated locally.
    """

    chunk_hours = max(1, int(access.get("request_chunk_hours", 24)))
    variable_chunk_size = max(1, int(access.get("request_variable_chunk_size", 1)))
    variable_groups = [
        tuple(variables[index:index + variable_chunk_size])
        for index in range(0, len(variables), variable_chunk_size)
    ]
    grouped_chunks: list[list[xr.Dataset]] = [[] for _ in variable_groups]
    last_error: Exception | None = None
    retries = max(1, int(access.get("request_retries", 3)))
    retry_pause = float(access.get("retry_pause_seconds", 1.0))
    for chunk_start, chunk_end in _time_chunks(start, end, chunk_hours):
        for group_index, variable_group in enumerate(variable_groups):
            chunk = None
            error: Exception | None = None
            for attempt in range(retries):
                try:
                    chunk = _open_subset(
                        url, variable_group, bounds, chunk_start, chunk_end
                    )
                    error = None
                    break
                except Exception as caught:
                    error = caught
                    # A forecast endpoint may have no values in the first or
                    # last request window even though the endpoint is valid.
                    if isinstance(caught, ValueError) and "no records in the requested interval" in str(caught):
                        break
                    if attempt + 1 < retries:
                        time.sleep(retry_pause)
            if error is not None:
                if isinstance(error, ValueError) and "no records in the requested interval" in str(error):
                    continue
                last_error = error
                raise error
            if chunk is None:
                continue
            grouped_chunks[group_index].append(chunk)
    datasets: list[xr.Dataset] = []
    for chunks in grouped_chunks:
        if chunks:
            datasets.append(xr.concat(chunks, dim="time").sortby("time"))
    if not datasets:
        if last_error is not None:
            raise last_error
        raise ValueError("collection has no records in the requested interval")
    return xr.merge(datasets, compat="override", join="outer")


def _time_chunks(
    start: pd.Timestamp, end: pd.Timestamp, chunk_hours: int
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    chunks: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    current = start
    step = pd.Timedelta(hours=chunk_hours)
    while current < end:
        following = min(current + step, end)
        chunks.append((current, following))
        current = following
    return chunks


def _open_local_subset(
    path: Path, variables: Sequence[str], bounds: tuple[float, float, float, float],
    start: pd.Timestamp, end: pd.Timestamp,
) -> xr.Dataset:
    with xr.open_dataset(path, decode_times=False) as opened:
        dataset = _select_requested_variables(
            opened, variables,
            f"none of the requested variables are present in {path}",
        )
        indexers = _coordinate_indexers(dataset, bounds)
        raw_times = np.asarray(dataset["time"].values)
        decoded = _decode_geos_cf_time(raw_times, dataset["time"].attrs)
        start_naive = start.tz_localize(None)
        end_naive = end.tz_localize(None)
        mask = (decoded >= start_naive.to_datetime64()) & (decoded < end_naive.to_datetime64())
        if not mask.any():
            raise ValueError(f"{path} has no records in the requested interval")
        indices = np.flatnonzero(mask)
        dataset = dataset.isel(time=slice(int(indices[0]), int(indices[-1]) + 1), **indexers)
        return dataset.assign_coords(time=("time", decoded[indices])).load()


def _select_requested_variables(
    dataset: xr.Dataset, variables: Sequence[str], missing_message: str
) -> xr.Dataset:
    """Select configured variables, accepting case differences in source names.

    The public OpenDAP collections expose lower-case names, while local NCCS
    files can contain upper-case characters.  Keep the configured names in
    the returned dataset so downstream preprocessing sees one stable schema.
    Exact matches take precedence if a source happens to expose names that
    differ only by case.
    """

    data_variables = list(dataset.data_vars)
    by_casefold: dict[str, list[str]] = {}
    for name in data_variables:
        by_casefold.setdefault(str(name).casefold(), []).append(str(name))

    selected: list[str] = []
    rename: dict[str, str] = {}
    for requested in variables:
        requested_name = str(requested)
        if requested_name in dataset.data_vars:
            actual = requested_name
        else:
            matches = by_casefold.get(requested_name.casefold(), [])
            actual = matches[0] if len(matches) == 1 else None
        if actual is None:
            continue
        selected.append(actual)
        if actual != requested_name:
            rename[actual] = requested_name

    if not selected:
        raise ValueError(missing_message)
    result = dataset[selected]
    return result.rename(rename) if rename else result


def _coordinate_indexers(dataset: xr.Dataset, bounds: tuple[float, float, float, float]) -> dict[str, slice]:
    west, south, east, north = bounds
    latitude = np.asarray(dataset["lat"].load().values)
    longitude = np.asarray(dataset["lon"].load().values)
    lat = np.flatnonzero((latitude >= south) & (latitude <= north))
    lon = np.flatnonzero((longitude >= west) & (longitude <= east))
    if not len(lat) or not len(lon):
        raise ValueError("GEOS-CF region does not intersect the native grid")
    return {"lat": slice(int(lat[0]), int(lat[-1]) + 1), "lon": slice(int(lon[0]), int(lon[-1]) + 1)}


def _decode_geos_cf_time(values: np.ndarray, attrs: Mapping[str, Any]) -> np.ndarray:
    units = str(attrs.get("units", "days since 1-1-1 00:00:0.0")).lower()
    if not units.startswith("days since 1-1-1"):
        raise ValueError(f"unsupported GEOS-CF time units: {units}")
    values = np.asarray(values, dtype=float)
    minimum = str(attrs.get("minimum", ""))
    match = re.fullmatch(r"(\d{2}:\d{2})z(\d{2}[A-Za-z]{3}\d{4})", minimum)
    if match:
        # GrADS supplies the human-readable origin and its numeric coordinate
        # is occasionally not aligned with Python's year-1 Gregorian epoch.
        # Anchor to the advertised minimum and use only numeric differences.
        origin = datetime.strptime(
            f"{match.group(1)} {match.group(2)}", "%H:%M %d%b%Y"
        ).replace(tzinfo=timezone.utc)
        first = float(values[0])
        decoded = [origin + timedelta(seconds=round((float(value) - first) * 86400)) for value in values]
    else:
        decoded = [datetime(1, 1, 1, tzinfo=timezone.utc) + timedelta(days=float(value)) for value in values]
    return np.asarray(
        [pd.Timestamp(value).tz_localize(None).to_datetime64() for value in decoded],
        dtype="datetime64[ns]",
    )


def _remote_url(access: Mapping[str, Any], stream: str, collection: str, initialization: pd.Timestamp | None) -> str:
    base = str(access.get("base_url", DEFAULT_BASE_URL)).rstrip("/")
    if stream == "ana":
        return f"{base}/ana/{collection}"
    endpoint = str(access.get("forecast_endpoint", "dated")).casefold()
    if endpoint == "latest":
        return f"{base}/fcst/{collection}.latest"
    if initialization is None:
        raise ValueError("forecast initialization is required for dated endpoint")
    date = initialization.strftime("%Y%m%d_%Hz")
    return f"{base}/fcst/{collection}/{collection}.{date}"


def _source_configuration(configuration: Mapping[str, Any]) -> Mapping[str, Any]:
    return configuration.get("input_data", {}).get("datasets", {}).get(SOURCE_KEY, {})


def _requested_collections(source: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    configured = source.get("access", {}).get("collections", {})
    result: dict[str, tuple[str, ...]] = {}
    for collection in COLLECTION_NAMES:
        values = configured.get(collection, DEFAULT_COLLECTIONS[collection])
        result[collection] = tuple(str(value) for value in values)
    return result


def _bounding_box(configuration: Mapping[str, Any]) -> tuple[float, float, float, float]:
    bounds = configuration.get("region", {}).get("bounds", {})
    latitude = bounds.get("latitude", [])
    longitude = bounds.get("longitude", [])
    if len(latitude) != 2 or len(longitude) != 2:
        raise AcquisitionError("GEOS-CF acquisition requires two-number region bounds", kind="configuration")
    return float(longitude[0]), float(latitude[0]), float(longitude[1]), float(latitude[1])


def _as_utc(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


__all__ = ["GeosCfDataSource", "DEFAULT_BASE_URL", "DEFAULT_COLLECTIONS"]
