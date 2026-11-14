"""Source-specific preprocessing for AirNow monitor data."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from aqforecast.contracts import DatasetBundle

POLLUTANTS = ("PM2.5", "PM10", "NO2", "O3", "SO2", "CO")
GASES = {"NO2", "O3", "SO2", "CO"}
UPPER_BOUNDS = {
    "PM2.5": 500.0,
    "PM10": 1000.0,
    "O3": 500.0,
    "NO2": 1000.0,
    "SO2": 1000.0,
    "CO": 50000.0,
}


class AirNowPreprocessor:
    """Convert, quality-control, and standardize an AirNow bundle."""

    source_key = "ground_monitors"

    def preprocess(
        self,
        dataset: DatasetBundle,
        configuration: Mapping[str, Any],
    ) -> DatasetBundle:
        if dataset is None:
            return dataset
        if not isinstance(dataset.data, pd.DataFrame):
            raise TypeError("AirNow preprocessing requires a pandas DataFrame")

        data = dataset.data.copy()
        required = {"aqs_id", "lat", "lon", "time"}
        missing = sorted(required.difference(data.columns))
        if missing:
            raise ValueError(
                "AirNow acquisition output is missing columns: "
                f"{', '.join(missing)}"
            )

        data["site_id"] = data["aqs_id"].astype("string")
        data["time"] = pd.to_datetime(data["time"], utc=True, errors="coerce")
        conversion_counts: dict[str, int] = {}
        invalid_counts: dict[str, int] = {}
        for pollutant in POLLUTANTS:
            if pollutant not in data.columns:
                data[pollutant] = np.nan
            unit_column = f"{pollutant}_unit"
            if unit_column not in data.columns:
                data[unit_column] = None

            values = pd.to_numeric(data[pollutant], errors="coerce")
            units = data[unit_column].astype("string").str.upper()
            ppm = units.eq("PPM") & values.notna() & (pollutant in GASES)
            conversion_counts[pollutant] = int(ppm.sum())
            values = values.where(~ppm, values * 1000.0)

            invalid = (
                values.isna()
                | (values < 0)
                | (values > UPPER_BOUNDS[pollutant])
            )
            invalid_counts[pollutant] = int(invalid.sum())
            data[pollutant] = values.mask(invalid, np.nan)

        final_columns = ["site_id", "lat", "lon", "time", *POLLUTANTS]
        data = (
            data[final_columns]
            .sort_values(["site_id", "time"])
            .reset_index(drop=True)
        )
        metadata = {
            **dataset.metadata,
            "preprocessed": True,
            "timestamps_utc": True,
            "site_column": "site_id",
            "site_id_source_column": "aqs_id",
            "unit_conversion_counts": conversion_counts,
            "invalid_value_counts": invalid_counts,
            "qa_status_retained": False,
            "temporary_unit_columns_removed": True,
        }
        return DatasetBundle(self.source_key, data, metadata)


__all__ = ["AirNowPreprocessor"]
