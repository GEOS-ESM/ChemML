# ChemML: Chemical Machine Learning for Air Quality Estimation and Forecasting

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![Development Branch](https://img.shields.io/badge/branch-CNPDF__aqforecast__development-orange)](https://github.com/GEOS-ESM/ChemML/tree/CNPDF_aqforecast_development)

ChemML is a developing set of Python codes for high-resolution air quality estimation and forecasting. It combines satellite observations, numerical model outputs, and ground-based measurements using deep learning techniques, and leverages the DeepSensor framework to produce probabilistic forecasts of PM2.5, ozone (O₃), and nitrogen dioxide (NO₂) at fine spatial resolution (e.g., 1 km).

> **Warning:** ChemML is still under development. The configuration system and
> incremental input-data database manager are available. AirNow and OpenAQ
> ground-monitor acquisition and preprocessing, plus the TROPOMI NO₂/O₃ and
> VIIRS VJ219A2 AOD
> satellite ingest, plus PACE OCI trace-gas, TEMPO NO₂/O₃ Profile, and MCD12Q1
> land-cover ingest, are implemented
> source-specific ingests; other source ingest,
> forecasting, and validation
> workflows are being built incrementally.
> Several data-ingest modules, documentation pages, and example notebooks
> remain planned.

## Overview

ChemML integrates multiple data sources to generate accurate, high-resolution air quality forecasts:

- **Satellite Data**: VIIRS MAIAC AOD, TROPOMI NO₂/O₃, PACE NO₂/O₃, MCD12Q1 land cover, GOES-ABI AOD, TEMPO NO₂/O₃ profiles
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
- `aqforecast/utils/regridding.py` provides the shared irregular-point
  regridder for dataset-specific latitude/longitude grids.
- `aqforecast/utils/opendap.py` provides authenticated, bounding-box-subset
  access to NASA Earthdata DAP4 resources through xarray and pydap.
- `aqforecast/data_acquisition/generic.py` provides local and remote acquisition adapter contracts for source-specific ingest implementations.
- `aqforecast/data_acquisition/airnow.py` implements the AirNow historical monitor acquisition adapter.
- `aqforecast/data_acquisition/openaq.py` implements the OpenAQ v3 sensor-based monitor acquisition adapter.
- `aqforecast/data_acquisition/tropomi.py` implements version-2 TROPOMI NO₂ and total-column O₃ Earthdata acquisition.
- `aqforecast/data_acquisition/viirs.py` implements VJ219A2 version-002 VIIRS AOD Earthdata acquisition.
- `aqforecast/data_acquisition/pace.py` implements standard PACE OCI trace-gas Earthdata acquisition.
- `aqforecast/data_acquisition/tempo.py` implements authenticated TEMPO NO₂ DAP4/OpenDAP acquisition with resumable temporary subsets.
- `aqforecast/data_acquisition/tempo_o3.py` implements configurable-layer TEMPO O₃ Profile DAP4/OpenDAP acquisition.
- `aqforecast/data_acquisition/land_cover.py` implements MCD12Q1 yearly Earthdata acquisition with up to two years of source-year fallback.
- `aqforecast/preprocessing/generic.py` provides shared fill-value and basic quality-control preprocessing.
- `aqforecast/preprocessing/airnow.py` implements AirNow unit conversion, quality control, and site-ID standardization.
- `aqforecast/preprocessing/openaq.py` implements OpenAQ unit conversion, shared quality control, sensor reconciliation, and site-ID standardization.
- `aqforecast/preprocessing/tropomi.py` implements TROPOMI quality control, 0.05-degree regridding, and daily aggregation.
- `aqforecast/preprocessing/viirs.py` implements VJ219A2 QA filtering, RSIN geolocation, 0.01-degree regridding, and daily aggregation.
- `aqforecast/preprocessing/pace.py` implements PACE quality filtering, 0.02-degree regridding, and daily aggregation for total-column NO₂/O₃.
- `aqforecast/preprocessing/tempo.py` implements TEMPO quality filtering, native-grid hourly aggregation, and UTC timestamp normalization.
- `aqforecast/preprocessing/tempo_o3.py` implements configurable-layer selection, angle/cloud QC, native-grid hourly aggregation, and UTC timestamp normalization for TEMPO O₃.
- `aqforecast/preprocessing/land_cover.py` implements MCD12Q1 sinusoidal geolocation, configurable `LW`/`QC` filtering, categorical 0.005-degree regridding, and source-year timestamps.
- `aqforecast/data_acquisition/`, `aqforecast/preprocessing/`, `aqforecast/forecasting/`, `aqforecast/validation/`, and `aqforecast/orchestration/` contain the stage interfaces; most source-specific and forecasting implementations remain planned.
- `aqforecast/orchestration/database_update.py` provides the standalone database-update mode.
- `aqforecast/aqforecast.py` contains the `run_aqforecast()` workflow entry
  point; it loads configuration, can optionally check credentials, and exposes
  the explicit database-update mode.
- `tests/` contains pytest regression tests for configuration, database
  management, AirNow/OpenAQ/TROPOMI/VIIRS/PACE/TEMPO/MCD12Q1 ingest, OpenDAP
  access, and shared regridding.
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

For an AirNow or OpenAQ region, the database manager automatically registers
the provider-specific adapter and preprocessor. For example, using the ATL
testing configuration:

```bash
conda activate chemml
python - <<'PY'
from aqforecast.config_management.configuration import load_configuration
from aqforecast.orchestration import run_database_update

configuration = load_configuration(
    "config/testing_config.yaml",
    require_credentials=True,
)
report = run_database_update(
    configuration,
    "2026-08-04T00:00:00Z",
    "2026-08-10T00:00:00Z",
    source_keys=["ground_monitors"],
    conflict_policy="fill_missing",
)
print(report)
PY
```

This requests August 4–9 inclusive. The selected region provider determines
whether the AirNow or OpenAQ adapter is registered. Both providers use the
configured region bounds, standardize monitor identifiers and coordinates,
apply the shared concentration QC limits after unit conversion, and store
monthly point-data CSV partitions. OpenAQ additionally reconciles multiple
sensors at a site and reports competing valid sensor values.

## Documentation

Available and planned documentation is listed in the `docs/` directory. The installation guide, configuration reference, and initial user guide are currently available:

- [Installation Guide](docs/installation.md)
- [Configuration Reference](docs/configuration.md)
- [User Guide](docs/user_guide.md)

Additional documentation pages are planned:

- [Data Sources](docs/data_sources.md) (AirNow, OpenAQ, TROPOMI, VIIRS, PACE, TEMPO NO₂/O₃, and MCD12Q1 currently implemented)
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
  - `pydap >= 3.5` (authenticated DAP4/OpenDAP subsets)
  - `deepsensor`
  - `pytorch >= 2.0` (for GPU acceleration)
  - `pyyaml` (configuration parsing)
  - `requests` (remote data acquisition)
  - `pytest` (regression tests)
  - `yamllint` (YAML validation)

See `environment.yml` for complete dependency list.

## Data Sources

ChemML accesses data from multiple sources:

### Satellite Data (via NASA Earthdata)
- **VIIRS/JPSS2 VJ219A2**: 0.55 micron AOD; version-002 acquisition, QC, regridding, daily aggregation, and database integration are implemented
- **TROPOMI**: high-resolution NO₂ and total column O₃; version-2 acquisition and preprocessing are implemented
- **PACE OCI**: `total_column_no2` and `total_column_o3`; standard trace-gas acquisition, quality control, 0.02-degree regridding, daily aggregation, and database integration are implemented
- **TEMPO NO₂**: `TEMPO_NO2_L3`; authenticated DAP4/OpenDAP regional subsets, resumable caching, moderate quality filtering, native 0.02-degree hourly aggregation, and database integration are implemented
- **TEMPO O₃ Profile**: `TEMPO_O3PROF_L3`; configurable profile-layer selection, authenticated DAP4/OpenDAP regional subsets, cloud/angle QC, native 0.04-degree hourly aggregation, and database integration are implemented
- **MCD12Q1**: yearly `LC_Type1` land cover; Earthdata acquisition with up to two years of fallback, native sinusoidal geolocation, configurable `LW`/`QC` filters, categorical 0.005-degree regridding, and yearly database integration are implemented
- **GOES-ABI**: AOD
- **TEMPO PM2.5**: deferred beyond Phase 2 until April 2027 because the
  product is not expected to be available before then

GEMS and GCAS are also deferred beyond the immediate Phase 2 implementation
scope. GOES-ABI and GEOS-CF remain planned Phase 2 sources.

### Numerical Models
- **[GEOS-CF](https://gmao.gsfc.nasa.gov/gmao-products/geos-cf/)**: NASA's atmospheric composition forecast system

### Ground-Based Observations
- **EPA AirNow**: U.S. air quality monitoring network; acquisition and preprocessing are implemented
- **[OpenAQ](https://openaq.org/)**: Global air quality data platform; acquisition,
  preprocessing, and database integration are implemented for selected regions





