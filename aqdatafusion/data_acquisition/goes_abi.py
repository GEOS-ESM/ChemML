"""Public NOAA S3 acquisition for GOES ABI aerosol optical depth."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from aqdatafusion.contracts import DataRequest, DatasetBundle
from aqdatafusion.data_acquisition.base import AcquisitionError
from aqdatafusion.data_acquisition.generic import RemoteDataSource


SATELLITE_ORDER = ("noaa-goes19", "noaa-goes16", "noaa-goes18", "noaa-goes17")
PRODUCT = "ABI-L2-AODC"


class GoesAbiAodDataSource(RemoteDataSource):
    """Acquire GOES ABI AODC granules from the anonymous NOAA S3 bucket.

    Satellite selection is performed independently for each UTC hour.  The
    configured satellite order is used, so a satellite with no files for an
    hour does not prevent a later satellite from supplying that hour.
    """

    source_key = "GOES-ABI"

    def __init__(self, logger: Any = None) -> None:
        self.logger = logger
        super().__init__(self.source_key, self._download)

    def _download(
        self, request: DataRequest, configuration: Mapping[str, Any]
    ) -> DatasetBundle:
        try:
            import s3fs
        except ImportError as error:
            raise AcquisitionError(
                "s3fs is required for GOES-ABI acquisition", kind="dependency"
            ) from error

        if request.start_time is None or request.end_time is None:
            raise AcquisitionError(
                "GOES-ABI acquisition requires a UTC start and end time",
                kind="configuration",
            )
        source = configuration.get("input_data", {}).get("datasets", {}).get(
            self.source_key, {}
        )
        access = source.get("access", {})
        product = str(access.get("product", PRODUCT))
        satellite_order = tuple(access.get("satellite_order", SATELLITE_ORDER))
        if not satellite_order:
            raise AcquisitionError(
                "GOES-ABI access.satellite_order cannot be empty",
                kind="configuration",
            )
        start = _utc_timestamp(request.start_time)
        end = _utc_timestamp(request.end_time)
        hours = pd.date_range(start.floor("h"), end, freq="1h", inclusive="left")

        try:
            fs = s3fs.S3FileSystem(anon=True)
        except Exception as error:
            raise AcquisitionError(
                "Could not initialize anonymous NOAA S3 access for GOES-ABI",
                kind="access",
                retryable=True,
                details=str(error),
            ) from error

        remote_by_satellite: dict[str, list[str]] = {}
        selected_satellites: dict[str, str] = {}
        candidates_by_satellite_hour: dict[tuple[str, pd.Timestamp], list[str]] = {}
        days = pd.date_range(
            hours[0].normalize(), hours[-1].normalize(), freq="1D"
        ) if len(hours) else pd.DatetimeIndex([])
        for day in days:
            for satellite in satellite_order:
                prefix = f"{satellite}/{product}/{day.year}/{day.day_of_year:03d}"
                try:
                    candidates = [
                        str(path)
                        for path in fs.glob(f"{prefix}/*/*.nc")
                        if str(path).endswith(".nc")
                    ]
                except FileNotFoundError:
                    candidates = []
                except Exception as error:
                    raise AcquisitionError(
                        f"GOES-ABI S3 listing failed for {prefix}",
                        kind="search",
                        retryable=True,
                        details=str(error),
                    ) from error
                for hour in hours[hours.normalize() == day]:
                    hour_candidates = [
                        path for path in candidates if f"/{hour.hour:02d}/" in path
                    ]
                    if hour_candidates:
                        candidates_by_satellite_hour[(satellite, hour)] = sorted(
                            hour_candidates
                        )

        for hour in hours:
            selected = None
            for satellite in satellite_order:
                candidates = candidates_by_satellite_hour.get((satellite, hour), [])
                if candidates:
                    if selected is None:
                        selected = satellite
                    remote_by_satellite.setdefault(satellite, []).extend(candidates)
            if selected is not None:
                selected_satellites[hour.isoformat()] = selected

        for satellite, paths in remote_by_satellite.items():
            remote_by_satellite[satellite] = list(dict.fromkeys(paths))

        remotes = [path for paths in remote_by_satellite.values() for path in paths]
        if not remotes:
            return DatasetBundle(
                self.source_key,
                [],
                {
                    "product": product,
                    "satellite_order": list(satellite_order),
                    "selected_satellites": selected_satellites,
                    "granules": 0,
                    "requested_start_time": request.start_time.isoformat(),
                    "requested_end_time": request.end_time.isoformat(),
                },
                [],
            )

        temporary_directory = Path(
            request.metadata.get("temporary_directory")
            or access.get("temporary_directory", ".tmp")
        )
        temporary_directory.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        try:
            for remote in remotes:
                local = temporary_directory / Path(remote).name
                fs.get(remote, str(local))
                paths.append(local)
        except Exception as error:
            raise AcquisitionError(
                "GOES-ABI S3 download failed",
                kind="download",
                retryable=True,
                details=str(error),
            ) from error

        # Retain the satellite grouping needed by the preprocessor's quality
        # fallback logic. All available satellites are staged so a preferred
        # satellite with no valid retrievals can fall through to the next one.
        files_by_satellite = {
            satellite: [
                str(temporary_directory / Path(remote).name)
                for remote in remotes_for_satellite
            ]
            for satellite, remotes_for_satellite in remote_by_satellite.items()
        }
        return DatasetBundle(
            self.source_key,
            paths,
            {
                "product": product,
                "satellite_order": list(satellite_order),
                "selected_satellites": selected_satellites,
                "files_by_satellite": files_by_satellite,
                "remote_files": remotes,
                "granules": len(paths),
                "requested_start_time": request.start_time.isoformat(),
                "requested_end_time": request.end_time.isoformat(),
            },
            [],
        )


def _utc_timestamp(value: datetime) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(timezone.utc)
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp


__all__ = ["PRODUCT", "SATELLITE_ORDER", "GoesAbiAodDataSource"]
