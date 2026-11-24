"""Contracts for data-source acquisition implementations."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from aqdatafusion.contracts import DataRequest, DatasetBundle


class AcquisitionError(RuntimeError):
    """Actionable source error that can be included in an update report."""

    def __init__(self, message: str, *, kind: str = "source", retryable: bool = False, details: Any = None):
        super().__init__(message)
        self.issue = {
            "kind": kind,
            "message": message,
            "retryable": retryable,
            **({"details": details} if details is not None else {}),
        }


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


__all__ = ["AcquisitionError", "DataSource", "UnavailableDataSource"]
