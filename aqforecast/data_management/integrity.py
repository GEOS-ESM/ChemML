"""Post-update integrity checks for partitioned input-data databases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional

import numpy as np
import pandas as pd


def _time_name(source: Mapping[str, Any]) -> str:
    return str(source.get("coordinate_names", {}).get("time", "time"))


def _configured_variables(source: Mapping[str, Any]) -> list[str]:
    values = source.get("variables", [])
    return [str(value) for value in values] if isinstance(values, list) else []


def _variable_candidates(name: str, source: Mapping[str, Any]) -> list[str]:
    prefix = source.get("variable_prefix", "")
    candidates = [name]
    if prefix and not name.startswith(str(prefix)):
        candidates.append(f"{prefix}{name}")
    return candidates


def _utc_times(values: Any) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(values, utc=True, errors="coerce"))


def _files(directory: Path, file_format: str) -> list[Path]:
    suffix = ".csv" if file_format == "csv" else ".nc"
    if not directory.exists():
        return []
    return sorted(
        path for path in directory.rglob(f"*{suffix}") if ".tmp" not in path.parts
    )


def _axis_values(dataset: Any, name: str) -> Optional[np.ndarray]:
    if name not in dataset.coords and name not in dataset.dims:
        return None
    return np.asarray(dataset[name].values)


def _same_axis(left: np.ndarray, right: np.ndarray) -> bool:
    if left.shape != right.shape:
        return False
    if np.issubdtype(left.dtype, np.number) and np.issubdtype(right.dtype, np.number):
        return bool(np.allclose(left, right, equal_nan=True))
    return bool(np.array_equal(left, right))


def _missing_expected(
    expected: pd.DatetimeIndex,
    observed: pd.DatetimeIndex,
    source: Mapping[str, Any],
) -> pd.DatetimeIndex:
    """Apply the source's aggregation and timestamp tolerance rules."""

    availability = source.get("time", {}).get("availability", {})
    if availability.get("mode") == "yearly":
        observed_years = {value.year for value in observed}
        fallback = int(source.get("access", {}).get("max_year_fallback", 0))
        return pd.DatetimeIndex(
            [value for value in expected if not any(0 <= value.year - year <= fallback for year in observed_years)]
        )
    if source.get("time", {}).get("aggregation") == "daily_mean":
        observed_dates = {value.normalize() for value in observed}
        return pd.DatetimeIndex([value for value in expected if value.normalize() not in observed_dates])
    tolerance = pd.Timedelta(source.get("time", {}).get("tolerance", "0s"))
    observed_ns = observed.tz_localize(None).asi8
    missing = [
        value
        for value in expected
        if not len(observed_ns)
        or not bool((np.abs(observed_ns - value.tz_localize(None).value) <= tolerance.value).any())
    ]
    return pd.DatetimeIndex(missing)


def verify_database_integrity(
    source_key: str,
    directory: Path,
    source: Mapping[str, Any],
    *,
    expected_times: Optional[pd.DatetimeIndex] = None,
) -> dict[str, Any]:
    """Inspect all partitions and their catalog for one configured source.

    Missing expected timestamps are warnings because source availability is not
    necessarily continuous. Malformed files, missing schema elements,
    duplicate records, inconsistent grids, and catalog mismatches are errors.
    """

    directory = Path(directory)
    file_format = str(source.get("storage", {}).get("format", "netcdf"))
    coordinate_names = source.get("coordinate_names", {})
    time_name = _time_name(source)
    latitude_name = str(coordinate_names.get("latitude", "lat"))
    longitude_name = str(coordinate_names.get("longitude", "lon"))
    configured_variables = _configured_variables(source)
    files = _files(directory, file_format)
    errors: list[str] = []
    warnings: list[str] = []
    observed: list[pd.Timestamp] = []
    record_keys: set[tuple[Any, ...]] = set()
    grids: Optional[tuple[np.ndarray, np.ndarray]] = None
    file_checks: list[dict[str, Any]] = []

    for path in files:
        check: dict[str, Any] = {"path": str(path.relative_to(directory)), "valid": True}
        try:
            if file_format == "csv":
                frame = pd.read_csv(path)
                required = [time_name]
                site_id = source.get("site_id")
                if site_id:
                    required.extend([str(site_id), latitude_name, longitude_name])
                required.extend(configured_variables)
                missing = sorted(set(required).difference(frame.columns))
                if missing:
                    raise ValueError(f"missing columns: {', '.join(missing)}")
                times = _utc_times(frame[time_name])
                if times.isna().any():
                    raise ValueError("contains invalid timestamps")
                observed.extend(times.tolist())
                identity = [str(site_id), time_name] if site_id else [time_name]
                identity.extend(
                    name for name in (latitude_name, longitude_name) if name in frame
                )
                duplicate_count = int(frame.duplicated(identity).sum())
                if duplicate_count:
                    raise ValueError(f"contains {duplicate_count} duplicate records")
                for row in frame[identity].itertuples(index=False, name=None):
                    key = tuple(row)
                    if key in record_keys:
                        raise ValueError("duplicates records in another partition")
                    record_keys.add(key)
                check["record_count"] = int(len(frame))
                check["timestamp_count"] = int(times.nunique())
            else:
                import xarray as xr

                with xr.open_dataset(path) as dataset:
                    missing_coordinates = [
                        name
                        for name in (time_name, latitude_name, longitude_name)
                        if name not in dataset.coords and name not in dataset.dims
                    ]
                    if missing_coordinates:
                        raise ValueError(
                            "missing coordinates/dimensions: "
                            + ", ".join(missing_coordinates)
                        )
                    present = set(str(name) for name in dataset.data_vars)
                    missing_variables = [
                        name
                        for name in configured_variables
                        if not present.intersection(_variable_candidates(name, source))
                    ]
                    if missing_variables:
                        raise ValueError(
                            "missing variables: " + ", ".join(missing_variables)
                        )
                    times = _utc_times(dataset[time_name].values)
                    if times.isna().any():
                        raise ValueError("contains invalid timestamps")
                    observed.extend(times.tolist())
                    lead_name = "forecast_lead_day"
                    if lead_name in dataset.dims or lead_name in dataset.coords:
                        leads = np.asarray(dataset[lead_name].values)
                        if len(leads) != len(set(leads.tolist())):
                            raise ValueError("contains duplicate forecast lead values")
                        keys = [(time, lead) for time in times for lead in leads]
                    else:
                        keys = [(time,) for time in times]
                    duplicate_count = len(keys) - len(set(keys))
                    if duplicate_count:
                        raise ValueError(f"contains {duplicate_count} duplicate records")
                    for key in keys:
                        if key in record_keys:
                            raise ValueError("duplicates records in another partition")
                        record_keys.add(key)
                    latitude = _axis_values(dataset, latitude_name)
                    longitude = _axis_values(dataset, longitude_name)
                    if latitude is None or longitude is None:
                        raise ValueError("missing spatial coordinate values")
                    if not np.isfinite(latitude).all() or not np.isfinite(longitude).all():
                        raise ValueError("contains non-finite spatial coordinates")
                    if latitude.ndim != 1 or longitude.ndim != 1:
                        raise ValueError("spatial coordinates must be one-dimensional")
                    if len(latitude) > 1 and not np.all(np.diff(latitude) > 0):
                        raise ValueError("latitude coordinate is not strictly increasing")
                    if len(longitude) > 1 and not np.all(np.diff(longitude) > 0):
                        raise ValueError("longitude coordinate is not strictly increasing")
                    current_grid = (latitude, longitude)
                    if grids is None:
                        grids = current_grid
                    elif not all(_same_axis(old, new) for old, new in zip(grids, current_grid)):
                        raise ValueError("spatial grid differs from another partition")
                    check["dimensions"] = {str(name): int(size) for name, size in dataset.sizes.items()}
                    check["timestamp_count"] = int(times.nunique())
            check["valid"] = True
        except Exception as error:
            check["valid"] = False
            check["error"] = str(error)
            errors.append(f"{path.name}: {error}")
        finally:
            file_checks.append(check)

    observed_index = _utc_times(observed).dropna().unique().sort_values()
    timestamp_check: dict[str, Any] = {
        "observed_count": int(len(observed_index)),
        "expected_count": int(len(expected_times)) if expected_times is not None else None,
        "missing": [],
    }
    if expected_times is not None:
        expected_index = _utc_times(expected_times).dropna().unique().sort_values()
        missing = _missing_expected(expected_index, observed_index, source)
        timestamp_check["missing"] = [value.isoformat() for value in missing]
        if len(missing):
            warnings.append(
                f"{len(missing)} expected timestamps are unavailable or missing"
            )
    if not files:
        warnings.append("no data partitions are present")

    catalog_check: dict[str, Any] = {"exists": False, "valid": True}
    catalog_name = str(source.get("storage", {}).get("catalog_filename", "catalog.json"))
    catalog_path = directory / catalog_name
    if not catalog_path.exists():
        errors.append(f"catalog is missing: {catalog_name}")
        catalog_check["valid"] = False
    else:
        catalog_check["exists"] = True
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            entries = catalog.get("files", [])
            catalog_files = {str(entry.get("path")) for entry in entries}
            actual_files = {str(path.relative_to(directory)) for path in files}
            if catalog_files != actual_files:
                errors.append("catalog file list does not match data partitions")
                catalog_check["valid"] = False
            checks_by_path = {check["path"]: check for check in file_checks}
            for entry in entries:
                path_name = str(entry.get("path"))
                file_check = checks_by_path.get(path_name)
                if file_check and file_check.get("valid") and "timestamp_count" in entry:
                    if int(entry["timestamp_count"]) != int(file_check["timestamp_count"]):
                        errors.append(
                            f"catalog timestamp count disagrees with partition: {path_name}"
                        )
                        catalog_check["valid"] = False
            unreadable = [entry.get("path") for entry in entries if entry.get("status") == "unreadable"]
            if unreadable:
                errors.append("catalog contains unreadable files: " + ", ".join(map(str, unreadable)))
                catalog_check["valid"] = False
            catalog_check["file_count"] = len(entries)
        except (OSError, json.JSONDecodeError, AttributeError) as error:
            errors.append(f"catalog cannot be read: {error}")
            catalog_check["valid"] = False

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "timestamps": timestamp_check,
            "files": file_checks,
            "catalog": catalog_check,
            "coordinates": {"grid_consistent": grids is not None or not files},
            "required_variables": {"configured": configured_variables},
            "duplicates": {"checked": True},
            "partitions": {"count": len(files)},
        },
    }


__all__ = ["verify_database_integrity"]
