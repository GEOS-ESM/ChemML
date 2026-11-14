# ChemML Project Development Plan

**Repository**: <https://github.com/GEOS-ESM/ChemML.git>

**Development branch**: `CNPDF_aqforecast_development`

## Project Overview

ChemML is a high-resolution air-quality forecasting system that combines satellite observations, numerical model outputs, and ground-based measurements using deep learning. The system is designed to produce probabilistic forecasts of PM2.5, O₃, and NO₂ at fine spatial resolution (for example, 1 km) over user-defined regions.

### Project Goals

1. **Primary goal**: Develop an operational air-quality forecasting system using machine learning.
2. **Secondary goals**:
   - Integrate multiple NASA Earth observation datasets.
   - Provide uncertainty quantification through ensemble forecasting.
   - Enable both retrospective analysis and real-time forecasting.
   - Deploy on NASA NCCS infrastructure.
   - Support scientific research and operational applications.

### Target Capabilities

- **Spatial resolution**: 1 km
- **Forecast horizon**: 72 hours, with an option for up to 120 hours
- **Update frequency**: Daily
- **Pollutants**: PM2.5, O₃, and NO₂
- **Uncertainty**: 90% confidence intervals
- **Validation**: Comprehensive metrics with cross-validation

## Development Phases

### Phase 1: Foundation — Complete

**Objective**: Establish project infrastructure and core utilities.

**Tasks**:

- [x] Define project structure.
- [x] Create configuration system design.
- [x] Set up GitHub repository and branch.
- [x] Define package structure and interfaces.
  - [x] Add the configuration-management package.
  - [x] Add shared utility modules, including logging.
  - [x] Add data-acquisition interfaces and package scaffold.
  - [x] Add preprocessing interfaces and package scaffold.
  - [x] Add forecasting-model interfaces and package scaffold.
  - [x] Add validation interfaces and package scaffold.
  - [x] Add workflow-orchestration interfaces and package scaffold.
- [x] Define configuration file layout and ownership.
- [x] Implement configuration validation/checking utility.
- [x] Implement a runtime loader that resolves and merges component configurations.
- [x] Integrate configuration loading and checking with the new forecasting runner.
- [x] Create `config/credentials/credentials_template.yaml`.
- [x] Create `config/filepaths/filepaths_template.yaml`.
- [x] Create `config/regions/region_template.yaml`.
- [x] Implement credentials management and optional remote verification.
- [x] Set up logging utilities.
- [x] Create database manager framework with partitioned storage, completeness checks, incremental merging, and catalog regeneration.
- [x] Implement a startup/install function that guides users through creating configuration files, entering credentials, creating configured directories, and verifying the setup.
- [x] Write initial configuration documentation.
- [x] Add an initial configuration regression test.
- [x] Create the initial AQ-forecast runner skeleton that loads configuration and returns run status.
- [x] Add credential-management tests.

**Deliverables**:

- ~~Package skeleton with all directories and shared stage interfaces.~~
- ~~Configuration file templates.~~
- ~~Credentials management system.~~
- ~~Basic logging infrastructure.~~
- ~~Database manager with incremental update support.~~
- ~~A startup/install function for first-time configuration and credential setup.~~
- ~~First draft of the Installation Guide.~~
- ~~First draft of the Configuration Reference.~~
- ~~First draft of the User Guide.~~

**Current status**:

- Project objectives and high-level structure defined.
- Configuration file layout, templates, validation utility, documentation, and regression tests are in place.
- Runtime configuration loading, credential management, and the initial runner integration are in place.
- The guided `aqforecast.utils.setup_aqforecast()` setup flow copies missing configuration files, collects paths and credentials, creates configured directories, and verifies the completed setup.
- Package directories and shared data contracts for acquisition, preprocessing,
  forecasting, validation, orchestration, and database management are in place.
- The database manager can inspect partitioned CSV/NetCDF files, identify
  missing expected timestamps, merge acquired data with `fill_missing`
  semantics, use per-run temporary staging, and regenerate per-source JSON
  catalogs.
- Generic local/remote acquisition adapters and shared preprocessing are in
  place. AirNow is the first complete source-specific implementation, with
  acquisition, preprocessing, retries, QC, AQS site-ID handling, and database
  registration; other dataset-specific download, regridding, and source
  adapters remain future work.
- Model execution, forecasting, and evaluation remain to be implemented.

### Phase 2: Data Acquisition — In Progress

**Objective**: Acquire, quality-control, standardize, and maintain local
databases for all configured input sources.

**Tasks**:

- [ ] Implement satellite data acquisition:
  - [ ] VIIRS MAIAC AOD.
  - [ ] TROPOMI NO₂ and O₃.
  - [ ] PACE NO₂ and O₃.
  - [ ] GOES-ABI AOD.
  - [ ] TEMPO NO₂ and O₃ profiles.
- [ ] Implement GEOS-CF model data acquisition.
- [ ] Implement ground-station data acquisition:
  - [x] EPA AirNow API integration.
  - [ ] OpenAQ API integration.
- [ ] Implement data quality control for all configured sources.
- [x] Implement AirNow source-specific quality control and PPM-to-PPB conversion.
- [ ] Convert each source from its original format into the configured
  standardized database format during acquisition.
- [ ] Apply source-specific fill-value handling, bounds checks, quality flags,
  cloud filters, and other quality-control rules.
- [ ] Subset data to the requested region, period, variables, and desired
  spatial and temporal resolution wherever possible at ingest time.
- [ ] Regrid and aggregate acquired data according to the input-data
  configuration before writing database partitions.
- [ ] Implement post-update database integrity verification, including
  timestamp completeness, required variables, coordinate/grid structure,
  duplicate detection, partition/catalog consistency, and explicit reporting
  of any remaining gaps.
- [ ] Modify `run_aqforecast()` to expose a database-update mode now that a
  complete source-specific ingestion path exists.
- [ ] Add generic site-coordinate verification at both acquisition-output and
  database-management boundaries, using configured site IDs and tolerances
  rather than duplicating the checks in each dataset adapter.
- [ ] Replace the hard-coded provider-to-adapter mapping in `DatabaseManager`
  with a configurable or registry-based source-adapter mechanism.
- [ ] Extend the generic acquisition contract so source adapters can pass
  structured API/file error messages to the logging and update-report systems.
- [ ] Add an end-to-end database-update test covering acquisition,
  preprocessing, merging, partition writing, and catalog generation.
- [ ] Handle empty source files, including CSV files containing only headers,
  as empty databases or explicit, actionable input errors.
- [ ] Create data download scripts.
- [ ] Implement data-acquisition modules for the remaining configured sources.
- [x] Add the AirNow source-specific acquisition and preprocessing adapters to
  the database manager.
- [x] Add AirNow source-specific tests using mocked API responses and
  representative raw-data fixtures.
- [x] Add database-manager tests for missing intervals, site identity,
  coordinate consistency, empty databases, and timestamp normalization.
- [ ] Add broader tests for partial updates, retries/failures, and output
  database fixtures across all sources.
- [ ] Keep `config/inputs/input_data_config.yaml` aligned with the settings required to download and preprocess each data source as ingest codes are developed.
- [ ] Test data acquisition on NCCS.
- [ ] Schedule ongoing data ingest:
  - [ ] Create scripts to update the database in NCCS on a regular (daily) cadence.
  - [ ] Schedule scripts to run automatically using `cron`.
  - [ ] Verify that data are being ingested as intended.

Land-cover data are part of this acquisition workflow, but require a special
time-offset provision. The acquisition process must support requesting a
reference period from an earlier source period (for example, using land-cover
data from the preceding year) rather than assuming that all sources cover the
same dates.

**Deliverables**:

- Functional data acquisition modules for all sources.
- Data quality control procedures.
- Download scripts for historical data.
- Unit tests for data modules.
- Network-free adapter tests with mocked API/filesystem responses.
- Representative raw-data and standardized database fixtures.
- Tests for partial updates, retry/failure behavior, and remaining-gap
  reporting.
- Automated database updating script.
- Database integrity verification.
- Documentation for data sources.

**Dependencies**:

- Phase 1 completion.
- NASA Earthdata credentials.
- AirNow and OpenAQ API keys.
- NCCS access.

### Phase 3: Data Conditioning — Planned

**Objective**: Convert the standardized acquired databases into
DeepSensor-compatible data structures and apply DeepSensor normalization.

**Tasks**:

- [ ] Convert standardized database records into DeepSensor-compatible
  structures.
- [ ] Configure DeepSensor coordinate names and data-processor inputs.
- [ ] Apply normalization using DeepSensor functions.
- [ ] Create data-conditioning scripts.
- [ ] Optimize data conditioning for NCCS performance.

**Deliverables**:

- DeepSensor-compatible data-preparation modules.
- DeepSensor normalization configuration and workflow.
- Data-conditioning scripts.
- Unit tests.
- Documentation.

**Dependencies**:

- Phase 2 completion.
- Sample data from all sources.

### Phase 4: Forecasting Model — Planned

**Objective**: Implement a DeepSensor-based forecasting system.

**Tasks**:

- [ ] Create a DeepSensor wrapper for ConvNP.
- [ ] Implement the training pipeline.
- [ ] Implement a cross-validation framework.
- [ ] Create the DeepSensor forecasting system.
- [ ] Implement the inference pipeline.
- [ ] Integrate the future forecasting stages with `run_aqforecast()`.
- [ ] Update `config/deepsensor/deepsensor_config.yaml` once the Phase 4 DeepSensor implementation defines the required configuration settings.
- [ ] Keep `config/aqforecast/aqforecast_config.yaml` up to date as the forecasting model and its required settings are developed.
- [ ] Optimize GPU training on NCCS.
- [ ] Create model-training scripts.
- [ ] Develop a model-versioning system.

**Deliverables**:

- DeepSensor wrapper module.
- Training pipeline with cross-validation.
- Ensemble forecasting implementation.
- Inference pipeline for 72-hour forecasts.
- Training scripts for NCCS.
- Model checkpointing and versioning.
- Unit tests.
- Documentation.

**Dependencies**:

- Phase 3 completion.
- Preprocessed training data.
- NCCS GPU access.

### Phase 5: Validation — Planned

**Objective**: Implement a comprehensive validation framework.

**Tasks**:

- [ ] Implement core metrics: bias, RMSE, and correlation.
- [ ] Create a stratification framework:
  - [ ] By monitoring site.
  - [ ] By forecast lead time.
  - [ ] By hour of day.
  - [ ] By region.
- [ ] Implement confidence-interval coverage analysis.
- [ ] Create sensitivity analysis for data outages.
- [ ] Keep `config/validation/validation_config.yaml` up to date as the validation system and its supported analyses are developed.
- [ ] Implement visualization tools.
- [ ] Create a validation reporting system.
- [ ] Develop validation scripts.

**Deliverables**:

- Validation metrics module.
- Stratification framework.
- Sensitivity analysis tools.
- Visualization functions.
- Automated reporting system.
- Validation scripts.
- Unit tests.
- Documentation.

**Dependencies**:

- Phase 4 completion.
- Forecast outputs.
- Ground-truth data.

### Phase 6: Orchestration — Planned

**Objective**: Implement workflow orchestration for operations.

**Tasks**:

- [ ] Create a retrospective-mode workflow.
- [ ] Implement a real-time-mode workflow.
- [ ] Develop a scheduling system for daily updates.
- [ ] Create NCCS job-submission scripts.
- [ ] Implement automated validation of previous forecasts.
- [ ] Set up monitoring and alerting.
- [ ] Create operational documentation.
- [ ] Test end-to-end workflows.

**Deliverables**:

- Retrospective workflow implementation.
- Real-time workflow with scheduling.
- NCCS deployment scripts.
- Automated validation workflow.
- Monitoring system.
- Operational documentation.
- Integration tests.

**Dependencies**:

- Phases 1–5 completion.
- NCCS production environment setup.

### Phase 7: Documentation and Testing — Planned

**Objective**: Complete documentation and comprehensive testing.

**Tasks**:

- [x] Create `docs/installation.md`.
- [x] Create `docs/user_guide.md`.
- [x] Create `docs/configuration.md`.
- [ ] Create `docs/data_sources.md`.
- [ ] Create `docs/nccs_deployment.md`.
- [ ] Create `docs/api_reference.md`.
- [ ] Develop example Jupyter notebooks.
- [ ] Create `docs/examples/01_data_acquisition.ipynb`.
- [ ] Create `docs/examples/02_model_training.ipynb`.
- [ ] Create `docs/examples/03_retrospective_forecast.ipynb`.
- [ ] Create `docs/examples/04_realtime_forecast.ipynb`.
- [ ] Create `docs/examples/05_validation_analysis.ipynb`.
- [x] Set up the initial pytest test structure.
- [ ] Complete unit-test coverage.
- [ ] Add database-manager regression and integration tests using representative CSV and NetCDF fixtures.
- [ ] Perform integration testing.
- [ ] Conduct a security review.
- [ ] Create tutorial videos and materials.
- [ ] Prepare for the initial release.

**Deliverables**:

- Complete documentation suite.
- Example notebooks for all workflows.
- Full test coverage.
- Security audit report.
- NCCS deployment guide.
- Tutorial materials.
- Version 0.1.0 release.

**Dependencies**:

- Phases 1–6 completion.

## Current Development Status

### Completed Items

- ✅ Project structure design.
- ✅ Development roadmap.
- ✅ GitHub repository setup.
- ✅ Configuration file layout and templates.
- ✅ Configuration validation utility.
- ✅ Configuration reference documentation.
- ✅ Initial configuration regression test.
- ✅ Initial AQ-forecast runner skeleton.
- ✅ Runtime configuration loader and runner integration.
- ✅ Credential management with optional remote verification.
- ✅ Credential-management tests.
- ✅ Shared logging utility with credential redaction.
- ✅ Incremental partitioned database manager with UTC completeness checking.
- ✅ Per-source catalog generation and update reporting.
- ✅ Standalone database-update orchestration mode.
- ✅ AirNow acquisition adapter using the verified historical API query format.
- ✅ AirNow preprocessing with PPM-to-PPB conversion, QC, and AQS-based site IDs.
- ✅ Site-aware database merging, coordinate validation, gap detection, and
  empty-database initialization.

AirNow is currently the only source for which acquisition and preprocessing
are complete. All other configured satellite, model, and ground-data sources
remain planned or require further implementation and integration testing.

### In Progress

- 🚧 Dataset-specific data acquisition and preprocessing implementations beyond
  AirNow, plus broader database integration fixtures.
- 🚧 Forecasting and validation workflow implementation.

### Upcoming

- Source-specific acquisition adapters for satellite, model, and remaining
  ground-data sources.
- Dataset-specific quality control, regridding, and aggregation.
- Integration fixtures and broader database-manager coverage.

## Technical Decisions

### Architecture Decisions

1. **Database organization**: Monthly NetCDF or CSV files organized by region and data source.
   - **Rationale**: Balances file size, access speed, and incremental updates.
2. **Machine-learning framework**: DeepSensor with a ConvNP architecture.
   - **Rationale**: Designed for spatiotemporal data fusion with uncertainty quantification.
3. **Spatial resolution**: 1 km grid.
   - **Rationale**: Balances computational cost with urban-scale resolution needs.
4. **Forecast horizon**: 72 hours, with a 120-hour option.
   - **Rationale**: Matches GEOS-CF availability and operational needs.

### Technology Stack

- **Language**: Python 3.9+
- **Core libraries**: NumPy, pandas, xarray, and PyTorch
- **Data access**: earthaccess
- **Ground-data access**: AirNow API through `requests`
- **ML framework**: DeepSensor
- **Developer tools**: pytest, yamllint, Black, and Flake8
- **Deployment**: NASA NCCS (Discover/ADAPT)
- **Version control**: Git (GitHub)

## Data Sources Summary

### Satellite Data

| Source | Product | Variables | Resolution | Latency |
| --- | --- | --- | --- | --- |
| VIIRS MAIAC | VNP09GA | AOD | 1 km | 1–2 days |
| TROPOMI | S5P_L2 | NO₂, O₃ | 7 km | 1–2 days |
| PACE | PACE_OCI_L2 | NO₂, O₃ | 1 km | 1–2 days |
| GOES-ABI | ABI-L2-AOD | AOD | 2 km | 1 hour |
| TEMPO | TEMPO_L2 | NO₂, O₃ profile | 2–8 km | 1 hour |

### Model Data

| Source | Variables | Resolution | Forecast horizon |
| --- | --- | --- | --- |
| GEOS-CF | PM2.5, O₃, NO₂, meteorology | 25 km | 120 hours |

### Ground Data

| Source | Variables | Temporal resolution | Coverage |
| --- | --- | --- | --- |
| AirNow | PM2.5, PM10, NO₂, O₃, SO₂, CO | Hourly | U.S. |
| OpenAQ | PM2.5, O₃, NO₂ | Hourly | Global |

## Resource Requirements

### Storage (NCCS)

- Historical data: approximately 500 GB per region per year.
- Model weights: approximately 1 GB per trained model.
- Forecast outputs: approximately 10 GB per region per month.
- **Total estimated**: 1–2 TB per region.

### Compute (NCCS)

- **Training**: One GPU node, 24 hours per model.
- **Daily forecasting**: One CPU node, 2 hours per region.
- **Data processing**: One CPU node, 4 hours per day.

## Risk Assessment

### Technical Risks

| Risk | Probability | Impact | Mitigation |
| --- | --- | --- | --- |
| Data availability issues | Medium | High | Implement fallback data sources and robust error handling. |
| Model performance below expectations | Medium | High | Use extensive validation, ensemble methods, and iterative improvement. |
| NCCS resource constraints | Low | Medium | Optimize code and request adequate allocation. |
| DeepSensor integration challenges | Medium | Medium | Prototype early and use community support. |

### Operational Risks

| Risk | Probability | Impact | Mitigation |
| --- | --- | --- | --- |
| API rate limits | Medium | Medium | Implement caching and request optimization. |
| Data latency issues | Medium | Medium | Monitor data availability and adjust schedules. |
| Credential management | Low | High | Use secure storage, documentation, and backup procedures. |

## Success Metrics

### Technical Metrics

- **Forecast accuracy**: RMSE less than 20% of the observed range.
- **Forecast bias**: MNB less than 10%.
- **Forecast correlation**: R² greater than 0.75, with spatial and temporal correlation each above 0.6.
- **Spatial coverage**: More than 90% of monitoring sites.
- **Temporal coverage**: More than 95% of forecast periods.
- **Confidence calibration**: 90% confidence-interval coverage between 85% and 95%.

### Operational Metrics

- **Update frequency**: Daily forecasts without interruption.
- **Latency**: Forecasts available within 6 hours of data availability.
- **Reliability**: More than 99% uptime for automated workflows.

### Development Metrics

- **Code coverage**: More than 80% unit-test coverage.
- **Documentation**: 100% of public APIs documented.
- **Security**: Zero critical vulnerabilities.

## Communication Plan

### Documentation

- **Code**: Inline comments and docstrings.
- **API**: Auto-generated from docstrings.
- **User**: Markdown documentation in `docs/`.
- **Project**: This file (`PROJECT.md`).

## Version History

| Version | Date | Description |
| --- | --- | --- |
| 0.0.1-dev | November 2026 | Initial development version |
