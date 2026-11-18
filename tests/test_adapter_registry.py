"""Tests for source-adapter registry construction and overrides."""

from aqforecast.data_management import DatabaseManager, SourceRegistry, default_source_registry


class SyntheticSource:
    def __init__(self, logger):
        self.logger = logger


class SyntheticPreprocessor:
    pass


def _configuration(source_key="synthetic"):
    return {
        "input_data": {"datasets": {source_key: {}}},
        "filepaths": {"data_sources": {source_key: "/tmp/source"}},
    }


def test_default_registry_contains_implemented_sources_without_eager_adapters():
    registry = default_source_registry(_configuration())

    assert {"GEOS-CF", "TROPOMI", "VIIRS", "PACE", "TEMPO_NO2", "TEMPO_O3", "land_cover", "GOES-ABI", "ground_monitors"} <= {
        key for key, _ in registry.items()
    }
    assert registry.get("GEOS-CF") is not None


def test_custom_registry_registers_source_specific_adapters():
    registry = SourceRegistry()
    registry.register("synthetic", SyntheticSource, SyntheticPreprocessor)

    manager = DatabaseManager(_configuration(), source_registry=registry)

    assert isinstance(manager.data_sources["synthetic"], SyntheticSource)
    assert isinstance(manager.preprocessors["synthetic"], SyntheticPreprocessor)


def test_explicit_adapter_overrides_are_preserved():
    registry = SourceRegistry()
    registry.register("synthetic", SyntheticSource, SyntheticPreprocessor)
    source = object()
    preprocessor = object()

    manager = DatabaseManager(
        _configuration(),
        source_registry=registry,
        data_sources={"synthetic": source},
        preprocessors={"synthetic": preprocessor},
    )

    assert manager.data_sources["synthetic"] is source
    assert manager.preprocessors["synthetic"] is preprocessor
