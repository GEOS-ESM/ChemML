"""Earthdata acquisition for the version-2 TROPOMI products."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from aqdatafusion.contracts import DataRequest, DatasetBundle
from aqdatafusion.data_acquisition.base import AcquisitionError
from aqdatafusion.data_acquisition.generic import RemoteDataSource


NO2_SHORT_NAME = "S5P_L2__NO2____HiR"
O3_SHORT_NAME = "S5P_L2__O3_TOT_HiR"


class TropomiDataSource(RemoteDataSource):
    """Download matching TROPOMI NO2 and total-column O3 granules."""

    source_key = "TROPOMI"

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
                "earthaccess is required for TROPOMI acquisition",
                kind="dependency",
            ) from error

        credentials = configuration.get("credentials", {}).get("earthdata", {})
        username = credentials.get("username")
        password = credentials.get("password")
        if not username or not password:
            raise AcquisitionError(
                "Earthdata username and password are required for TROPOMI acquisition",
                kind="credentials",
            )
        os.environ["EARTHDATA_USERNAME"] = str(username)
        os.environ["EARTHDATA_PASSWORD"] = str(password)
        try:
            earthaccess.login(strategy="environment")
        except Exception as error:
            raise AcquisitionError(
                "Earthdata authentication failed for TROPOMI",
                kind="authentication",
                retryable=False,
                details=str(error),
            ) from error

        source = configuration.get("input_data", {}).get("datasets", {}).get(
            self.source_key, {}
        )
        access = source.get("access", {})
        bbox = _bounding_box(configuration)
        temporal = (
            request.start_time.isoformat().replace("+00:00", "Z"),
            request.end_time.isoformat().replace("+00:00", "Z"),
        )
        version = access.get("collection_version")
        granules: dict[str, list[Any]] = {}
        for product, short_name in (("no2", NO2_SHORT_NAME), ("o3", O3_SHORT_NAME)):
            search_kwargs: dict[str, Any] = {
                "short_name": short_name,
                "temporal": temporal,
                "bounding_box": bbox,
                "count": -1,
            }
            if version:
                search_kwargs["version"] = str(version)
            try:
                # earthaccess may return GranuleResults rather than a list;
                # normalize it before combining the two product searches.
                granules[product] = list(earthaccess.search_data(**search_kwargs))
            except Exception as error:
                raise AcquisitionError(
                    f"Earthdata search failed for {short_name}",
                    kind="search",
                    retryable=True,
                    details=str(error),
                ) from error

        all_granules = granules["no2"] + granules["o3"]
        if not all_granules:
            return DatasetBundle(
                self.source_key,
                [],
                {"files_by_product": {"no2": [], "o3": []}},
                [],
            )
        temporary_directory = Path(
            request.metadata.get("temporary_directory")
            or access.get("temporary_directory", ".tmp")
        )
        temporary_directory.mkdir(parents=True, exist_ok=True)
        try:
            downloaded = earthaccess.download(
                all_granules,
                local_path=str(temporary_directory),
                threads=int(access.get("download_threads", 2)),
            )
        except Exception as error:
            raise AcquisitionError(
                "Earthdata download failed for TROPOMI",
                kind="download",
                retryable=True,
                details=str(error),
            ) from error

        paths = [Path(path) for path in downloaded]
        files_by_product = {
            "no2": [str(path) for path in paths if "NO2" in path.name],
            "o3": [str(path) for path in paths if "O3" in path.name],
        }
        missing = [name for name, files in files_by_product.items() if not files]
        warnings = []
        if missing:
            warnings.append(
                {"message": f"No downloaded TROPOMI files for: {', '.join(missing)}"}
            )
        return DatasetBundle(
            self.source_key,
            paths,
            {
                "files_by_product": files_by_product,
                "earthdata_short_names": {
                    "no2": NO2_SHORT_NAME,
                    "o3": O3_SHORT_NAME,
                },
                "warnings": warnings,
            },
            [],
        )


def _bounding_box(configuration: Mapping[str, Any]) -> tuple[float, float, float, float]:
    bounds = configuration.get("region", {}).get("bounds", {})
    latitude = bounds.get("latitude", [])
    longitude = bounds.get("longitude", [])
    if len(latitude) != 2 or len(longitude) != 2:
        raise AcquisitionError(
            "TROPOMI acquisition requires two-number region bounds",
            kind="configuration",
        )
    return (float(longitude[0]), float(latitude[0]), float(longitude[1]), float(latitude[1]))


__all__ = ["NO2_SHORT_NAME", "O3_SHORT_NAME", "TropomiDataSource"]
