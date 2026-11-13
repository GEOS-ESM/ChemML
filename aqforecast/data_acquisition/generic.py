"""Generic local and remote acquisition adapters.

These adapters deliberately delegate source-specific work to a callable. The
database manager supplies the normalized request, including the requested
interval, variables, and run temporary directory.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from aqforecast.contracts import DataRequest, DatasetBundle


class LocalDataSource:
    """Use a local-filesystem handler for a configured source."""

    def __init__(self, source_key: str, loader: Callable[[DataRequest, Mapping[str, Any]], DatasetBundle]):
        self.source_key = source_key
        self.loader = loader

    def acquire(self, request: DataRequest, configuration: Mapping[str, Any]) -> DatasetBundle:
        return self.loader(request, configuration)


class RemoteDataSource:
    """Use a remote/API handler for a configured source.

    The handler owns Earthdata, AirNow, OpenAQ, or other service-specific
    behavior. Its request metadata includes the manager-created temporary
    directory, which handlers should clean or leave for the manager to clean.
    """

    def __init__(self, source_key: str, downloader: Callable[[DataRequest, Mapping[str, Any]], DatasetBundle]):
        self.source_key = source_key
        self.downloader = downloader

    def acquire(self, request: DataRequest, configuration: Mapping[str, Any]) -> DatasetBundle:
        return self.downloader(request, configuration)


__all__ = ["LocalDataSource", "RemoteDataSource"]
