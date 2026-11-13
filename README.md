# ChemML: Chemical Machine Learning for Air Quality Estimation and Forecasting

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![Development Branch](https://img.shields.io/badge/branch-CNPDF__aqforecast__development-orange)](https://github.com/GEOS-ESM/ChemML/tree/CNPDF_aqforecast_development)

ChemML is a developing set of Python codes for high-resolution air quality estimation and forecasting. It combines satellite observations, numerical model outputs, and ground-based measurements using deep learning techniques, and leverages the DeepSensor framework to produce probabilistic forecasts of PM2.5, ozone (O₃), and nitrogen dioxide (NO₂) at fine spatial resolution (e.g., 1 km).

> **Warning:** ChemML is still under development. The configuration system and
> incremental input-data database manager are available, while source-specific
> ingest, forecasting, and validation workflows are being built incrementally.
> Several data-ingest modules, documentation pages, and example notebooks
> remain planned.

## Overview

ChemML integrates multiple data sources to generate accurate, high-resolution air quality forecasts:

- **Satellite Data**: VIIRS MAIAC AOD, TROPOMI NO₂/O₃, PACE NO₂/O₃, GOES-ABI AOD, TEMPO NO₂/O₃ profiles
- **Numerical Models**: GEOS-CF atmospheric composition forecasts
- **Ground Observations**: EPA AirNow and OpenAQ monitoring networks
- **Machine Learning**: [DeepSensor](https://github.com/alan-turing-institute/deepsensor) Conditional Neural Process (ConvNP) architecture

### Key Features

- **Multi-source Data Fusion**: Seamlessly integrates satellite retrievals, model forecasts, and ground measurements
- **High-Resolution Forecasting**: Generates fine resolution (e.g., 1 km) forecasts for user-defined regions
- **Probabilistic Outputs**: Provides forecast uncertainty through ensemble predictions and confidence intervals
- **Flexible Architecture**: Supports both retrospective analysis and near-real-time operational forecasting
- **Comprehensive Validation**: Built-in cross-validation, sensitivity analysis, and performance metrics
- **NCCS Integration**: Optimized for deployment on NASA's High-Performance Computing systems

### Current Repository Components

- `config/` contains the master configuration and component YAML files.
- `aqforecast/config_management/` contains the configuration checker and interactive configuration utility.
- `aqforecast/config_management/credentials.py` manages local credentials and optional remote verification.
- `aqforecast/utils/logging.py` provides shared console/file logging with credential redaction.
- `aqforecast/utils/setup.py` provides a guided first-time setup flow that copies configuration files, collects paths and credentials, creates configured directories, and verifies the result.
- `aqforecast/contracts.py` defines the shared request, result, and workflow-context data contracts.
- `aqforecast/data_management/` provides the incremental partitioned database manager and regenerable per-source catalogs.
- `aqforecast/data_acquisition/generic.py` provides local and remote acquisition adapter contracts for source-specific ingest implementations.
- `aqforecast/preprocessing/generic.py` provides shared fill-value and basic quality-control preprocessing.
- `aqforecast/data_acquisition/`, `aqforecast/preprocessing/`, `aqforecast/forecasting/`, `aqforecast/validation/`, and `aqforecast/orchestration/` contain the initial typed interfaces for future workflow stages; their implementations are not yet complete.
- `aqforecast/orchestration/database_update.py` provides the standalone database-update mode.
- `aqforecast/aqforecast.py` contains the initial `run_aqforecast()` workflow entry point; it loads configuration and can optionally check credentials.
- `tests/` contains the initial pytest regression tests.
- `docs/configuration.md` documents the current configuration structure and ownership boundaries.

## Quick Start

The guided setup below is available after the conda environment is activated;
the forecasting workflow itself remains under development.

### Required Credentials

You will need:
1. NASA Earthdata Login account ([register here](https://urs.earthdata.nasa.gov/users/new))
2. NCCS username and project/account for Discover workflows
3. EPA AirNow API key (optional, for AirNow-based workflows; [request here](https://docs.airnowapi.org/account/request/))
4. OpenAQ API key (optional, for higher rate limits, [request here](https://explore.openaq.org/register))

### Installation

1. Clone the repository:

```bash
git clone https://github.com/GEOS-ESM/ChemML.git
cd ChemML
git checkout CNPDF_aqforecast_development
```

2. Create and activate the conda environment:

```bash
conda env create -f environment.yml
conda activate chemml
```

3. Run the guided first-time setup (recommended):

```bash
python -m aqforecast.utils.setup
```

This copies missing configuration files, prompts for input and output roots,
collects required credentials, creates configured directories, and verifies the
configuration. Use `--verify-remote` to request remote credential checks or
`--prompt-optional-credentials` to enter OpenAQ and AirNow credentials.

For the manual setup alternative and configuration details, see the
[Installation Guide](docs/installation.md).

### Update the input database

After configuration, use `run_database_update()` to check and incrementally
extend the enabled input datasets. The requested interval is interpreted as a
half-open UTC interval. See the [User Guide](docs/user_guide.md#update-the-input-data-database)
for examples, source selection, override behavior, and adapter registration.

## Documentation

Available and planned documentation is listed in the `docs/` directory. The installation guide, configuration reference, and initial user guide are currently available:

- [Installation Guide](docs/installation.md)
- [Configuration Reference](docs/configuration.md)
- [User Guide](docs/user_guide.md)

The following documentation pages are planned:

- [Data Sources](docs/data_sources.md)
- [NCCS Deployment](docs/nccs_deployment.md)
- [API Reference](docs/api_reference.md)

### Example Notebooks

Interactive Jupyter notebooks demonstrating key workflows:

> **Warning:** These workflow-specific notebooks are planned examples and the links below intentionally point to files that have not yet been created. The currently available demonstrations are under `docs/examples/deepsensor_demo/` and `docs/examples/deepsensor_run/`.

- [Data Acquisition](docs/examples/01_data_acquisition.ipynb)
- [Model Training](docs/examples/02_model_training.ipynb)
- [Retrospective Forecasting](docs/examples/03_retrospective_forecast.ipynb)
- [Real-time Forecasting](docs/examples/04_realtime_forecast.ipynb)
- [Validation Analysis](docs/examples/05_validation_analysis.ipynb)

## Software Dependencies

- Python 3.9 or higher
- Key packages:
  - `numpy >= 1.24`
  - `pandas >= 2.0`
  - `xarray >= 2023.1`
  - `netcdf4 >= 1.6`
  - `earthaccess >= 0.8`
  - `deepsensor`
  - `pytorch >= 2.0` (for GPU acceleration)
  - `pyyaml` (configuration parsing)
  - `pytest` (regression tests)

See `environment.yml` for complete dependency list.

## Data Sources

ChemML accesses data from multiple sources:

### Satellite Data (via NASA Earthdata)
- **VIIRS MAIAC**: Aerosol Optical Depth (AOD)
- **TROPOMI**: NO₂ and total column O₃
- **PACE**: NO₂ and O₃
- **GOES-ABI**: AOD
- **TEMPO**: NO₂ and O₃ profiles

### Numerical Models
- **[GEOS-CF](https://gmao.gsfc.nasa.gov/gmao-products/geos-cf/)**: NASA's atmospheric composition forecast system

### Ground-Based Observations
- **EPA AirNow**: U.S. air quality monitoring network
- **[OpenAQ](https://openaq.org/)**: Global air quality data platform





