# ChemML: Chemical Machine Learning for Air Quality Estimation and Forecasting

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![Development Branch](https://img.shields.io/badge/branch-CNPDF__aqforecast__development-orange)](https://github.com/GEOS-ESM/ChemML/tree/CNPDF_aqforecast_development)

ChemML is a Python package for high-resolution air quality estimation and forecasting that combines satellite observations, numerical model outputs, and ground-based measurements using deep learning techniques. The system leverages the DeepSensor framework to produce probabilistic forecasts of PM2.5, ozone (O₃), and nitrogen dioxide (NO₂) at fine spatial resolution (e.g., 1 km).

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

## Quick Start


### Required Credentials

You will need:
1. NASA Earthdata Login account ([register here](https://urs.earthdata.nasa.gov/users/new))
2. EPA AirNow API key ([request here](https://docs.airnowapi.org/account/request/))
3. OpenAQ API key (optional, for higher rate limits, [request here](https://explore.openaq.org/register))

### Installation

1. Clone the repository:

> git clone https://github.com/GEOS-ESM/ChemML.git cd ChemML git checkout CNPDF_aqforecast_development

2. Create and activate the conda environment:

> conda env create -f environment.yml 
> conda activate chemml

3. Install the package:

> pip install -e .

4. Set up credentials:

> cp config/credentials_template.yaml config/credentials.yaml

Edit `config/credentials.yaml` with your API keys and credentials

5. Set up file path configurations:

> cp config/filepaths_template.yaml config/filepaths.yaml

Edit `config/filepaths.yaml` with the paths to relevant data on your machine

6. Set up regional description(s)

> cp config/regions/region_template.yaml config/regions/my_new_region.yaml

Edit `config/regions/my_new_region.yaml` with information about your region of interest

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- [Installation Guide](docs/installation.md)
- [User Guide](docs/user_guide.md)
- [Configuration Reference](docs/configuration.md)
- [Data Sources](docs/data_sources.md)
- [NCCS Deployment](docs/nccs_deployment.md)
- [API Reference](docs/api_reference.md)

### Example Notebooks

Interactive Jupyter notebooks demonstrating key workflows:

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





