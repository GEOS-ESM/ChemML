"""Regenerable catalogs describing the files in each input-data database."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional


class DatasetCatalog:
    """Build and persist a confirmation catalog for one configured source.

    Configuration remains authoritative.  The catalog is derived from files on
    disk each time it is rebuilt and is intended for discovery, diagnostics,
    and provenance rather than for overriding configuration.
    """

    def __init__(self, source_key: str, directory: Path, configuration: Mapping[str, Any]):
        self.source_key = source_key
        self.directory = Path(directory)
        self.configuration = configuration
        self.filename = str(configuration.get("storage", {}).get("catalog_filename", "catalog.json"))

    def _files(self) -> Iterable[Path]:
        file_format = str(self.configuration.get("storage", {}).get("format", "netcdf"))
        suffix = ".csv" if file_format == "csv" else ".nc"
        if not self.directory.exists():
            return []
        return sorted(
            path for path in self.directory.rglob(f"*{suffix}")
            if ".tmp" not in path.parts
        )

    def _entry(self, path: Path) -> Dict[str, Any]:
        coordinate_names = self.configuration.get("coordinate_names", {})
        time_name = coordinate_names.get("time", "time") if isinstance(coordinate_names, Mapping) else "time"
        variables = self.configuration.get("variables", [])
        entry: Dict[str, Any] = {
            "path": str(path.relative_to(self.directory)),
            "format": self.configuration.get("storage", {}).get("format", "netcdf"),
            "variables_configured": list(variables) if isinstance(variables, list) else [],
        }
        try:
            if entry["format"] == "csv":
                import pandas as pd

                frame = pd.read_csv(path, usecols=lambda column: column == time_name)
                times = pd.to_datetime(frame[time_name], utc=True, errors="coerce").dropna()
                entry["row_count"] = int(len(frame))
                entry["timestamp_count"] = int(times.nunique())
                if len(times):
                    entry["start_time"] = times.min().isoformat()
                    entry["end_time"] = times.max().isoformat()
            else:
                import xarray as xr

                with xr.open_dataset(path) as dataset:
                    times = dataset[time_name].values if time_name in dataset else []
                    parsed = pd_to_utc(times)
                    entry["timestamp_count"] = int(len(set(parsed)))
                    if parsed:
                        entry["start_time"] = min(parsed).isoformat()
                        entry["end_time"] = max(parsed).isoformat()
                    entry["dimensions"] = {name: int(size) for name, size in dataset.sizes.items()}
                    entry["variables_present"] = sorted(str(name) for name in dataset.data_vars)
                    for axis in (coordinate_names.get("latitude", "lat"), coordinate_names.get("longitude", "lon")):
                        if axis in dataset.coords:
                            values = dataset[axis].values
                            if len(values):
                                entry.setdefault("spatial_extent", {})[axis] = [float(values.min()), float(values.max())]
        except Exception as error:  # Catalog generation should not hide a bad file.
            entry["status"] = "unreadable"
            entry["error"] = str(error)
        return entry

    def rebuild(self) -> Dict[str, Any]:
        self.directory.mkdir(parents=True, exist_ok=True)
        entries = [self._entry(path) for path in self._files()]
        catalog = {
            "catalog_version": 1,
            "source_key": self.source_key,
            "region_code": self.configuration.get("region_code"),
            "configuration_authoritative": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "storage": dict(self.configuration.get("storage", {})),
            "files": entries,
        }
        target = self.directory / self.filename
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(target)
        return catalog


def pd_to_utc(values: Any) -> list[datetime]:
    """Convert xarray time values to timezone-aware UTC datetimes."""

    import pandas as pd

    parsed = pd.to_datetime(values, utc=True, errors="coerce")
    return [value.to_pydatetime() for value in parsed if not pd.isna(value)]


__all__ = ["DatasetCatalog"]
