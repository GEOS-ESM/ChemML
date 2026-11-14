"""Interfaces for acquiring configured air-quality input data."""

from .base import DataSource, UnavailableDataSource
from .generic import LocalDataSource, RemoteDataSource
from .airnow import AirNowDataSource

__all__ = ["DataSource", "UnavailableDataSource", "LocalDataSource", "RemoteDataSource", "AirNowDataSource"]
