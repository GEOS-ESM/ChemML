"""Interfaces for acquiring configured air-quality input data."""

from .base import AcquisitionError, DataSource, UnavailableDataSource
from .generic import LocalDataSource, RemoteDataSource
from .airnow import AirNowDataSource
from .openaq import OpenAQDataSource
from .tropomi import TropomiDataSource
from .viirs import ViirsAodDataSource
from .pace import PaceTraceGasDataSource
from .tempo import TempoNo2DataSource
from .tempo_o3 import TempoO3ProfileDataSource
from .land_cover import LandCoverDataSource

__all__ = ["AcquisitionError", "DataSource", "UnavailableDataSource", "LocalDataSource", "RemoteDataSource", "AirNowDataSource", "OpenAQDataSource", "TropomiDataSource", "ViirsAodDataSource", "PaceTraceGasDataSource", "TempoNo2DataSource", "TempoO3ProfileDataSource", "LandCoverDataSource"]
