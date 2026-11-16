"""Authenticated OpenDAP acquisition for TEMPO NO2 Level-3 granules."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Mapping

import xarray as xr

from aqforecast.contracts import DataRequest, DatasetBundle
from aqforecast.data_acquisition.base import AcquisitionError
from aqforecast.data_acquisition.generic import RemoteDataSource
from aqforecast.utils.opendap import EarthdataOpenDAPClient


SHORT_NAME = "TEMPO_NO2_L3"
CONCEPT_ID = "C3685896708-LARC_CLOUD"
PRODUCT_GROUP = "product"
SCIENCE_VARIABLES = ("vertical_column_troposphere", "main_data_quality_flag")


class TempoNo2DataSource(RemoteDataSource):
    """Search TEMPO granules and cache spatial OpenDAP subsets locally."""

    source_key = "TEMPO_NO2"

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
                "earthaccess is required for TEMPO acquisition", kind="dependency"
            ) from error

        credentials = configuration.get("credentials", {}).get("earthdata", {})
        if not credentials.get("username") or not credentials.get("password"):
            raise AcquisitionError(
                "Earthdata username and password are required for TEMPO acquisition",
                kind="credentials",
            )
        os.environ["EARTHDATA_USERNAME"] = str(credentials["username"])
        os.environ["EARTHDATA_PASSWORD"] = str(credentials["password"])
        try:
            client = EarthdataOpenDAPClient.from_credentials(credentials)
            source = configuration.get("input_data", {}).get("datasets", {}).get(
                self.source_key, {}
            )
            access = source.get("access", {})
            search_kwargs: dict[str, Any] = {
                "short_name": access.get("collection_short_name", SHORT_NAME),
                "temporal": (
                    request.start_time.isoformat().replace("+00:00", "Z"),
                    request.end_time.isoformat().replace("+00:00", "Z"),
                ),
                "bounding_box": _bounding_box(configuration),
                "count": -1,
            }
            if access.get("collection_version"):
                search_kwargs["version"] = str(access["collection_version"])
            granules = earthaccess.search_data(**search_kwargs)
        except Exception as error:
            raise AcquisitionError(
                "Earthdata search or authentication failed for TEMPO NO2",
                kind="search",
                retryable=True,
                details=str(error),
            ) from error

        urls = [url for granule in granules for url in granule.data_links()]
        if not urls:
            return DatasetBundle(self.source_key, [], {"granules": 0}, [])

        cache_directory = _cache_directory(request, configuration)
        cache_directory.mkdir(parents=True, exist_ok=True)
        bbox = _bounding_box(configuration)
        files: list[Path] = []
        failures: list[dict[str, Any]] = []
        for url in urls:
            name = url.rsplit("/", 1)[-1]
            cache_name = _cache_name(name, url, bbox)
            target = cache_directory / cache_name
            if _valid_cache(target):
                files.append(target)
                continue
            temporary = target.with_suffix(target.suffix + ".part")
            try:
                subset = client.open_subset(
                    url,
                    collection_concept_id=access.get(
                        "concept_id", CONCEPT_ID
                    ),
                    group=access.get("group", PRODUCT_GROUP),
                    variables=tuple(
                        access.get("variables", SCIENCE_VARIABLES)
                    ),
                    bounding_box=bbox,
                    load=True,
                )
                subset.attrs.update(
                    {
                        "source_url": url,
                        "source_short_name": SHORT_NAME,
                        "subset_bounding_box": repr(bbox),
                    }
                )
                subset.to_netcdf(temporary)
                temporary.replace(target)
                subset.close()
                files.append(target)
            except Exception as error:
                temporary.unlink(missing_ok=True)
                failures.append({"url": url, "message": str(error)})

        if not files and failures:
            raise AcquisitionError(
                "No TEMPO NO2 OpenDAP subsets could be acquired",
                kind="download",
                retryable=True,
                details=failures,
            )
        metadata = {
            "earthdata_short_name": SHORT_NAME,
            "earthdata_concept_id": access.get("concept_id", CONCEPT_ID),
            "granules": len(files),
            "cached_subset_directory": str(cache_directory),
            "cached_subset_files": [str(path) for path in files],
            "request_start_time": request.start_time.isoformat(),
            "request_end_time": request.end_time.isoformat(),
            "resumed_from_cache": len(files) - len(failures) < len(urls),
            "warnings": ([{"message": "Some TEMPO granules failed", "failures": failures}]
                         if failures else []),
        }
        return DatasetBundle(self.source_key, files, metadata, [])

    def cleanup(self, dataset: DatasetBundle) -> None:
        """Remove cached subsets after their processed data are archived."""

        paths = dataset.metadata.get("cached_subset_files", [])
        for value in paths:
            path = Path(value)
            path.unlink(missing_ok=True)
            path.with_suffix(path.suffix + ".part").unlink(missing_ok=True)


def _cache_name(name: str, url: str, bbox: tuple[float, float, float, float]) -> str:
    key = hashlib.sha256(f"{url}|{bbox}".encode()).hexdigest()[:12]
    return f"{key}_{name}"


def _valid_cache(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        with xr.open_dataset(path) as dataset:
            return all(variable in dataset for variable in SCIENCE_VARIABLES)
    except (OSError, ValueError):
        return False


def _cache_directory(
    request: DataRequest, configuration: Mapping[str, Any]
) -> Path:
    source = configuration.get("input_data", {}).get("datasets", {}).get(
        "TEMPO_NO2", {}
    )
    access = source.get("access", {})
    configured_source = (
        configuration.get("filepaths", {}).get("data_sources", {}).get("TEMPO_NO2")
    )
    if configured_source:
        return Path(configured_source).expanduser() / str(
            access.get("cache_subdirectory", ".tmp")
        )
    return Path(
        request.metadata.get("temporary_directory")
        or access.get("temporary_directory", ".tmp")
    )


def _bounding_box(configuration: Mapping[str, Any]) -> tuple[float, float, float, float]:
    bounds = configuration.get("region", {}).get("bounds", {})
    latitude = bounds.get("latitude", [])
    longitude = bounds.get("longitude", [])
    if len(latitude) != 2 or len(longitude) != 2:
        raise AcquisitionError(
            "TEMPO acquisition requires two-number region bounds",
            kind="configuration",
        )
    return (float(longitude[0]), float(latitude[0]), float(longitude[1]), float(latitude[1]))


__all__ = ["CONCEPT_ID", "SHORT_NAME", "TempoNo2DataSource"]
