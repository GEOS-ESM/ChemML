"""Earthdata acquisition for the MODIS MCD12Q1 land-cover product."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from aqdatafusion.contracts import DataRequest, DatasetBundle
from aqdatafusion.data_acquisition.base import AcquisitionError
from aqdatafusion.data_acquisition.generic import RemoteDataSource


SHORT_NAME = "MCD12Q1"
DEFAULT_CONCEPT_ID = "C2484079608-LPCLOUD"


class LandCoverDataSource(RemoteDataSource):
    """Download MCD12Q1 granules for the requested reference years."""

    source_key = "land_cover"

    def __init__(self, logger: Any = None) -> None:
        self.logger = logger
        super().__init__(self.source_key, self._download)

    def _download(
        self, request: DataRequest, configuration: Mapping[str, Any]
    ) -> DatasetBundle:
        try:
            import earthaccess
        except ImportError as error:
            raise AcquisitionError(
                "earthaccess is required for land-cover acquisition", kind="dependency"
            ) from error

        credentials = configuration.get("credentials", {}).get("earthdata", {})
        username = credentials.get("username")
        password = credentials.get("password")
        if not username or not password:
            raise AcquisitionError(
                "Earthdata username and password are required for land-cover acquisition",
                kind="credentials",
            )
        os.environ["EARTHDATA_USERNAME"] = str(username)
        os.environ["EARTHDATA_PASSWORD"] = str(password)
        try:
            earthaccess.login(strategy="environment")
        except Exception as error:
            raise AcquisitionError(
                "Earthdata authentication failed for MCD12Q1",
                kind="authentication",
                details=str(error),
            ) from error

        source = configuration.get("input_data", {}).get("datasets", {}).get(
            self.source_key, {}
        )
        access = source.get("access", {})
        requested_years = _requested_years(request)
        current_year = datetime.now(timezone.utc).year
        max_year_fallback = max(0, int(access.get("max_year_fallback", 2)))
        files_by_requested_year: dict[str, list[str]] = {}
        source_year_by_requested_year: dict[str, int] = {}
        granules_by_id: dict[str, Any] = {}

        for requested_year in requested_years:
            search_year = min(requested_year, current_year)
            found = []
            selected_year = None
            for candidate_year in range(
                search_year, search_year - max_year_fallback - 1, -1
            ):
                temporal = (
                    f"{candidate_year}-01-01T00:00:00Z",
                    f"{candidate_year + 1}-01-01T00:00:00Z",
                )
                search_kwargs: dict[str, Any] = {
                    "short_name": access.get("collection_short_name", SHORT_NAME),
                    "temporal": temporal,
                    "bounding_box": _bounding_box(configuration),
                    "count": -1,
                }
                version = access.get("collection_version")
                if version:
                    search_kwargs["version"] = str(version)
                try:
                    found = earthaccess.search_data(**search_kwargs)
                except Exception as error:
                    raise AcquisitionError(
                        f"Earthdata search failed for MCD12Q1 year {candidate_year}",
                        kind="search",
                        retryable=True,
                        details=str(error),
                    ) from error
                if found:
                    selected_year = candidate_year
                    break
            if not found or selected_year is None:
                continue
            paths_for_year = []
            for granule in found:
                identifier = _granule_identifier(granule)
                granules_by_id[identifier] = granule
                paths_for_year.append(identifier)
            files_by_requested_year[str(requested_year)] = paths_for_year
            source_year_by_requested_year[str(requested_year)] = selected_year

        if not granules_by_id:
            return DatasetBundle(
                self.source_key,
                [],
                {
                    "requested_years": requested_years,
                    "files_by_requested_year": files_by_requested_year,
                    "source_year_by_requested_year": source_year_by_requested_year,
                    "granules": 0,
                },
                [],
            )

        temporary_directory = Path(
            request.metadata.get("temporary_directory")
            or access.get("temporary_directory", ".tmp")
        )
        temporary_directory.mkdir(parents=True, exist_ok=True)
        try:
            downloaded = earthaccess.download(
                list(granules_by_id.values()),
                local_path=str(temporary_directory),
                threads=int(access.get("download_threads", 2)),
            )
        except Exception as error:
            raise AcquisitionError(
                "Earthdata download failed for MCD12Q1",
                kind="download",
                retryable=True,
                details=str(error),
            ) from error

        downloaded_paths = [Path(path) for path in downloaded if str(path).lower().endswith(".hdf")]
        path_by_identifier = {
            path.name.rsplit(".hdf", 1)[0]: str(path) for path in downloaded_paths
        }
        resolved_files: dict[str, list[str]] = {}
        for year, identifiers in files_by_requested_year.items():
            resolved_files[year] = [
                path_by_identifier[identifier]
                for identifier in identifiers
                if identifier in path_by_identifier
            ]
        return DatasetBundle(
            self.source_key,
            downloaded_paths,
            {
                "earthdata_short_name": SHORT_NAME,
                "earthdata_concept_id": access.get("concept_id", DEFAULT_CONCEPT_ID),
                "earthdata_version": access.get("collection_version", "061"),
                "requested_years": requested_years,
                "files_by_requested_year": resolved_files,
                "source_year_by_requested_year": source_year_by_requested_year,
                "granules": len(downloaded_paths),
                "requested_start_time": request.start_time.isoformat(),
                "requested_end_time": request.end_time.isoformat(),
            },
            [],
        )


def _requested_years(request: DataRequest) -> list[int]:
    start = pd.Timestamp(request.start_time)
    end = pd.Timestamp(request.end_time) - pd.Timedelta(nanoseconds=1)
    return list(range(start.year, end.year + 1))


def _granule_identifier(granule: Any) -> str:
    umm = granule.get("umm", {}) if hasattr(granule, "get") else {}
    granule_ur = umm.get("GranuleUR")
    if granule_ur:
        return str(granule_ur)
    links = granule.data_links() if hasattr(granule, "data_links") else []
    if links:
        return Path(str(links[0])).name.rsplit(".hdf", 1)[0]
    return str(granule)


def _bounding_box(configuration: Mapping[str, Any]) -> tuple[float, float, float, float]:
    bounds = configuration.get("region", {}).get("bounds", {})
    latitude = bounds.get("latitude", [])
    longitude = bounds.get("longitude", [])
    if len(latitude) != 2 or len(longitude) != 2:
        raise AcquisitionError(
            "MCD12Q1 acquisition requires two-number region bounds", kind="configuration"
        )
    return (float(longitude[0]), float(latitude[0]), float(longitude[1]), float(latitude[1]))


__all__ = ["DEFAULT_CONCEPT_ID", "SHORT_NAME", "LandCoverDataSource"]
