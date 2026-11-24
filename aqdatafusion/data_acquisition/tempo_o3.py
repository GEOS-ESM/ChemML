"""Authenticated OpenDAP acquisition for TEMPO Level-3 ozone profiles."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Mapping

import xarray as xr

from aqdatafusion.contracts import DataRequest, DatasetBundle
from aqdatafusion.data_acquisition.base import AcquisitionError
from aqdatafusion.data_acquisition.generic import RemoteDataSource
from aqdatafusion.utils.opendap import EarthdataOpenDAPClient


SHORT_NAME = "TEMPO_O3PROF_L3"
CONCEPT_ID = "C3685896402-LARC_CLOUD"
QUALITY_VARIABLES = ("eff_cloud_fraction", "solar_zenith_angle", "viewing_zenith_angle")


class TempoO3ProfileDataSource(RemoteDataSource):
    """Search TEMPO O₃ granules and cache regional OpenDAP subsets."""

    source_key = "TEMPO_O3"

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
                "earthaccess is required for TEMPO O₃ acquisition", kind="dependency"
            ) from error
        credentials = configuration.get("credentials", {}).get("earthdata", {})
        if not credentials.get("username") or not credentials.get("password"):
            raise AcquisitionError(
                "Earthdata username and password are required for TEMPO O₃ acquisition",
                kind="credentials",
            )
        os.environ["EARTHDATA_USERNAME"] = str(credentials["username"])
        os.environ["EARTHDATA_PASSWORD"] = str(credentials["password"])
        source = configuration.get("input_data", {}).get("datasets", {}).get(
            self.source_key, {}
        )
        access = source.get("access", {})
        profile_layers = _profile_layers(source)
        try:
            client = EarthdataOpenDAPClient.from_credentials(credentials)
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
                "Earthdata search or authentication failed for TEMPO O₃",
                kind="search", retryable=True, details=str(error)
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
            target = cache_directory / _cache_name(name, url, bbox, profile_layers)
            required_variables = tuple(
                f"ozone_profile_layer_{layer}" for layer in profile_layers
            ) + QUALITY_VARIABLES
            if _valid_cache(target, required_variables):
                files.append(target)
                continue
            temporary = target.with_suffix(target.suffix + ".part")
            try:
                product = client.open_subset(
                    url,
                    collection_concept_id=access.get("concept_id", CONCEPT_ID),
                    group=access.get("product_group", "product"),
                    variables=("ozone_profile",),
                    bounding_box=bbox,
                    load=True,
                )
                support = client.open_subset(
                    url,
                    collection_concept_id=access.get("concept_id", CONCEPT_ID),
                    group=access.get("support_group", "support_data"),
                    variables=("eff_cloud_fraction",),
                    bounding_box=bbox,
                    load=True,
                )
                geolocation = client.open_subset(
                    url,
                    collection_concept_id=access.get("concept_id", CONCEPT_ID),
                    group=access.get("geolocation_group", "geolocation"),
                    variables=("solar_zenith_angle", "viewing_zenith_angle"),
                    bounding_box=bbox,
                    load=True,
                )
                source_layer_count = product.sizes.get("layer", 0)
                if any(layer < 1 or layer > source_layer_count for layer in profile_layers):
                    raise ValueError(
                        f"requested profile layers {profile_layers} are outside "
                        f"the product's 1..{source_layer_count} range"
                    )
                layer_datasets = [
                    product["ozone_profile"].isel(layer=layer - 1, drop=True).rename(
                        f"ozone_profile_layer_{layer}"
                    ).to_dataset()
                    for layer in profile_layers
                ]
                subset = xr.merge(
                    [
                        *layer_datasets,
                        support[["eff_cloud_fraction"]],
                        geolocation[["solar_zenith_angle", "viewing_zenith_angle"]],
                    ],
                    compat="override",
                )
                subset.attrs.update(
                    {
                        **product.attrs,
                        "source_url": url,
                        "source_short_name": SHORT_NAME,
                        "subset_bounding_box": repr(bbox),
                        "profile_layers": profile_layers,
                "profile_layer_indices": [layer - 1 for layer in profile_layers],
                    }
                )
                subset.to_netcdf(temporary)
                temporary.replace(target)
                product.close(); support.close(); geolocation.close()
                files.append(target)
            except Exception as error:
                temporary.unlink(missing_ok=True)
                failures.append({"url": url, "message": str(error)})
        if not files and failures:
            raise AcquisitionError(
                "No TEMPO O₃ OpenDAP subsets could be acquired",
                kind="download", retryable=True, details=failures
            )
        return DatasetBundle(
            self.source_key,
            files,
            {
                "earthdata_short_name": SHORT_NAME,
                "earthdata_concept_id": access.get("concept_id", CONCEPT_ID),
                "profile_layers": profile_layers,
                "granules": len(files),
                "cached_subset_directory": str(cache_directory),
                "cached_subset_files": [str(path) for path in files],
                "request_start_time": request.start_time.isoformat(),
                "request_end_time": request.end_time.isoformat(),
                "warnings": ([{"message": "Some TEMPO O₃ granules failed", "failures": failures}]
                             if failures else []),
            },
            [],
        )

    def cleanup(self, dataset: DatasetBundle) -> None:
        """Remove cached O₃ subsets after their database partition is written."""
        for value in dataset.metadata.get("cached_subset_files", []):
            path = Path(value)
            path.unlink(missing_ok=True)
            path.with_suffix(path.suffix + ".part").unlink(missing_ok=True)


def _cache_name(name: str, url: str, bbox: tuple[float, float, float, float], layers: tuple[int, ...]) -> str:
    key = hashlib.sha256(f"{url}|{bbox}|{layers}".encode()).hexdigest()[:12]
    return f"{key}_{name}"


def _valid_cache(path: Path, required_variables: tuple[str, ...]) -> bool:
    if not path.is_file():
        return False
    try:
        with xr.open_dataset(path) as dataset:
            return all(variable in dataset for variable in required_variables)
    except (OSError, ValueError):
        return False


def _cache_directory(request: DataRequest, configuration: Mapping[str, Any]) -> Path:
    source = configuration.get("input_data", {}).get("datasets", {}).get("TEMPO_O3", {})
    access = source.get("access", {})
    configured_source = configuration.get("filepaths", {}).get("data_sources", {}).get("TEMPO_O3")
    if configured_source:
        return Path(configured_source).expanduser() / str(access.get("cache_subdirectory", ".tmp"))
    return Path(request.metadata.get("temporary_directory") or access.get("temporary_directory", ".tmp"))


def _bounding_box(configuration: Mapping[str, Any]) -> tuple[float, float, float, float]:
    bounds = configuration.get("region", {}).get("bounds", {})
    latitude, longitude = bounds.get("latitude", []), bounds.get("longitude", [])
    if len(latitude) != 2 or len(longitude) != 2:
        raise AcquisitionError("TEMPO O₃ acquisition requires two-number region bounds", kind="configuration")
    return (float(longitude[0]), float(latitude[0]), float(longitude[1]), float(latitude[1]))


def _profile_layers(source: Mapping[str, Any]) -> tuple[int, ...]:
    values = source.get("profile_layers", [24])
    layers = tuple(dict.fromkeys(int(value) for value in values))
    if not layers:
        raise AcquisitionError("TEMPO O₃ profile_layers cannot be empty", kind="configuration")
    return layers


__all__ = ["CONCEPT_ID", "SHORT_NAME", "TempoO3ProfileDataSource"]
