"""Contracts for source-specific and shared preprocessing."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from aqforecast.contracts import DatasetBundle


class DataPreprocessor(Protocol):
    """Transform an acquired dataset into a model-ready dataset."""

    source_key: str

    def preprocess(
        self,
        dataset: DatasetBundle,
        configuration: Mapping[str, Any],
    ) -> DatasetBundle:
        """Apply quality control, regridding, and feature preparation."""


__all__ = ["DataPreprocessor"]
