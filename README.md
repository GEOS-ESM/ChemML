# ChemML: Chemical Machine Learning for Air Quality Estimation and Forecasting

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![Development Branch](https://img.shields.io/badge/branch-CNPDF__aqforecast__development-orange)](https://github.com/GEOS-ESM/ChemML/tree/CNPDF_aqforecast_development)

ChemML is a developing set of Python codes for high-resolution air quality estimation and forecasting. It combines satellite observations, numerical model outputs, and ground-based measurements using deep learning techniques, and leverages the DeepSensor framework to produce probabilistic forecasts of PM2.5, ozone (O₃), and nitrogen dioxide (NO₂) at fine spatial resolution (e.g., 1 km).

> **Warning:** ChemML is still under development. The configuration system, forecasting workflow, and validation system are being built incrementally. Several data-ingest modules, documentation pages, and example notebooks remain planned.

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
- `aqforecast/aqforecast.py` contains the initial `run_aqforecast()` workflow entry point; it currently loads configuration only.
- `tests/` contains the initial pytest regression tests.
- `docs/configuration.md` documents the current configuration structure and ownership boundaries.

## Quick Start

The setup steps below are a development guide and may not yet be fully executable.

### Required Credentials

You will need:
1. NASA Earthdata Login account ([register here](https://urs.earthdata.nasa.gov/users/new))
2. EPA AirNow API key ([request here](https://docs.airnowapi.org/account/request/))
3. OpenAQ API key (optional, for higher rate limits, [request here](https://explore.openaq.org/register))

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

3. Set up credentials:

```bash
cp config/credentials/credentials_template.yaml config/credentials/credentials.yaml
```

Edit `config/credentials/credentials.yaml` with your API keys and credentials

4. Set up file path configurations:

```bash
cp config/filepaths/filepaths_template.yaml config/filepaths/filepaths.yaml
```

Edit `config/filepaths/filepaths.yaml` with the paths to relevant data on your machine

5. Set up regional description(s):

```bash
cp config/regions/region_template.yaml config/regions/my_new_region.yaml
```

Edit `config/regions/my_new_region.yaml` with information about your region of interest

6. Check the selected configuration:

```bash
python aqforecast/config_management/configuration.py config/default_config.yaml
```

Use `--interactive` to prompt for fixable missing or invalid values. The checker currently validates the YAML configuration files but is not yet integrated with the legacy forecasting runner.

The initial AQ-forecast runner can be called from Python:

```python
from aqforecast import run_aqforecast

result = run_aqforecast("config/default_config.yaml")
```

At present, this loads the configuration and returns a status summary. Data access, preprocessing, model training, forecasting, and evaluation will be added later.

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

> **Warning:** These workflow-specific notebooks are planned examples. The currently available demonstrations are under `docs/examples/deepsensor_demo/` and `docs/examples/deepsensor_run/`.

- [Data Acquisition](docs/examples/01_data_acquisition.ipynb)
- [Model Training](docs/examples/02_model_training.ipynb)
- [Retrospective Forecasting](docs/examples/03_retrospective_forecast.ipynb)
- [Real-time Forecasting](docs/examples/04_realtime_forecast.ipynb)
- [Validation Analysis](docs/examples/05_validation_analysis.ipynb)

## Software Dependencies

- Python 3.9 or higher
- Key packages:
  - `numpy >= 1.24`
  - `xarray >= 2023.1`
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





