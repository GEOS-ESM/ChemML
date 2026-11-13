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


class UnavailableDataSource:
    """Default adapter used until a source-specific ingest is registered."""

    def __init__(self, source_key: str):
        self.source_key = source_key

    def acquire(self, request: DataRequest, configuration: Mapping[str, Any]) -> DatasetBundle:
        raise RuntimeError(
            f"no acquisition adapter is registered for {self.source_key}; "
            "register a local or remote DataSource implementation"
        )


__all__ = ["DataSource", "UnavailableDataSource"]
