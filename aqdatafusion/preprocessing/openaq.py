"""OpenAQ normalization, sensor reconciliation, and quality control."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from aqdatafusion.contracts import DatasetBundle

POLLUTANTS = ("PM2.5", "PM10", "NO2", "O3", "SO2", "CO")
GASES = {"NO2", "O3", "SO2", "CO"}
MOLECULAR_WEIGHTS = {"NO2": 46.01, "O3": 48.00, "SO2": 64.07, "CO": 28.01}
UGM3_TO_PPB = {pollutant: 24.45 / weight for pollutant, weight in MOLECULAR_WEIGHTS.items()}


def _unit(value: Any) -> str:
    return str(value or "").strip().casefold().replace("μ", "µ").replace("³", "3")


class OpenAQPreprocessor:
    """Convert OpenAQ long measurements to ChemML's wide point-data schema."""

    source_key = "ground_monitors"

    def preprocess(self, dataset: DatasetBundle, configuration: Mapping[str, Any]) -> DatasetBundle:
        if dataset is None:
            return dataset
        if not isinstance(dataset.data, pd.DataFrame):
            raise TypeError("OpenAQ preprocessing requires a pandas DataFrame")
        required = {"site_id", "lat", "lon", "time", "pollutant", "value", "unit", "sensor_id"}
        missing = sorted(required.difference(dataset.data.columns))
        if missing:
            raise ValueError("OpenAQ acquisition output is missing columns: " + ", ".join(missing))

        data = dataset.data.copy()
        data["site_id"] = data["site_id"].astype("string")
        data["time"] = pd.to_datetime(data["time"], utc=True, errors="coerce")
        data["pollutant"] = data["pollutant"].map(lambda value: str(value).upper())
        data["value"] = pd.to_numeric(data["value"], errors="coerce")
        data["sensor_id"] = pd.to_numeric(data["sensor_id"], errors="coerce")
        bounds = (
            configuration.get("input_data", {}).get("datasets", {}).get(self.source_key, {})
            .get("quality_control", {}).get("bounds", {})
        )
        conversion_counts = {pollutant: 0 for pollutant in POLLUTANTS}
        invalid_counts = {pollutant: 0 for pollutant in POLLUTANTS}
        converted: list[float] = []
        for row in data.itertuples(index=False):
            pollutant, value, unit = row.pollutant, row.value, _unit(row.unit)
            if pd.notna(value) and pollutant in GASES:
                if unit == "ppm":
                    value *= 1000.0
                    conversion_counts[pollutant] += 1
                elif unit in {"µg/m3", "µg/m^3", "ug/m3", "ug/m^3"}:
                    value *= UGM3_TO_PPB[pollutant]
                    conversion_counts[pollutant] += 1
                elif unit not in {"ppb", ""}:
                    value = np.nan
            elif pd.notna(value) and pollutant in {"PM2.5", "PM10"}:
                if unit not in {"µg/m3", "µg/m^3", "ug/m3", "ug/m^3"}:
                    value = np.nan
            limits = bounds.get(pollutant, [0, None])
            invalid = pd.isna(value)
            if isinstance(limits, (list, tuple)) and limits and not pd.isna(value):
                if limits[0] is not None:
                    invalid = invalid or value < float(limits[0])
                if len(limits) > 1 and limits[1] is not None:
                    invalid = invalid or value > float(limits[1])
            if invalid:
                invalid_counts[pollutant] = invalid_counts.get(pollutant, 0) + 1
                value = np.nan
            converted.append(value)
        data["value"] = converted
        data = data.dropna(subset=["site_id", "lat", "lon", "time"])

        warnings: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        identity = ["site_id", "lat", "lon", "time", "pollutant"]
        for key, group in data.groupby(identity, dropna=False, sort=False):
            valid = group.dropna(subset=["value"])
            if valid.empty:
                value = np.nan
            elif len(valid) == 1 or valid["value"].nunique(dropna=True) == 1:
                value = float(valid.iloc[0]["value"])
            else:
                highest = valid.sort_values("sensor_id").iloc[-1]
                value = float(highest["value"])
                warnings.append({
                    "kind": "competing_sensor_values",
                    "message": "OpenAQ sensors provided different valid values; highest sensor ID selected.",
                    "retryable": False,
                    "site_id": str(key[0]), "pollutant": str(key[4]),
                    "time": pd.Timestamp(key[3]).isoformat(),
                    "sensor_ids": [int(sensor_id) for sensor_id in valid["sensor_id"].tolist()],
                    "values": [float(sensor_value) for sensor_value in valid["value"].tolist()],
                    "selected_sensor_id": int(highest["sensor_id"]),
                })
            rows.append({"site_id": key[0], "lat": key[1], "lon": key[2], "time": key[3], "pollutant": key[4], "value": value})

        base_columns = ["site_id", "lat", "lon", "time"]
        wide = pd.DataFrame(rows)
        if wide.empty:
            wide = pd.DataFrame(columns=base_columns + list(POLLUTANTS))
        else:
            wide = wide.pivot_table(index=base_columns, columns="pollutant", values="value", aggfunc="first").reset_index()
            wide.columns.name = None
            for pollutant in POLLUTANTS:
                if pollutant not in wide.columns:
                    wide[pollutant] = np.nan
            wide = wide[base_columns + list(POLLUTANTS)].sort_values(["site_id", "time"]).reset_index(drop=True)
        metadata = {
            **dataset.metadata,
            "preprocessed": True,
            "timestamps_utc": True,
            "site_column": "site_id",
            "canonical_units": {"PM2.5": "µg/m3", "PM10": "µg/m3", **{pollutant: "ppb" for pollutant in GASES}},
            "unit_conversion_counts": conversion_counts,
            "invalid_value_counts": invalid_counts,
            "sensor_reconciliation": "fill_nan_then_highest_sensor_id_on_conflict",
            "competing_sensor_warning_count": len(warnings),
        }
        if warnings:
            metadata["warnings"] = warnings
        return DatasetBundle(self.source_key, wide, metadata, list(dataset.errors))


__all__ = ["OpenAQPreprocessor"]
