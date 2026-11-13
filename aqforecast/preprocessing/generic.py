"""Generic preprocessing shared by database updates.

Dataset adapters can subclass this implementation when source-specific quality
control or regridding is needed.
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from aqforecast.contracts import DatasetBundle


class GenericPreprocessor:
    """Apply configuration-independent preprocessing common to all sources."""

    def __init__(self, source_key: str):
        self.source_key = source_key

    def preprocess(
        self,
        dataset: DatasetBundle,
        configuration: Mapping[str, Any],
    ) -> DatasetBundle:
        if dataset is None:
            return dataset

        data = dataset.data
        settings = (
            configuration.get("input_data", {})
            .get("datasets", {})
            .get(self.source_key, {})
        )
        quality_control = settings.get("quality_control", {})
        fill_values = quality_control.get("fill_values", [])

        if isinstance(data, pd.DataFrame):
            data = data.copy()
            coordinate_names = settings.get("coordinate_names", {})
            time_name = coordinate_names.get("time", "time")
            if time_name in data:
                data[time_name] = pd.to_datetime(data[time_name], utc=True)
            if fill_values:
                data = data.replace(fill_values, float("nan"))

            bounds = quality_control.get("bounds", {})
            for variable, limits in bounds.items():
                if variable not in data or not isinstance(limits, (list, tuple)):
                    continue
                if len(limits) > 0:
                    data.loc[data[variable] < limits[0], variable] = float("nan")
                if len(limits) > 1:
                    data.loc[data[variable] > limits[1], variable] = float("nan")
        else:
            for value in fill_values:
                data = data.where(data != value)

        metadata = {
            **dataset.metadata,
            "preprocessed": True,
            "timestamps_utc": True,
        }
        return DatasetBundle(self.source_key, data, metadata)


__all__ = ["GenericPreprocessor"]
