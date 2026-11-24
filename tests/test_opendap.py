"""Network-free tests for the reusable Earthdata OpenDAP utility."""

import numpy as np
import pytest

from aqdatafusion.utils.opendap import _as_dap4_url, _bounding_indexers


def test_opendap_url_is_normalized_to_dap4():
    assert _as_dap4_url("https://example.test/file.nc") == "dap4://example.test/file.nc"
    assert _as_dap4_url("dap4://example.test/file.nc") == "dap4://example.test/file.nc"
    mapped = _as_dap4_url(
        "https://data.example.test/path/file.nc",
        collection_concept_id="C123-LARC_CLOUD",
    )
    assert mapped == "dap4://opendap.earthdata.nasa.gov/collections/C123-LARC_CLOUD/granules/file.nc"


def test_bounding_box_returns_native_coordinate_slices():
    indexers = _bounding_indexers(
        np.array([32.99, 33.01, 33.03, 35.01]),
        np.array([-85.01, -84.99, -84.97, -82.99]),
        (-85.0, 33.0, -83.0, 35.0),
        "latitude",
        "longitude",
    )
    assert indexers == {"latitude": slice(1, 3), "longitude": slice(1, 3)}


def test_bounding_box_requires_an_intersection():
    with pytest.raises(ValueError, match="does not intersect"):
        _bounding_indexers(
            np.array([0.0, 1.0]), np.array([0.0, 1.0]), (10, 10, 11, 11), "lat", "lon"
        )
