"""Validation shared by acquisition adapters and database management."""

from __future__ import annotations

from typing import Any, Mapping, Optional

import pandas as pd


def validate_site_coordinates(
    data: Any,
    source: Mapping[str, Any],
    label: str,
    *,
    site_id_name: Optional[str] = None,
) -> None:
    """Ensure every point-data site has stable, complete coordinates."""

    if not isinstance(data, pd.DataFrame) or data.empty:
        return
    site_id_name = site_id_name or source.get("site_id")
    if not site_id_name:
        return
    coordinate_names = source.get("coordinate_names", {})
    latitude_name = coordinate_names.get("latitude", "lat")
    longitude_name = coordinate_names.get("longitude", "lon")
    required = [str(site_id_name), latitude_name, longitude_name]
    missing = [name for name in required if name not in data.columns]
    if missing:
        raise ValueError(
            f"{label} is missing site coordinate columns: {', '.join(missing)}"
        )
    incomplete = data[required].isna().any(axis=1)
    if incomplete.any():
        raise ValueError(
            f"{label} contains rows with missing site ID or site coordinates"
        )
    tolerance = float(source.get("site_coordinate_tolerance", 1e-6))
    grouped = data[required].groupby(str(site_id_name))[
        [latitude_name, longitude_name]
    ].agg(["min", "max"])
    for site_id, values in grouped.iterrows():
        latitude_delta = float(values[(latitude_name, "max")] - values[(latitude_name, "min")])
        longitude_delta = float(values[(longitude_name, "max")] - values[(longitude_name, "min")])
        if latitude_delta > tolerance or longitude_delta > tolerance:
            raise ValueError(
                f"{label} site {site_id!r} has inconsistent coordinates; "
                f"maximum allowed difference is {tolerance} degrees"
            )


__all__ = ["validate_site_coordinates"]
