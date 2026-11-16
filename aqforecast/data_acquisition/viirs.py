"""Earthdata acquisition for the VIIRS/JPSS2 VJ219A2 product."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from aqforecast.contracts import DataRequest, DatasetBundle
from aqforecast.data_acquisition.base import AcquisitionError
from aqforecast.data_acquisition.generic import RemoteDataSource


SHORT_NAME = "VJ219A2"
CONCEPT_ID = "C2885060488-LPCLOUD"


class ViirsAodDataSource(RemoteDataSource):
    """Download VJ219A2 version-002 granules for a configured region."""

    source_key = "VIIRS"

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
                "earthaccess is required for VIIRS acquisition", kind="dependency"
            ) from error

        credentials = configuration.get("credentials", {}).get("earthdata", {})
        username = credentials.get("username")
        password = credentials.get("password")
        if not username or not password:
            raise AcquisitionError(
                "Earthdata username and password are required for VIIRS acquisition",
                kind="credentials",
            )
        os.environ["EARTHDATA_USERNAME"] = str(username)
        os.environ["EARTHDATA_PASSWORD"] = str(password)
        try:
            earthaccess.login(strategy="environment")
        except Exception as error:
            raise AcquisitionError(
                "Earthdata authentication failed for VIIRS",
                kind="authentication",
                retryable=False,
                details=str(error),
            ) from error

        source = configuration.get("input_data", {}).get("datasets", {}).get(
            self.source_key, {}
        )
        access = source.get("access", {})
        temporal = (
            request.start_time.isoformat().replace("+00:00", "Z"),
            request.end_time.isoformat().replace("+00:00", "Z"),
        )
        search_kwargs: dict[str, Any] = {
            "short_name": access.get("collection_short_name", SHORT_NAME),
            "temporal": temporal,
            "bounding_box": _bounding_box(configuration),
            "count": -1,
        }
        if access.get("collection_version"):
            search_kwargs["version"] = str(access["collection_version"])
        try:
            granules = earthaccess.search_data(**search_kwargs)
            if not granules and access.get("concept_id", CONCEPT_ID):
                granules = earthaccess.search_data(
                    concept_id=access.get("concept_id", CONCEPT_ID),
                    temporal=temporal,
                    bounding_box=_bounding_box(configuration),
                    count=-1,
                )
        except Exception as error:
            raise AcquisitionError(
                "Earthdata search failed for VJ219A2",
                kind="search",
                retryable=True,
                details=str(error),
            ) from error

        if not granules:
            return DatasetBundle(self.source_key, [], {"granules": 0}, [])

        temporary_directory = Path(
            request.metadata.get("temporary_directory")
            or access.get("temporary_directory", ".tmp")
        )
        temporary_directory.mkdir(parents=True, exist_ok=True)
        try:
            downloaded = earthaccess.download(
                granules,
                local_path=str(temporary_directory),
                threads=int(access.get("download_threads", 2)),
            )
        except Exception as error:
            raise AcquisitionError(
                "Earthdata download failed for VJ219A2",
                kind="download",
                retryable=True,
                details=str(error),
            ) from error

        paths = [Path(path) for path in downloaded]
        paths = [path for path in paths if SHORT_NAME in path.name]
        return DatasetBundle(
            self.source_key,
            paths,
            {
                "earthdata_short_name": SHORT_NAME,
                "earthdata_concept_id": access.get("concept_id", CONCEPT_ID),
                "earthdata_version": access.get("collection_version", "002"),
                "granules": len(paths),
                "requested_start_time": request.start_time.isoformat(),
                "requested_end_time": request.end_time.isoformat(),
            },
            [],
        )


def _bounding_box(configuration: Mapping[str, Any]) -> tuple[float, float, float, float]:
    bounds = configuration.get("region", {}).get("bounds", {})
    latitude = bounds.get("latitude", [])
    longitude = bounds.get("longitude", [])
    if len(latitude) != 2 or len(longitude) != 2:
        raise AcquisitionError(
            "VIIRS acquisition requires two-number region bounds", kind="configuration"
        )
    return (float(longitude[0]), float(latitude[0]), float(longitude[1]), float(latitude[1]))


__all__ = ["SHORT_NAME", "CONCEPT_ID", "ViirsAodDataSource"]
