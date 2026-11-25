"""Generic incremental database update orchestration for input datasets."""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from aqdatafusion.contracts import DataRequest, DatasetBundle
from aqdatafusion.data_acquisition.base import UnavailableDataSource
from aqdatafusion.data_acquisition.base import AcquisitionError
from aqdatafusion.data_management.catalog import DatasetCatalog
from aqdatafusion.data_management.integrity import (
    configured_file_matches,
    verify_database_integrity,
)
from aqdatafusion.data_management.registry import SourceRegistry, default_source_registry
from aqdatafusion.preprocessing.generic import GenericPreprocessor
from aqdatafusion.data_management.validation import validate_site_coordinates
from aqdatafusion.utils.logging import get_logger


@dataclass
class DatabaseUpdateReport:
    """Structured result of one database update run."""

    start_time: str
    end_time: str
    sources: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "sources": self.sources,
            "warnings": self.warnings,
        }


def _utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _utc_nanoseconds(values: pd.DatetimeIndex) -> Any:
    """Return timestamps as UTC nanosecond integers.

    CSV readers and pandas operations can produce either timezone-naive or
    timezone-aware indexes. Naive archive timestamps are defined as UTC by
    ChemML's data contract.
    """

    index = pd.DatetimeIndex(values)
    if index.tz is None:
        index = index.tz_localize("UTC")
    else:
        index = index.tz_convert("UTC")
    return index.tz_localize(None).astype("datetime64[ns]").asi8


class DatabaseManager:
    """Maintain partitioned CSV/NetCDF databases for configured sources.

    ``data_sources`` and ``preprocessors`` are registries keyed by source. A
    source adapter is responsible for remote APIs or source-specific local
    files; this class owns completeness, merging, partitioning, and catalogs.
    """

    def __init__(
        self,
        configuration: Mapping[str, Any],
        *,
        data_sources: Optional[Mapping[str, Any]] = None,
        preprocessors: Optional[Mapping[str, Any]] = None,
        logger: Optional[logging.Logger] = None,
        source_registry: Optional[SourceRegistry] = None,
    ) -> None:
        self.configuration = configuration
        self.data_sources = dict(data_sources or {})
        self.preprocessors = dict(preprocessors or {})
        self.logger = logger or get_logger(configuration=configuration)
        registry = source_registry or default_source_registry(self.configuration)
        configured_datasets = self.configuration.get("input_data", {}).get("datasets", {})
        for source_key, registration in registry.items():
            if source_key not in configured_datasets and source_key != "ground_monitors":
                continue
            if not registration.enabled_if(self.configuration):
                continue
            if source_key not in self.data_sources:
                self.data_sources[source_key] = registration.create_data_source(
                    self.logger
                )
            if source_key not in self.preprocessors:
                self.preprocessors[source_key] = registration.create_preprocessor()

    def _expected_times(
        self, source: Mapping[str, Any], start: pd.Timestamp, end: pd.Timestamp
    ) -> pd.DatetimeIndex:
        time_config = source.get("time", {})
        availability = time_config.get("availability", {})
        if availability.get("mode") == "yearly":
            last_year = (end - pd.Timedelta(nanoseconds=1)).year
            return pd.DatetimeIndex(
                [
                    pd.Timestamp(year=year, month=1, day=1, tz="UTC")
                    for year in range(start.year, last_year + 1)
                ]
            )
        frequency = time_config.get("frequency", "1h")
        mode = (
            availability.get("mode", "continuous")
            if isinstance(availability, Mapping)
            else "continuous"
        )
        convention = time_config.get("timestamp_convention", "reference")
        offset = (
            pd.Timedelta("30m")
            if convention == "center" and frequency == "1h"
            else pd.Timedelta(0)
        )
        if mode != "daily_window":
            return pd.date_range(start, end, freq=frequency, inclusive="left") + offset
        timezone_name = availability.get("timezone") or self.configuration.get(
            "region", {}
        ).get("timezone", "UTC")
        local_start = start.tz_convert(timezone_name).normalize()
        local_end = end.tz_convert(timezone_name).normalize()
        start_text, end_text = availability.get("start", "08:00"), availability.get(
            "end", "17:00"
        )
        values: list[pd.Timestamp] = []
        for day in pd.date_range(local_start, local_end, freq="1D", inclusive="left"):
            begin = pd.Timestamp(f"{day.date()} {start_text}", tz=timezone_name)
            finish = pd.Timestamp(f"{day.date()} {end_text}", tz=timezone_name)
            values.extend(
                pd.date_range(
                    begin, finish, freq=frequency, inclusive="left"
                ).tz_convert("UTC")
                + offset
            )
        # Local-calendar windows can begin on the preceding UTC date (for
        # example, 07:00 US/Eastern is 11:00 UTC). A request must never
        # declare timestamps outside its explicit half-open UTC interval as
        # missing, so trim the generated windows after converting them to UTC.
        generated = pd.DatetimeIndex(values)
        return generated[(generated >= start) & (generated < end)]

    def _source_directory(self, source_key: str) -> Path:
        return Path(
            self.configuration["filepaths"]["data_sources"][source_key]
        ).expanduser()

    def _source_with_context(
        self, source_key: str, source: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        region = self.configuration.get("region", {})
        return {
            **source,
            "region_code": region.get("region_code", "region"),
            "provider": region.get("ground_monitoring", {}).get(
                "provider", "provider"
            ),
        }

    def verify_database_integrity(
        self,
        source_key: str,
        *,
        expected_times: Optional[pd.DatetimeIndex] = None,
    ) -> Dict[str, Any]:
        """Verify one configured source database and return structured findings."""

        configured = self.configuration.get("input_data", {}).get("datasets", {})
        if source_key not in configured:
            raise KeyError(f"no input-data configuration exists for {source_key}")
        source = configured[source_key]
        return verify_database_integrity(
            source_key,
            self._source_directory(source_key),
            self._source_with_context(source_key, source),
            expected_times=expected_times,
        )

    def _read_database(self, source_key: str, source: Mapping[str, Any]) -> Any:
        directory = self._source_directory(source_key)
        storage = source.get("storage", {})
        file_format = storage.get("format", "netcdf")
        files = (
            sorted(directory.rglob("*.csv" if file_format == "csv" else "*.nc"))
            if directory.exists()
            else []
        )
        files = [path for path in files if ".tmp" not in path.parts]
        files = [
            path
            for path in files
            if configured_file_matches(
                path, self._source_with_context(source_key, source)
            )
        ]
        if not files:
            return pd.DataFrame() if file_format == "csv" else None
        if file_format == "csv":
            frames = []
            site_id_name = self._site_id_name(source)
            dtype = {site_id_name: "string"} if site_id_name else None
            for path in files:
                try:
                    frame = pd.read_csv(path, dtype=dtype)
                except pd.errors.EmptyDataError as error:
                    raise ValueError(
                        f"input CSV file {path} is empty; provide a header-only "
                        "file or remove it before retrying"
                    ) from error
                frames.append(frame)
            combined = pd.concat(frames, ignore_index=True)
            return self._normalize_site_ids(combined, source)
        import xarray as xr

        return xr.open_mfdataset(files, combine="by_coords")

    def read_database(self, source_key: str) -> Any:
        """Read the current on-disk database for one configured source.

        Point-monitor databases are returned as a :class:`pandas.DataFrame`;
        gridded databases are returned as an lazily opened
        :class:`xarray.Dataset`.  An empty DataFrame or ``None`` is returned
        when no database files exist yet.  Callers are responsible for closing
        an xarray Dataset when it is no longer needed.
        """

        configured = self.configuration.get("input_data", {}).get("datasets", {})
        if source_key not in configured:
            raise KeyError(f"no input-data configuration exists for {source_key}")
        return self._read_database(source_key, configured[source_key])

    def _observed_times(self, data: Any, source: Mapping[str, Any]) -> pd.DatetimeIndex:
        time_name = source.get("coordinate_names", {}).get("time", "time")
        if data is None:
            return pd.DatetimeIndex([])
        if isinstance(data, pd.DataFrame):
            if time_name not in data.columns:
                return pd.DatetimeIndex([])
            return pd.DatetimeIndex(
                pd.to_datetime(data[time_name], utc=True, errors="coerce")
                .dropna()
                .unique()
            )
        return pd.DatetimeIndex(pd.to_datetime(data[time_name].values, utc=True))

    def _site_id_name(self, source: Mapping[str, Any]) -> Optional[str]:
        """Return the configured point-site identifier column, if any."""

        site_id = source.get("site_id")
        return str(site_id) if site_id else None

    def _normalize_site_ids(
        self, data: pd.DataFrame, source: Mapping[str, Any]
    ) -> pd.DataFrame:
        """Use one stable string representation for point-site identities."""

        site_id_name = self._site_id_name(source)
        if site_id_name is None or site_id_name not in data.columns:
            return data
        normalized = data.copy()
        normalized[site_id_name] = normalized[site_id_name].astype("string")
        return normalized

    def _validate_site_coordinates(
        self, data: Any, source: Mapping[str, Any], label: str
    ) -> None:
        """Ensure each site identifier has one stable coordinate pair."""

        validate_site_coordinates(data, source, label)

    def _validate_site_coordinate_match(
        self,
        existing: Any,
        incoming: pd.DataFrame,
        source: Mapping[str, Any],
    ) -> None:
        """Ensure incoming coordinates agree with archived coordinates."""

        site_id_name = self._site_id_name(source)
        if (
            site_id_name is None
            or not isinstance(existing, pd.DataFrame)
            or existing.empty
        ):
            return
        coordinate_names = source.get("coordinate_names", {})
        latitude_name = coordinate_names.get("latitude", "lat")
        longitude_name = coordinate_names.get("longitude", "lon")
        required = [site_id_name, latitude_name, longitude_name]
        if any(
            name not in existing.columns or name not in incoming.columns
            for name in required
        ):
            return
        existing_sites = (
            existing[required]
            .dropna(subset=required)
            .drop_duplicates(site_id_name)
            .set_index(site_id_name)
        )
        incoming_sites = (
            incoming[required]
            .dropna(subset=required)
            .drop_duplicates(site_id_name)
            .set_index(site_id_name)
        )
        common_sites = existing_sites.index.intersection(incoming_sites.index)
        tolerance = float(source.get("site_coordinate_tolerance", 1e-6))
        for site_id in common_sites:
            latitude_delta = abs(
                float(existing_sites.loc[site_id, latitude_name])
                - float(incoming_sites.loc[site_id, latitude_name])
            )
            longitude_delta = abs(
                float(existing_sites.loc[site_id, longitude_name])
                - float(incoming_sites.loc[site_id, longitude_name])
            )
            if latitude_delta > tolerance or longitude_delta > tolerance:
                raise ValueError(
                    f"site {site_id!r} coordinates do not match archived data; "
                    f"maximum allowed difference is {tolerance} degrees"
                )

    def _missing_site_times(
        self,
        expected: pd.DatetimeIndex,
        data: pd.DataFrame,
        source: Mapping[str, Any],
        tolerance: Any,
    ) -> tuple[pd.DatetimeIndex, list[str]]:
        """Find missing timestamps independently for each configured site."""

        site_id_name = self._site_id_name(source)
        time_name = source.get("coordinate_names", {}).get("time", "time")
        if (
            site_id_name is None
            or site_id_name not in data.columns
            or time_name not in data.columns
        ):
            return (
                self._missing_times(
                    expected, self._observed_times(data, source), tolerance, source
                ),
                [],
            )
        if data.empty:
            return self._missing_times(expected, pd.DatetimeIndex([]), tolerance), []

        missing_by_site: list[pd.DatetimeIndex] = []
        missing_site_ids: list[str] = []
        for site_id, site_data in data.groupby(site_id_name, dropna=True):
            observed = pd.DatetimeIndex(
                pd.to_datetime(site_data[time_name], utc=True, errors="coerce")
                .dropna()
                .unique()
            )
            missing = self._missing_times(expected, observed, tolerance, source)
            if len(missing):
                missing_by_site.append(missing)
                missing_site_ids.append(str(site_id))
        if not missing_by_site:
            return pd.DatetimeIndex([]), []
        return (
            pd.DatetimeIndex(
                sorted(set(value for values in missing_by_site for value in values))
            ),
            missing_site_ids,
        )

    def _missing_times(
        self,
        expected: pd.DatetimeIndex,
        observed: pd.DatetimeIndex,
        tolerance: Any,
        source: Optional[Mapping[str, Any]] = None,
    ) -> pd.DatetimeIndex:
        if source and source.get("time", {}).get("availability", {}).get("mode") == "yearly":
            fallback = int(source.get("access", {}).get("max_year_fallback", 0))
            observed_years = {int(_utc(value).year) for value in observed}
            return pd.DatetimeIndex(
                [
                    value
                    for value in expected
                    if not any(
                        0 <= value.year - observed_year <= fallback
                        for observed_year in observed_years
                    )
                ]
            )
        if source and source.get("time", {}).get("aggregation") == "daily_mean":
            observed_dates = {_utc(value).normalize() for value in observed}
            return pd.DatetimeIndex(
                [value for value in expected if _utc(value).normalize() not in observed_dates]
            )
        tolerance = pd.Timedelta(tolerance or "0s")
        # Normalize timestamp resolution before comparing integer values.
        # Recent pandas versions may retain parsed input at microsecond
        # precision while date_range commonly produces nanoseconds.
        observed_values = _utc_nanoseconds(observed)
        expected_values = _utc_nanoseconds(expected)
        missing = [
            value
            for value, integer_value in zip(expected, expected_values)
            if not len(observed_values)
            or not bool((abs(observed_values - integer_value) <= tolerance.value).any())
        ]
        return pd.DatetimeIndex(missing)

    def _filename(
        self, source_key: str, source: Mapping[str, Any], period: pd.Timestamp
    ) -> str:
        template = source.get("file_template", f"{source_key}_{{month_string}}")
        region = self.configuration.get("region", {})
        context = {
            "region_code": region.get("region_code", "region"),
            "provider": region.get("ground_monitoring", {}).get("provider", "provider"),
        }
        partition = source.get("storage", {}).get("partition", "monthly")
        context.update(
            {
                "date_string": period.strftime("%Y%m%d"),
                "month_string": period.strftime("%Y%m"),
                "year_string": period.strftime("%Y"),
            }
        )
        return re.sub(
            r"\{([^{}]+)\}",
            lambda match: str(context.get(match.group(1), match.group(0))),
            template,
        )

    def _partitions(
        self, times: pd.DatetimeIndex, source: Mapping[str, Any]
    ) -> Iterable[pd.Timestamp]:
        partition = source.get("storage", {}).get("partition", "monthly")
        if partition == "daily":
            return times.normalize().unique()
        if partition == "yearly":
            return pd.DatetimeIndex(
                [
                    pd.Timestamp(year=int(year), month=1, day=1, tz="UTC")
                    for year in sorted(set(times.year))
                ]
            )
        return times.tz_convert(None).to_period("M").to_timestamp().tz_localize("UTC").unique()

    def _merge(
        self, existing: Any, incoming: Any, source: Mapping[str, Any], policy: str
    ) -> Any:
        time_name = source.get("coordinate_names", {}).get("time", "time")
        if incoming is None:
            return existing
        if isinstance(incoming, DatasetBundle):
            incoming = incoming.data
        if isinstance(incoming, pd.DataFrame):
            incoming = self._normalize_site_ids(incoming, source)
            if incoming.empty:
                return existing if existing is not None else incoming
            if isinstance(existing, pd.DataFrame):
                existing = self._normalize_site_ids(existing, source)
            self._validate_site_coordinates(existing, source, "existing data")
            self._validate_site_coordinates(incoming, source, "incoming data")
            self._validate_site_coordinate_match(existing, incoming, source)
            incoming[time_name] = pd.to_datetime(incoming[time_name], utc=True)
            site_id_name = self._site_id_name(source)
            if existing is None or (
                isinstance(existing, pd.DataFrame) and existing.empty
            ):
                identity = (
                    [site_id_name, time_name]
                    if site_id_name
                    else [time_name, "lat", "lon"]
                )
                return incoming.drop_duplicates(
                    subset=identity, keep="last"
                ).reset_index(drop=True)
            existing = existing.copy()
            existing[time_name] = pd.to_datetime(existing[time_name], utc=True)
            combined = pd.concat([existing, incoming], ignore_index=True)
            if site_id_name:
                identity = [site_id_name, time_name]
            else:
                identity = [time_name] + [
                    column for column in ("lat", "lon") if column in combined
                ]
            combined = combined.drop_duplicates(
                subset=identity,
                keep="first" if policy == "preserve_existing" else "last",
            )
            return combined.sort_values(time_name).reset_index(drop=True)
        import xarray as xr

        if existing is None:
            return incoming
        if not isinstance(existing, xr.Dataset):
            return incoming
        if policy == "replace_all":
            return incoming
        if source.get("time", {}).get("aggregation") == "daily_mean":
            return self._merge_daily_xarray(existing, incoming, time_name, policy)
        combined = xr.concat([existing, incoming], dim=time_name).sortby(time_name)
        unique_times = (
            pd.DatetimeIndex(pd.to_datetime(combined[time_name].values, utc=True))
            .unique()
            .sort_values()
        )
        combined_times = pd.DatetimeIndex(
            pd.to_datetime(combined[time_name].values, utc=True)
        )
        records = []
        for timestamp in unique_times:
            # ``combined`` can contain the same timestamp in both the
            # archived and incoming datasets. Label-based selection is
            # ambiguous until those duplicate records are resolved, so use
            # positional indices here.
            indices = [
                index
                for index, value in enumerate(combined_times)
                if value == timestamp
            ]
            candidates = combined.isel({time_name: indices})
            if policy == "replace_partition":
                record = candidates.isel({time_name: -1})
            else:
                record = candidates.isel({time_name: 0})
                for index in range(1, candidates.sizes.get(time_name, 1)):
                    record = record.combine_first(candidates.isel({time_name: index}))
            records.append(
                record.expand_dims({time_name: [timestamp.tz_localize(None)]})
            )
        return xr.concat(records, dim=time_name).sortby(time_name)

    def _merge_daily_xarray(
        self, existing: Any, incoming: Any, time_name: str, policy: str
    ) -> Any:
        """Merge daily datasets by calendar date, not exact overpass time."""

        import xarray as xr

        combined = xr.concat([existing, incoming], dim=time_name).sortby(time_name)
        timestamps = pd.DatetimeIndex(
            pd.to_datetime(combined[time_name].values, utc=True)
        )
        dates = timestamps.normalize()
        records = []
        output_times = []
        for day in dates.unique().sort_values():
            indices = [index for index, value in enumerate(dates) if value == day]
            if policy == "replace_partition":
                selected = combined.isel({time_name: indices[-1]}, drop=True)
                timestamp = timestamps[indices[-1]].tz_localize(None)
            else:
                selected = combined.isel({time_name: indices[0]}, drop=True)
                timestamp = timestamps[indices[0]].tz_localize(None)
                for index in indices[1:]:
                    selected = selected.combine_first(
                        combined.isel({time_name: index}, drop=True)
                    )
            records.append(selected.expand_dims({time_name: [timestamp]}))
            output_times.append(timestamp)
        return xr.concat(records, dim=time_name).assign_coords(
            {time_name: output_times}
        ).sortby(time_name)

    def _write(
        self, source_key: str, source: Mapping[str, Any], data: Any, run_dir: Path
    ) -> list[str]:
        directory = self._source_directory(source_key)
        directory.mkdir(parents=True, exist_ok=True)
        time_name = source.get("coordinate_names", {}).get("time", "time")
        times = self._observed_times(data, source)
        written: list[str] = []
        for period in self._partitions(times, source):
            if isinstance(data, pd.DataFrame):
                timestamps = pd.to_datetime(data[time_name], utc=True)
                partition = source.get("storage", {}).get("partition", "monthly")
                if partition == "daily":
                    mask = timestamps.dt.normalize() == period.normalize()
                elif partition == "yearly":
                    mask = timestamps.dt.year == period.year
                else:
                    mask = timestamps.dt.tz_localize(None).dt.to_period("M") == period.tz_localize(None).to_period("M")
                subset = data[mask]
                target = directory / self._filename(source_key, source, period)
                staged = run_dir / target.name
                subset.to_csv(staged, index=False)
            else:
                partition = source.get("storage", {}).get("partition", "monthly")
                timestamps = pd.DatetimeIndex(
                    pd.to_datetime(data[time_name].values, utc=True)
                )
                if partition == "daily":
                    mask = timestamps.normalize() == period.normalize()
                elif partition == "yearly":
                    mask = timestamps.year == period.year
                else:
                    mask = timestamps.tz_convert(None).to_period("M") == period.tz_localize(None).to_period("M")
                subset = data.isel({time_name: mask})
                target = directory / self._filename(source_key, source, period)
                staged = run_dir / target.name
                subset.to_netcdf(staged)
            staged.replace(target)
            written.append(str(target))
        return written

    def update(
        self,
        start_time: Any,
        end_time: Any,
        *,
        source_keys: Optional[Sequence[str]] = None,
        conflict_policy: str = "fill_missing",
        override: bool = False,
    ) -> DatabaseUpdateReport:
        """Update enabled sources for the half-open interval ``[start, end)``."""
        if _utc(end_time) <= _utc(start_time):
            raise ValueError("end_time must be after start_time")
        if conflict_policy not in {
            "preserve_existing",
            "fill_missing",
            "replace_partition",
            "replace_all",
        }:
            raise ValueError("unsupported conflict policy")
        if override:
            conflict_policy = "replace_partition"
        start, end = _utc(start_time), _utc(end_time)
        report = DatabaseUpdateReport(start.isoformat(), end.isoformat())
        inputs = self.configuration.get("aqdatafusion", {}).get("inputs", {})
        configured = self.configuration.get("input_data", {}).get("datasets", {})
        selected = (
            list(source_keys)
            if source_keys is not None
            else [
                key
                for key, settings in inputs.items()
                if isinstance(settings, Mapping) and settings.get("enabled")
            ]
        )
        run_id = uuid.uuid4().hex
        for source_key in selected:
            source_started = time.perf_counter()
            if source_key not in configured:
                report.warnings.append(
                    f"{source_key}: no input-data configuration exists"
                )
                continue
            source = configured[source_key]
            directory = self._source_directory(source_key)
            temp = directory / ".tmp" / run_id
            temp.mkdir(parents=True, exist_ok=True)
            source_report: Dict[str, Any] = {
                "status": "checked",
                "missing_timestamps": [],
                "written_files": [],
            }
            try:
                existing = self._read_database(source_key, source)
                expected = self._expected_times(source, start, end)
                observed = self._observed_times(existing, source)
                tolerance = source.get("time", {}).get("tolerance", "0s")
                missing_site_ids: list[str] = []
                if isinstance(existing, pd.DataFrame) and self._site_id_name(source):
                    missing, missing_site_ids = self._missing_site_times(
                        expected, existing, source, tolerance
                    )
                else:
                    missing = self._missing_times(expected, observed, tolerance, source)
                source_report["missing_timestamps"] = [
                    value.isoformat() for value in missing
                ]
                source_report["missing_site_ids"] = missing_site_ids
                incoming = None
                if len(missing):
                    adapter = self.data_sources.get(
                        source_key, UnavailableDataSource(source_key)
                    )
                    request = DataRequest(
                        source_key,
                        self.configuration.get("region", {}).get("region_code", ""),
                        source.get("variables", []),
                        start.to_pydatetime(),
                        end.to_pydatetime(),
                        {
                            "missing_timestamps": source_report["missing_timestamps"],
                            "missing_site_ids": missing_site_ids,
                            "temporary_directory": str(temp),
                        },
                    )
                    incoming = adapter.acquire(request, self.configuration)
                    if incoming is not None:
                        if isinstance(incoming, DatasetBundle):
                            preliminary_site = incoming.metadata.get("preliminary_site_column")
                            validate_site_coordinates(
                                incoming.data,
                                source,
                                "acquisition output",
                                site_id_name=preliminary_site,
                            )
                            source_report["errors"] = list(incoming.errors)
                            bundle_warnings = incoming.metadata.get("warnings", [])
                            if isinstance(bundle_warnings, list) and bundle_warnings:
                                source_report["warnings"] = list(bundle_warnings)
                                for warning in bundle_warnings:
                                    message = (
                                        warning.get("message", str(warning))
                                        if isinstance(warning, Mapping)
                                        else str(warning)
                                    )
                                    report.warnings.append(f"{source_key}: {message}")
                                    self.logger.warning("%s acquisition warning: %s", source_key, warning)
                            for issue in incoming.errors:
                                self.logger.warning(
                                    "%s acquisition issue: %s", source_key, issue
                                )
                        preprocessor = self.preprocessors.get(
                            source_key, GenericPreprocessor(source_key)
                        )
                        incoming = preprocessor.preprocess(incoming, self.configuration)
                        if isinstance(incoming, DatasetBundle):
                            source_report["errors"] = list(incoming.errors)
                            bundle_warnings = incoming.metadata.get("warnings", [])
                            if isinstance(bundle_warnings, list) and bundle_warnings:
                                source_report["warnings"] = list(bundle_warnings)
                                for warning in bundle_warnings:
                                    message = (
                                        warning.get("message", str(warning))
                                        if isinstance(warning, Mapping)
                                        else str(warning)
                                    )
                                    report.warnings.append(f"{source_key}: {message}")
                                    self.logger.warning("%s preprocessing warning: %s", source_key, warning)
                if incoming is not None:
                    merged = self._merge(existing, incoming, source, conflict_policy)
                    if isinstance(incoming, DatasetBundle):
                        incoming_data = incoming.data
                    else:
                        incoming_data = incoming
                    if isinstance(incoming_data, pd.DataFrame) and incoming_data.empty:
                        source_report["status"] = "no_data"
                    else:
                        source_report["written_files"] = self._write(
                            source_key, source, merged, temp
                        )
                        cleanup = getattr(adapter, "cleanup", None)
                        if callable(cleanup) and isinstance(incoming, DatasetBundle):
                            try:
                                cleanup(incoming)
                                source_report["temporary_files_cleaned"] = True
                            except OSError as error:
                                source_report["temporary_files_cleaned"] = False
                                source_report.setdefault("warnings", []).append(
                                    f"Temporary-file cleanup failed: {error}"
                                )
                                report.warnings.append(
                                    f"{source_key}: temporary-file cleanup failed: {error}"
                                )
                        source_report["status"] = "updated"
                catalog = DatasetCatalog(
                    source_key,
                    directory,
                    {
                        **source,
                        "region_code": self.configuration.get("region", {}).get(
                            "region_code"
                        ),
                    },
                ).rebuild()
                source_report["catalog_files"] = len(catalog["files"])
                integrity = verify_database_integrity(
                    source_key,
                    directory,
                    self._source_with_context(source_key, source),
                    expected_times=expected,
                )
                source_report["integrity"] = integrity
                for warning in integrity["warnings"]:
                    report.warnings.append(f"{source_key}: {warning}")
                    self.logger.warning("%s integrity warning: %s", source_key, warning)
                if not integrity["valid"]:
                    source_report["status"] = "failed"
                    source_report["errors"] = integrity["errors"]
                    report.warnings.extend(
                        f"{source_key}: integrity error: {error}"
                        for error in integrity["errors"]
                    )
                    self.logger.error(
                        "%s database integrity verification failed: %s",
                        source_key,
                        integrity["errors"],
                    )
            except AcquisitionError as error:
                source_report["status"] = "failed"
                source_report["errors"] = [error.issue]
                source_report["error"] = str(error)
                report.warnings.append(f"{source_key}: {error}")
                self.logger.error("Database acquisition failed for %s: %s", source_key, error)
            except (
                FileNotFoundError,
                OSError,
                ValueError,
                ImportError,
                RuntimeError,
            ) as error:
                source_report["status"] = "failed"
                source_report["error"] = str(error)
                source_report["errors"] = [{"kind": "input_or_processing", "message": str(error), "retryable": False}]
                report.warnings.append(f"{source_key}: {error}")
                self.logger.exception("Database update failed for %s", source_key)
            finally:
                shutil.rmtree(temp, ignore_errors=True)
                source_report["wall_time_seconds"] = round(
                    time.perf_counter() - source_started, 3
                )
            report.sources[source_key] = source_report
        self.logger.info(
            "Database update completed: %s",
            json.dumps(report.as_dict(), sort_keys=True),
        )
        return report


__all__ = ["DatabaseManager", "DatabaseUpdateReport"]
