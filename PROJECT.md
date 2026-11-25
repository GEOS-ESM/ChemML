# ChemML Project Development Plan

**Repository**: <https://github.com/GEOS-ESM/ChemML.git>

**Default development branch**: `aqdatafusion_development`

## Project Overview

ChemML is a high-resolution air-quality data-fusion system that combines satellite observations, numerical model outputs, and ground-based measurements using deep learning. Forecasting is one application; the system is also intended to support retrospective assessment and other analyses of PM2.5, O₃, and NO₂ at fine spatial resolution (for example, 1 km) over user-defined regions.

### Project Goals

1. **Primary goal**: Develop an operational air-quality data-fusion system using machine learning, with forecasting as one application.
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

### `run_aqdatafusion` Workflow Modes

`run_aqdatafusion()` is the planned high-level entry point for the major
operating modes of the data-fusion system. Modes should remain explicit so
database maintenance, model development, evaluation, and model application
can be scheduled or repeated independently.

Implemented modes:

- `database_update`: update the configured input-data databases for a specified
  half-open time interval and region. Optional source selection allows focused
  acquisition or testing.
- `incremental_database_update`: update a configuration-defined rolling
  interval, such as the previous day. This mode is intended for an external
  scheduler such as cron; the scheduler invokes the mode but remains separate
  from the workflow implementation.

Planned modes:

- `model_training`: train a new Deepsensor convolutional neural process (CNP)
  using a configured time interval, input-source selection, and optional subset
  of ground-monitor locations.
- `model_evaluation`: load a trained CNP and apply it at designated target
  locations over a specified interval, producing predictions and comparison
  statistics where held-out observations are available.
- `training_and_evaluation_pipeline`: partition input data in space and time
  according to a configured cross-validation strategy, generate per-fold
  training job scripts, apply each trained fold model to its validation fold,
  calculate performance statistics, and aggregate results across folds. The
  initial implementation should generate scripts and print the NCCS command
  needed to run them, but must not submit or start jobs automatically.
- `model_application`: load a trained CNP and produce a spatially and
  temporally complete gridded output over a designated domain and interval.
  This differs from `model_evaluation`, which targets selected locations for
  comparison with observations.
- `incremental_model_application`: run `model_application` for an interval
  defined relative to the current time, such as a daily forecast of the next
  several days. It is intended for scheduled use after the required input data
  are available.

Database updates and model-application modes are separate operations and may be
offset in time. A model mode encountering missing input data should normally
issue a warning and continue where possible, since deliberately withheld
inputs may be part of evaluation or testing. Missing data should become an
error only when the requested model or configuration requires a complete input
that cannot be produced.

Trained models belong under the configured experiment model directory and
should be named using the experiment name plus a unique cross-validation-fold
identifier when applicable. Future configuration should allow an experiment
to reference a model trained by another experiment. Setup for that option may
copy the source experiment's model files into the new experiment's model
directory and rename them for the new run; this reuse workflow is planned but
not yet implemented. A future configuration setting is also needed for the
directory where generated NCCS job scripts are written.

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
- [x] Create the initial AQ-data-fusion runner skeleton that loads configuration and returns run status.
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

The Phase 1 foundation is complete. Configuration loading and validation,
credential management, setup utilities, shared contracts, database management,
and the initial workflow interfaces are available. Forecasting, validation, and
DeepSensor workflow execution remain future phases.

### Phase 2: Data Acquisition — In Progress

**Objective**: Acquire, quality-control, standardize, and maintain local
databases for all configured input sources.

**Tasks**:

- [x] Implement data acquisition and preprocessing for AirNow, OpenAQ,
  VIIRS, GOES-ABI, TROPOMI, PACE, TEMPO NO₂, TEMPO O₃ Profiles, and MCD12Q1
  land cover, including database integration and source-specific regression
  coverage.
- [x] Validate GEOS-CF remote OpenDAP database updates.
- [ ] Complete GEOS-CF local NCCS and end-to-end database-update validation.
- [x] Common data acquisition functionality, including integrity verification,
  coordinate checks, shared regridding, structured acquisition errors, empty
  source handling, registry-based adapters, operational reports, and regression
  fixtures/tests.
- [x] Update and streamline project documentation, including deployment and
  workflow guidance.
- [x] Integrate database-update and incremental-update modes with
  `run_aqdatafusion()`, including the Conda scheduler entry point and rolling
  window safeguards.
- [x] Examples and scripting/orchestration, including
  `scripts/update_database_incremental.sh`, the data-acquisition notebook, and
  the shared Cartopy plotting function with local caching and offline fallback.
- [ ] Testing and verification
  - [ ] Conduct an end-to-end database-update test covering acquisition,
    preprocessing, merging, partition writing, and catalog generation.
    After all intended datasets have acquisition implementations, conduct an
    all-up database-update test covering every implemented dataset over a period
    that crosses a month boundary. Verify multi-source downloads, database
    merging, monthly partitioning, catalogs, and subsequent data access.
  - [ ] Test data acquisition on NCCS. Schedule ongoing data ingest:
    - [ ] Create scripts to update the database in NCCS on a regular (daily) cadence.
    - [ ] Schedule scripts to run automatically using `cron`.
    - [ ] Verify that data are being ingested as intended.

**Deliverables**:

- ~~Functional data acquisition modules for the immediate Phase 2 sources.~~
- ~~Data quality control procedures.~~
- ~~Download scripts for historical data.~~
- ~~Unit tests for data modules.~~
- ~~Network-free adapter tests with mocked API/filesystem responses.~~
- ~~Representative raw-data and standardized database fixtures.~~
- ~~Tests for partial updates, retry/failure behavior, and remaining-gap
  reporting.~~
- ~~Automated database updating script.~~
- ~~Database integrity verification.~~
- ~~Documentation for data sources.~~

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
- [ ] Integrate the future forecasting stages with `run_aqdatafusion()`.
- [ ] Update `config/deepsensor/deepsensor_config.yaml` once the Phase 4 DeepSensor implementation defines the required configuration settings.
- [ ] Keep `config/aqdatafusion/aqdatafusion_config.yaml` up to date as the forecasting model and its required settings are developed.
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
- [x] Create and maintain `docs/data_sources.md` as the canonical data-source reference.
- [ ] Create `docs/nccs_deployment.md`.
- [ ] Create `docs/api_reference.md`.
- [ ] Develop example Jupyter notebooks.
- [x] Create `docs/examples/01_data_acquisition.ipynb`.
- [ ] Create `docs/examples/02_model_training.ipynb`.
- [ ] Create `docs/examples/03_retrospective_forecast.ipynb`.
- [ ] Create `docs/examples/04_realtime_forecast.ipynb`.
- [ ] Create `docs/examples/05_validation_analysis.ipynb`.
- [x] Set up the initial pytest test structure.
- [ ] Complete unit-test coverage.
- [x] Add database-manager regression and integration tests using representative CSV and NetCDF fixtures.
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

## Deferred Dataset Work

These datasets are outside the main implementation path and will be resumed
when their data availability and integration requirements are ready:

- [ ] GEMS ingest and preprocessing.
- [ ] GCAS ingest and preprocessing.
- [ ] TEMPO PM2.5 ingest and preprocessing — deferred until April 2027 because
  the product is not expected to be available before then.

## Current Development Status

Completed implementation areas are recorded in `CHANGELOG.md`. In summary,
the configuration foundation and the Phase 2 database-ingestion infrastructure
are implemented, including source registration, integrity verification,
incremental updates, operational reports, and scheduler integration. Several
source adapters are production-ready for their configured access modes; GEOS-CF
remote OpenDAP updates have been validated, while local/NCCS end-to-end
validation remains pending.

### In Progress

- 🚧 GEOS-CF local/NCCS and end-to-end validation.
- 🚧 Forecasting and validation workflow implementation.

### Upcoming

- Full all-source database-update testing, including retries, partial failures,
  and subsequent database access.
- NCCS environment testing and installation/scheduling verification.
- Documentation streamlining and additional workflow example notebooks.

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
