"""Interfaces for acquiring configured air-quality input data."""

from .base import AcquisitionError, DataSource, UnavailableDataSource
from .generic import LocalDataSource, RemoteDataSource
from .airnow import AirNowDataSource
from .openaq import OpenAQDataSource

__all__ = ["AcquisitionError", "DataSource", "UnavailableDataSource", "LocalDataSource", "RemoteDataSource", "AirNowDataSource", "OpenAQDataSource"]
