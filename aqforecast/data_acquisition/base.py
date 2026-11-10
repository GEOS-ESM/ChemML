"""Contracts for data-source acquisition implementations."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from aqforecast.contracts import DataRequest, DatasetBundle


class DataSource(Protocol):
    """A configured source capable of returning a normalized data bundle.

    Concrete sources should perform downloading and source-specific parsing
    here. They should not own workflow orchestration or global configuration.
    """

    source_key: str

    def acquire(
        self,
        request: DataRequest,
        configuration: Mapping[str, Any],
    ) -> DatasetBundle:
        """Acquire data for ``request`` using the resolved configuration."""


__all__ = ["DataSource"]
