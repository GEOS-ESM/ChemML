"""Generic incremental database update orchestration for input datasets."""

from __future__ import annotations

import json
import logging
import re
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from aqforecast.contracts import DataRequest, DatasetBundle
from aqforecast.data_acquisition.airnow import AirNowDataSource
from aqforecast.data_acquisition.base import UnavailableDataSource
from aqforecast.data_management.catalog import DatasetCatalog
from aqforecast.preprocessing.airnow import AirNowPreprocessor
from aqforecast.preprocessing.generic import GenericPreprocessor


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
    ) -> None:
        self.configuration = configuration
        self.data_sources = dict(data_sources or {})
        self.preprocessors = dict(preprocessors or {})
        self.logger = logger or logging.getLogger("aqforecast.data_management")
        provider = (
            self.configuration.get("region", {})
            .get("ground_monitoring", {})
            .get("provider")
        )
        if str(provider).casefold() == "airnow":
            self.data_sources.setdefault(
                "ground_monitors", AirNowDataSource(logger=self.logger)
            )
            self.preprocessors.setdefault("ground_monitors", AirNowPreprocessor())

    def _expected_times(
        self, source: Mapping[str, Any], start: pd.Timestamp, end: pd.Timestamp
    ) -> pd.DatetimeIndex:
        time_config = source.get("time", {})
        availability = time_config.get("availability", {})
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
        return pd.DatetimeIndex(values)

    def _source_directory(self, source_key: str) -> Path:
        return Path(
            self.configuration["filepaths"]["data_sources"][source_key]
        ).expanduser()

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
        if not files:
            return pd.DataFrame() if file_format == "csv" else None
        if file_format == "csv":
            return pd.concat((pd.read_csv(path) for path in files), ignore_index=True)
        import xarray as xr

        return xr.open_mfdataset(files, combine="by_coords")

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

    def _validate_site_coordinates(
        self, data: Any, source: Mapping[str, Any], label: str
    ) -> None:
        """Ensure each site identifier has one stable coordinate pair."""

        if not isinstance(data, pd.DataFrame) or data.empty:
            return
        site_id_name = self._site_id_name(source)
        if site_id_name is None:
            return
        coordinate_names = source.get("coordinate_names", {})
        latitude_name = coordinate_names.get("latitude", "lat")
        longitude_name = coordinate_names.get("longitude", "lon")
        required = [site_id_name, latitude_name, longitude_name]
        missing = [name for name in required if name not in data.columns]
        if missing:
            raise ValueError(
                f"{label} is missing site coordinate columns: {', '.join(missing)}"
            )

        incomplete = data[required].isna().any(axis=1)
        if incomplete.any():
            raise ValueError(
                f"{label} contains rows with missing site ID or site coordinates"
            )

        site_coordinates = data[required]
        tolerance = float(source.get("site_coordinate_tolerance", 1e-6))
        grouped = site_coordinates.groupby(site_id_name)[
            [latitude_name, longitude_name]
        ].agg(["min", "max"])
        for site_id, values in grouped.iterrows():
            latitude_delta = float(
                values[(latitude_name, "max")] - values[(latitude_name, "min")]
            )
            longitude_delta = float(
                values[(longitude_name, "max")] - values[(longitude_name, "min")]
            )
            if latitude_delta > tolerance or longitude_delta > tolerance:
                raise ValueError(
                    f"{label} site {site_id!r} has inconsistent coordinates; "
                    f"maximum allowed difference is {tolerance} degrees"
                )

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
                    expected, self._observed_times(data, source), tolerance
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
            missing = self._missing_times(expected, observed, tolerance)
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
        self, expected: pd.DatetimeIndex, observed: pd.DatetimeIndex, tolerance: Any
    ) -> pd.DatetimeIndex:
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
                    pd.Timestamp(year=int(year), tz="UTC")
                    for year in sorted(set(times.year))
                ]
            )
        return times.to_period("M").to_timestamp().tz_localize("UTC").unique()

    def _merge(
        self, existing: Any, incoming: Any, source: Mapping[str, Any], policy: str
    ) -> Any:
        time_name = source.get("coordinate_names", {}).get("time", "time")
        if incoming is None:
            return existing
        if isinstance(incoming, DatasetBundle):
            incoming = incoming.data
        if isinstance(incoming, pd.DataFrame):
            incoming = incoming.copy()
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
                return incoming.drop_duplicates(subset=identity).reset_index(drop=True)
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
                keep=(
                    "last"
                    if policy in {"replace_partition", "replace_all"}
                    else "first"
                ),
            )
            if policy == "fill_missing":
                combined = (
                    pd.concat([existing, incoming])
                    .groupby(identity, as_index=False)
                    .first()
                )
            return combined.sort_values(time_name).reset_index(drop=True)
        import xarray as xr

        if existing is None:
            return incoming
        if not isinstance(existing, xr.Dataset):
            return incoming
        if policy == "replace_all":
            return incoming
        combined = xr.concat([existing, incoming], dim=time_name).sortby(time_name)
        unique_times = (
            pd.DatetimeIndex(pd.to_datetime(combined[time_name].values, utc=True))
            .unique()
            .sort_values()
        )
        records = []
        for timestamp in unique_times:
            candidates = combined.sel({time_name: [timestamp]})
            if policy == "replace_partition":
                record = candidates.isel({time_name: -1})
            else:
                record = candidates.isel({time_name: 0})
                for index in range(1, candidates.sizes.get(time_name, 1)):
                    record = record.combine_first(candidates.isel({time_name: index}))
            records.append(record.expand_dims({time_name: [timestamp]}))
        return xr.concat(records, dim=time_name).sortby(time_name)

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
                    mask = timestamps.dt.to_period("M") == period.to_period("M")
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
                    mask = timestamps.to_period("M") == period.to_period("M")
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
        inputs = self.configuration.get("aqforecast", {}).get("inputs", {})
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
                    missing = self._missing_times(expected, observed, tolerance)
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
                        preprocessor = self.preprocessors.get(
                            source_key, GenericPreprocessor(source_key)
                        )
                        incoming = preprocessor.preprocess(incoming, self.configuration)
                if incoming is not None:
                    merged = self._merge(existing, incoming, source, conflict_policy)
                    source_report["written_files"] = self._write(
                        source_key, source, merged, temp
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
            except (
                FileNotFoundError,
                OSError,
                ValueError,
                ImportError,
                RuntimeError,
            ) as error:
                source_report["status"] = "failed"
                source_report["error"] = str(error)
                report.warnings.append(f"{source_key}: {error}")
                self.logger.exception("Database update failed for %s", source_key)
            finally:
                shutil.rmtree(temp, ignore_errors=True)
            report.sources[source_key] = source_report
        self.logger.info(
            "Database update completed: %s",
            json.dumps(report.as_dict(), sort_keys=True),
        )
        return report


__all__ = ["DatabaseManager", "DatabaseUpdateReport"]
