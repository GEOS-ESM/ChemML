# ChemML

ChemML is a developing air-quality estimation and data-fusion workflow. It is
designed to combine satellite observations, numerical model output, and ground
monitoring data with DeepSensor-based machine learning to produce probabilistic
PM2.5, ozone, and NO₂ forecasts at user-defined spatial resolution.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)

## Current status

The configuration system, partitioned input-data database, integrity checks,
incremental updates, operational reports, and scheduled-update entry point are
implemented. AirNow, OpenAQ, VIIRS, TROPOMI, PACE, TEMPO NO₂/O₃ Profiles,
MCD12Q1 land cover, and GOES-ABI ingestion paths are implemented. GEOS-CF
ingestion is developed but still requires local/NCCS end-to-end validation.

Forecasting, validation, and DeepSensor workflow integration remain under
development. See [PROJECT.md](PROJECT.md) for the roadmap and
[CHANGELOG.md](CHANGELOG.md) for substantive changes.

## Capabilities

- Configurable regional input-data acquisition and preprocessing.
- CSV/NetCDF partitioned databases with incremental merging and per-source
  catalogs.
- Source-specific quality control, timestamp normalization, regridding, and
  coordinate validation.
- Explicit time-bounded and rolling database updates.
- Human-readable per-run operational reports with configurable retention.
- Conda-based scheduler entry point suitable for cron or NCCS adaptation.
- Modular acquisition, preprocessing, forecasting, validation, and orchestration
  interfaces for future workflow stages.

## Quick start

Create the development environment and run the guided setup:

```bash
git clone https://github.com/GEOS-ESM/ChemML.git
cd ChemML
git checkout main
conda env create --file environment.yml
conda activate chemml
python -m aqdatafusion.utils.setup
```

The setup flow creates or copies configuration files, collects credentials and
paths, creates configured directories, and validates the result. See the
[Installation Guide](docs/installation.md) for manual setup.

Validate a configuration with:

```bash
python aqdatafusion/config_management/configuration.py config/default_config.yaml
```

Run a bounded database update from Python:

```python
from aqdatafusion import run_aqdatafusion

result = run_aqdatafusion(
    "config/default_config.yaml",
    mode="database_update",
    start_time="2026-08-04T00:00:00Z",
    end_time="2026-08-08T00:00:00Z",
    require_credentials=True,
)
print(result["status"])
```

Run the configured rolling update:

```python
result = run_aqdatafusion(
    "config/default_config.yaml",
    mode="incremental_database_update",
    require_credentials=True,
)
print(result["report"])
```

For scheduler use, make the included script executable and run it manually
before adding it to cron or an NCCS scheduler:

```bash
chmod +x scripts/update_database_incremental.sh
scripts/update_database_incremental.sh
```

Edit the `CONFIG_PATH` line in that script to use a different master
configuration. The script activates `chemml`, enables credential checking, and
returns a nonzero status when the update fails.

## Documentation

- [Installation and first-time setup](docs/installation.md)
- [Configuration reference](docs/configuration.md)
- [User guide](docs/user_guide.md)
- [Data-source reference](docs/data_sources.md)
- [Agent and contributor guidance](AGENTS.md)
- [Project roadmap](PROJECT.md)
- [Change history](CHANGELOG.md)

The following resources are planned and intentionally linked here so they are
not forgotten; the files do not yet exist:

- [NCCS deployment reference](docs/nccs_deployment.md) — planned; file to be created.
- [API reference](docs/api_reference.md) — planned; file to be created.
- [Data-acquisition example](docs/examples/01_data_acquisition.ipynb) — planned; file to be created.
- [Model-training example](docs/examples/02_model_training.ipynb) — planned; file to be created.
- [Retrospective forecast example](docs/examples/03_retrospective_forecast.ipynb) — planned; file to be created.
- [Real-time forecast example](docs/examples/04_realtime_forecast.ipynb) — planned; file to be created.
- [Validation example](docs/examples/05_validation_analysis.ipynb) — planned; file to be created.

Existing demonstrations are under `docs/examples/deepsensor_demo/` and
`docs/examples/deepsensor_run/`.

## Data sources

The current ingest scope includes AirNow and OpenAQ ground observations;
TROPOMI, VIIRS, PACE, TEMPO, MCD12Q1, and GOES-ABI satellite products; and
GEOS-CF numerical model data. GEMS, GCAS, and TEMPO PM2.5 remain deferred.
Access methods, preprocessing, and configurable defaults are summarized in
the [data-source reference](docs/data_sources.md).

## Development

Activate `chemml` before running Python commands. The network-free regression
suite can be run with:

```bash
python -m pytest tests/
```

See `AGENTS.md` for development conventions and `CONTRIBUTING.md` for
contribution requirements.
