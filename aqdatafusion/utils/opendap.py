"""Authenticated, subset-oriented access to NASA Earthdata DAP4 datasets."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
import xarray as xr


def earthdata_session(credentials: Mapping[str, Any]):
    """Authenticate with Earthdata and return a requests session for DAP4."""
    try:
        import earthaccess
    except ImportError as error:
        raise RuntimeError("earthaccess is required for Earthdata OpenDAP access") from error
    username = credentials.get("username")
    password = credentials.get("password")
    if not username or not password:
        raise ValueError("Earthdata username and password are required")
    os.environ["EARTHDATA_USERNAME"] = str(username)
    os.environ["EARTHDATA_PASSWORD"] = str(password)
    earthaccess.login(strategy="environment")
    return earthaccess.get_requests_https_session()


@dataclass
class EarthdataOpenDAPClient:
    """Open authenticated NASA DAP4 resources with optional spatial subsets.

    The client uses xarray's pydap backend and Earthaccess's authenticated
    requests session. ``open_subset`` loads only the root coordinate arrays to
    compute index slices, then applies those slices before callers load science
    variables. This is important for products whose coordinates are at the
    root while data variables are stored in NetCDF groups, such as TEMPO L3.
    """

    session: Any
    _coordinate_cache: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = field(
        default_factory=dict, init=False, repr=False
    )

    @classmethod
    def from_credentials(cls, credentials: Mapping[str, Any]) -> "EarthdataOpenDAPClient":
        return cls(earthdata_session(credentials))

    def open_subset(
        self,
        url: str,
        *,
        group: str | None = None,
        variables: Sequence[str] | None = None,
        bounding_box: tuple[float, float, float, float] | None = None,
        collection_concept_id: str | None = None,
        latitude_name: str = "latitude",
        longitude_name: str = "longitude",
        load: bool = False,
        decode_times: bool = False,
    ) -> xr.Dataset:
        """Open a DAP4 group and optionally subset it by lon/lat bounds.

        ``bounding_box`` is ``(west, south, east, north)``. The returned
        dataset has root coordinates assigned even when ``group`` is used.
        Set ``load=True`` to fetch the selected arrays before returning.
        """
        dap4_url = _as_dap4_url(url, collection_concept_id=collection_concept_id)
        cache_key = (latitude_name, longitude_name)
        root_attributes: dict[str, Any] = {}
        if cache_key in self._coordinate_cache:
            latitude, longitude = self._coordinate_cache[cache_key]
            # Coordinates are shared by many granules, but root attributes
            # (especially temporal coverage) are granule-specific.  Read
            # metadata from each root without re-downloading coordinates.
            root = xr.open_dataset(
                dap4_url,
                engine="pydap",
                backend_kwargs={"session": self.session},
                decode_times=decode_times,
            )
            try:
                root_attributes = dict(root.attrs)
            finally:
                root.close()
            coordinate_values = {
                latitude_name: xr.DataArray(latitude, dims=latitude_name),
                longitude_name: xr.DataArray(longitude, dims=longitude_name),
            }
        else:
            root = xr.open_dataset(
                dap4_url,
                engine="pydap",
                backend_kwargs={"session": self.session},
                decode_times=decode_times,
            )
            try:
                coordinate_names = [latitude_name, longitude_name]
                coordinates = root[coordinate_names].load()
                latitude = coordinates[latitude_name].values
                longitude = coordinates[longitude_name].values
                self._coordinate_cache[cache_key] = (latitude, longitude)
                root_attributes = dict(root.attrs)
                coordinate_values = {
                    latitude_name: coordinates[latitude_name],
                    longitude_name: coordinates[longitude_name],
                }
            finally:
                root.close()
        indexers = _bounding_indexers(
            coordinate_values[latitude_name].values,
            coordinate_values[longitude_name].values,
            bounding_box,
            latitude_name,
            longitude_name,
        )

        dataset = xr.open_dataset(
            dap4_url,
            engine="pydap",
            group=group,
            backend_kwargs={"session": self.session},
            decode_times=decode_times,
        )
        if variables is not None:
            dataset = dataset[list(variables)]
        dataset = dataset.isel(indexers)
        dataset.attrs = {**root_attributes, **dataset.attrs}
        dataset = dataset.assign_coords(
            {
                name: values.isel({name: indexers[name]}) if name in indexers else values
                for name, values in coordinate_values.items()
                if name in indexers or name in dataset.dims
            }
        )
        if load:
            dataset.load()
        return dataset


def _as_dap4_url(url: str, *, collection_concept_id: str | None = None) -> str:
    if url.startswith("dap4://"):
        return url
    if collection_concept_id and "opendap.earthdata.nasa.gov" not in url:
        filename = url.rstrip("/").rsplit("/", 1)[-1]
        url = (
            "https://opendap.earthdata.nasa.gov/collections/"
            f"{collection_concept_id}/granules/{filename}"
        )
    if url.startswith("https://"):
        return "dap4://" + url[len("https://") :]
    if url.startswith("http://"):
        return "dap4://" + url[len("http://") :]
    raise ValueError("Earthdata OpenDAP URL must use http(s) or dap4 scheme")


def _bounding_indexers(
    latitude: np.ndarray,
    longitude: np.ndarray,
    bounding_box: tuple[float, float, float, float] | None,
    latitude_name: str,
    longitude_name: str,
) -> dict[str, slice]:
    if bounding_box is None:
        return {
            latitude_name: slice(None),
            longitude_name: slice(None),
        }
    west, south, east, north = map(float, bounding_box)
    lat_indices = np.flatnonzero((latitude >= south) & (latitude < north))
    lon_indices = np.flatnonzero((longitude >= west) & (longitude < east))
    if not len(lat_indices) or not len(lon_indices):
        raise ValueError("OpenDAP bounding box does not intersect dataset coordinates")
    return {
        latitude_name: slice(int(lat_indices[0]), int(lat_indices[-1]) + 1),
        longitude_name: slice(int(lon_indices[0]), int(lon_indices[-1]) + 1),
    }


__all__ = ["EarthdataOpenDAPClient", "earthdata_session"]
