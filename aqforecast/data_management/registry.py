"""Registry of built-in acquisition and preprocessing adapters."""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional


AcquisitionFactory = Callable[[logging.Logger], Any]
PreprocessorFactory = Callable[[], Any]
EnabledPredicate = Callable[[Mapping[str, Any]], bool]


@dataclass(frozen=True)
class SourceRegistration:
    """Factories and optional configuration predicate for one source."""

    acquisition_factory: AcquisitionFactory
    preprocessor_factory: PreprocessorFactory
    enabled_if: EnabledPredicate = lambda configuration: True

    def create_data_source(self, logger: logging.Logger) -> Any:
        return self.acquisition_factory(logger)

    def create_preprocessor(self) -> Any:
        return self.preprocessor_factory()


class SourceRegistry:
    """Mutable source registry used to construct default adapters."""

    def __init__(self) -> None:
        self._registrations: Dict[str, SourceRegistration] = {}

    def register(
        self,
        source_key: str,
        acquisition_factory: AcquisitionFactory,
        preprocessor_factory: PreprocessorFactory,
        *,
        enabled_if: Optional[EnabledPredicate] = None,
    ) -> None:
        if not source_key:
            raise ValueError("source_key must be non-empty")
        self._registrations[source_key] = SourceRegistration(
            acquisition_factory,
            preprocessor_factory,
            enabled_if or (lambda configuration: True),
        )

    def items(self):
        return self._registrations.items()

    def get(self, source_key: str) -> Optional[SourceRegistration]:
        return self._registrations.get(source_key)


def _lazy_acquisition(module_name: str, class_name: str) -> AcquisitionFactory:
    def factory(logger: logging.Logger) -> Any:
        module = importlib.import_module(module_name)
        return getattr(module, class_name)(logger=logger)

    return factory


def _lazy_preprocessor(module_name: str, class_name: str) -> PreprocessorFactory:
    def factory() -> Any:
        module = importlib.import_module(module_name)
        return getattr(module, class_name)()

    return factory


def _ground_monitoring_enabled(configuration: Mapping[str, Any]) -> bool:
    provider = configuration.get("region", {}).get("ground_monitoring", {}).get("provider")
    return str(provider).casefold() in {"airnow", "openaq"}


def _ground_monitoring_acquisition(logger: logging.Logger) -> Any:
    # The predicate selects the provider before this factory is called.
    # Keeping imports here preserves the package's no-download import behavior.
    raise RuntimeError("ground-monitoring provider was not selected")


def _ground_monitoring_preprocessor() -> Any:
    raise RuntimeError("ground-monitoring provider was not selected")


def _airnow_acquisition(logger: logging.Logger) -> Any:
    from aqforecast.data_acquisition.airnow import AirNowDataSource

    return AirNowDataSource(logger=logger)


def _airnow_preprocessor() -> Any:
    from aqforecast.preprocessing.airnow import AirNowPreprocessor

    return AirNowPreprocessor()


def _openaq_acquisition(logger: logging.Logger) -> Any:
    from aqforecast.data_acquisition.openaq import OpenAQDataSource

    return OpenAQDataSource(logger=logger)


def _openaq_preprocessor() -> Any:
    from aqforecast.preprocessing.openaq import OpenAQPreprocessor

    return OpenAQPreprocessor()


def _ground_registration(configuration: Mapping[str, Any]) -> SourceRegistration:
    provider = str(
        configuration.get("region", {}).get("ground_monitoring", {}).get("provider", "")
    ).casefold()
    if provider == "airnow":
        return SourceRegistration(_airnow_acquisition, _airnow_preprocessor)
    if provider == "openaq":
        return SourceRegistration(_openaq_acquisition, _openaq_preprocessor)
    return SourceRegistration(
        _ground_monitoring_acquisition,
        _ground_monitoring_preprocessor,
        _ground_monitoring_enabled,
    )


def default_source_registry(configuration: Mapping[str, Any]) -> SourceRegistry:
    """Return built-in registrations selected for the resolved configuration."""

    registry = SourceRegistry()
    registry.register("ground_monitors", _airnow_acquisition, _airnow_preprocessor)
    registry.register("TROPOMI", _lazy_acquisition("aqforecast.data_acquisition.tropomi", "TropomiDataSource"), _lazy_preprocessor("aqforecast.preprocessing.tropomi", "TropomiPreprocessor"))
    registry.register("VIIRS", _lazy_acquisition("aqforecast.data_acquisition.viirs", "ViirsAodDataSource"), _lazy_preprocessor("aqforecast.preprocessing.viirs", "ViirsAodPreprocessor"))
    registry.register("PACE", _lazy_acquisition("aqforecast.data_acquisition.pace", "PaceTraceGasDataSource"), _lazy_preprocessor("aqforecast.preprocessing.pace", "PaceTraceGasPreprocessor"))
    registry.register("TEMPO_NO2", _lazy_acquisition("aqforecast.data_acquisition.tempo", "TempoNo2DataSource"), _lazy_preprocessor("aqforecast.preprocessing.tempo", "TempoNo2Preprocessor"))
    registry.register("TEMPO_O3", _lazy_acquisition("aqforecast.data_acquisition.tempo_o3", "TempoO3ProfileDataSource"), _lazy_preprocessor("aqforecast.preprocessing.tempo_o3", "TempoO3ProfilePreprocessor"))
    registry.register("land_cover", _lazy_acquisition("aqforecast.data_acquisition.land_cover", "LandCoverDataSource"), _lazy_preprocessor("aqforecast.preprocessing.land_cover", "LandCoverPreprocessor"))
    registry.register("GOES-ABI", _lazy_acquisition("aqforecast.data_acquisition.goes_abi", "GoesAbiAodDataSource"), _lazy_preprocessor("aqforecast.preprocessing.goes_abi", "GoesAbiAodPreprocessor"))
    registry.register("GEOS-CF", _lazy_acquisition("aqforecast.data_acquisition.geos_cf", "GeosCfDataSource"), _lazy_preprocessor("aqforecast.preprocessing.geos_cf", "GeosCfPreprocessor"))
    selected = _ground_registration(configuration)
    registry._registrations["ground_monitors"] = selected
    return registry


__all__ = ["SourceRegistry", "SourceRegistration", "default_source_registry"]
