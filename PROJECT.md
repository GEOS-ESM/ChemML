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
  place. AirNow and OpenAQ are complete point-monitor source-specific
  implementations. TROPOMI version-2 NO₂/O₃, VIIRS/JPSS2 VJ219A2 AOD, PACE
  OCI trace gases, and TEMPO NO₂/O₃ Profile acquisition and preprocessing are complete,
  with retries, QC, aggregation, shared regridding where applicable, and
  database registration. TEMPO uses authenticated DAP4/OpenDAP subsets with
  resumable `.tmp` caching and post-success cleanup. The shared
  irregular-point regridder is implemented in `aqforecast/utils/regridding.py`,
  using each dataset's configured target resolution while preserving
  non-spatial dimensions; other dataset-specific download and source adapters
  remain future work.
- GEOS-CF v2 acquisition and preprocessing have been developed. The adapter
  supports chunked public OpenDAP access, optional NCCS-local access, finite-
  value handling, native-grid analysis/forecast merging, and
  `forecast_lead_day` indexing. Network-free tests pass, but the implementation
  is not complete because a local end-to-end database test has not been
  completed and the public OpenDAP service has intermittently returned 502
  responses and stalled transfers.
- A live ATL database-update test using an in-memory OpenAQ provider override
  completed for August 4–9, 2026 and produced an OpenAQ partition alongside
  the existing AirNow partition in the external test-data directory.
- A live ATL TROPOMI database-update test completed for August 4–12, 2026,
  including overlapping incremental updates through `run_aqforecast()` and
  storage of both daily satellite variables in one monthly NetCDF partition.
- A live ATL TEMPO NO₂ database-update test completed for August 4–8, 2026
  through `run_aqforecast()` using the testing configuration, including native
  grid hourly storage, completeness-window correction, duplicate-time merging,
  and successful temporary-cache cleanup.
- A live ATL TEMPO O₃ Profile database-update test completed for August 4–8,
  2026 through `run_aqforecast()` using the testing configuration, including
  configurable layer selection, native-grid hourly storage, QC, and temporary
  cache cleanup.
- Model execution, forecasting, and evaluation remain to be implemented.

### Phase 2: Data Acquisition — In Progress

**Objective**: Acquire, quality-control, standardize, and maintain local
databases for all configured input sources.

**Tasks**:

- [ ] Implement data acquisition and preprocessing for key datasets.
  - [x] AirNow: acquire, subset, standardize, quality-control, validate site
    identity, and integrate into the database.
    - [x] Add the AirNow source-specific acquisition and preprocessing adapters to
      the database manager.
    - [x] Add AirNow source-specific tests using mocked API responses and
      representative raw-data fixtures.
  - [x] OpenAQ: acquire, subset, standardize, quality-control, reconcile sites,
    and integrate into the database, including a live ATL test.
  - [x] VIIRS/JPSS2 VJ219A2 AOD: acquire, quality-control, geolocate, regrid,
    aggregate, and integrate into the database.
  - [x] GOES-ABI AOD:
    - [x] Acquire public NOAA S3 `ABI-L2-AODC` data using ordered GOES-19,
      GOES-16, GOES-18, and GOES-17 fallback.
    - [x] Subset data by configured region, period, and variables.
    - [x] Convert fixed-grid NetCDF files to the standardized database format.
    - [x] Apply DQF, fill-value, valid-range, and physical AOD filters.
    - [x] Regrid to a configurable 0.02-degree grid and aggregate hourly with
      timestamps at the center of each UTC hour.
    - [x] Integrate processed data with the standardized database.
  - [x] TROPOMI NO₂/O₃: acquire, quality-control, regrid, aggregate, combine,
    and integrate both products into the database.
  - [x] PACE NO₂/O₃: acquire, quality-control, regrid, aggregate, and integrate
    both trace-gas variables into the database.
  - [x] TEMPO NO₂: acquire authenticated OpenDAP subsets, quality-control,
    aggregate on the native grid, and integrate with resumable caching.
  - [x] TEMPO O₃ Profiles: acquire configurable profile layers through OpenDAP,
    apply cloud/angle QC, aggregate on the native grid, and integrate with cache
    cleanup.
  - [ ] GEOS-CF (developed, but not complete pending local end-to-end testing):
    - [x] Implement analysis and forecast acquisition for configured regions and periods.
    - [x] Subset data by configured region, period, and selected variables using chunked requests.
    - [x] Convert source data to the standardized native-grid database structure.
    - [x] Apply finite-value handling, timestamp normalization, and availability-gap warnings.
    - [x] Integrate analysis and forecast runs with `forecast_lead_day` indexing.
    - [ ] Complete local NCCS and end-to-end database-update testing.
  - [x] Land Cover information:
    - [x] Acquire the configured reference-period land-cover product. If
      current-year data are unavailable, implement a special rule for acquiring
      earlier data. Land-cover data are part of this acquisition workflow, but
      require a special time-offset provision. The acquisition process must
      support requesting a reference period from an earlier source period (for
      example, using land-cover data from the preceding year) rather than
      assuming that all sources cover the same dates.
    - [x] Subset data by configured region and variables.
    - [x] Convert source files to the standardized database format.
    - [x] Apply quality control, fill-value handling, and class validation.
    - [x] Regrid or aggregate to the configured spatial resolution.
    - [x] Integrate the reference-period data with the existing database.
  - [ ] Common data acquisition functionality
  - [x] Implement post-update database integrity verification, including
    timestamp completeness, required variables, coordinate/grid structure,
    duplicate detection, partition/catalog consistency, and explicit reporting
    of any remaining gaps. Remaining source-availability gaps are reported as
    warnings; structural integrity failures are reported as source failures.
  - [x] Add generic site-coordinate verification at both acquisition-output and
    database-management boundaries, using configured site IDs and tolerances
    rather than duplicating the checks in each dataset adapter.
  - [x] Implement a shared irregular-point regridder with dataset-specific
    latitude/longitude resolution, numeric means, categorical modes, preserved
    non-spatial dimensions, and NaN empty cells.
  - [x] Extend the generic acquisition contract so source adapters can pass
    structured API/file error messages to the logging and update-report systems.
  - [x] Handle empty source files, including CSV files containing only headers,
    as empty databases or explicit, actionable input errors.
  - [x] Add database-manager tests for missing intervals, site identity,
    coordinate consistency, empty databases, and timestamp normalization.
  - [x] Add offline cross-source and cross-month database fixtures, including
    overlapping updates, failure isolation, year boundaries, and leap years.
  - [ ] Add broader tests for partial updates, retries/failures, and output
    database fixtures across all sources.
  - [x] Replace the hard-coded provider-to-adapter mapping in `DatabaseManager`
    with a registry-based source-adapter mechanism that supports custom
    registrations and explicit adapter overrides.
  - [x] Implement operational database-update reports with per-source results,
    warnings, detailed failures, interpretable filenames, and configurable
    cleanup of reports older than the retention period.
  - [ ] Keep `config/inputs/input_data_config.yaml` aligned with the settings required to download and preprocess each data source as ingest codes are developed.
  - [ ] Update project documentation files.
    - [ ] Keep `PROJECT.md` up to date with the current status of the implementation.
    - [ ] Keep `AGENTS.md` up to date with created files, notes on the overall project workflow, and notes relevant to implementing other data ingests in the future.
    - [ ] Keep `README.md` up to date with a brief note on development status, repository components, package dependencies, data sources, and a high-level overview of the workflow.
    - [ ] Keep `docs/configuration.md` up to date with notes on specific settings needed to be specified for the input data sources.
    - [ ] Keep `docs/data_sources.md` up to date with a summary of how each dataset is accessed and preprocessed.
    - [ ] Keep `docs/installation.md` up to date with an example of how to start an archive of the input data sources for a region of interest.
    - [ ] Keep `docs/user_guide.md` up to date with examples of how database updates are performed.
- [ ] Integration with `aqforecast` workflows
  - [x] Modify `run_aqforecast()` to expose a database-update mode now that a
    complete source-specific ingestion path exists.
  - [x] Add an incremental database update mode that automatically updates the
    input datasets around the current UTC hour, with configurable lookback,
    lookahead, and maximum-window safeguards. Scheduling remains a future
    script/cron task.
- [ ] Examples and Scripting/Orchestration
  - [ ] Create a runnable data download script (`.sh` file) which can be scheduled to run at a fixed cadence (e.g., daily) to keep the database up to date.
  - [ ] Create a Python notebook illustrating how to populate the database and visualize the data currently available in the database. Use `docs/examples/deepsensor_demo/Deepsensor_demo_Oct2025.ipynb` as inspiration for the plots.
    - [ ] To support this, create a generalized plotting function in the `aqforecast/utils` folder. This function should use `cartopy` for basemaps. Be sure that base maps are downloaded and saved locally during first-time setup if an internet connection is available.
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

- Functional data acquisition modules for the immediate Phase 2 sources.
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

### Future Dataset Work — Deferred

These datasets are outside the immediate Phase 2 implementation scope and are
deferred until their data availability and integration requirements are ready:

- [ ] GEMS ingest and preprocessing.
- [ ] GCAS ingest and preprocessing.
- [ ] TEMPO PM2.5 ingest and preprocessing — deferred until April 2027 because
  the product is not expected to be available before then.

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
- [x] Create and maintain `docs/data_sources.md` as the canonical data-source reference.
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
- ✅ TROPOMI version-2 NO₂ and total-column O₃ acquisition, moderate QC,
  0.05-degree regridding, daily aggregation, combined NetCDF storage, and
  incremental ATL integration tests.
- ✅ TEMPO NO₂ DAP4/OpenDAP acquisition, resumable regional caching, moderate
  QC, native-grid hourly aggregation, database integration, and successful
  ATL testing through `run_aqforecast()`.
- ✅ TEMPO O₃ Profile DAP4/OpenDAP acquisition with configurable profile layers,
  cloud/angle QC, native-grid hourly aggregation, database integration, and
  successful ATL testing through `run_aqforecast()`.
- ✅ MCD12Q1 yearly land-cover acquisition with up to two years of source-year
  fallback, native sinusoidal geolocation, categorical 0.005-degree regridding,
  configurable `LW`/`QC` filters, yearly storage, and ATL database-update
  testing.

AirNow, OpenAQ, TROPOMI, VIIRS, PACE, TEMPO NO₂/O₃ Profile, MCD12Q1 land
cover, and GOES-ABI now have complete source-specific acquisition and
preprocessing paths. GEOS-CF is developed but incomplete pending local
end-to-end testing; GEMS, GCAS, and TEMPO PM2.5 are deferred to future work.

### In Progress

- 🚧 GEOS-CF local/end-to-end validation and broader database integration fixtures.
- 🚧 Forecasting and validation workflow implementation.

### Upcoming

- Source-specific acquisition adapters and validation for any remaining Phase 2
  sources.
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
| VIIRS/JPSS2 MAIAC | VJ219A2 V002 | `optical_depth_055` | 0.01° output grid | 1–2 days |
| TROPOMI | S5P_L2 | NO₂, O₃ | 7 km | 1–2 days |
| PACE OCI | PACE_OCI_L2_TRGAS V3.0 | `total_column_no2`, `total_column_o3` | 0.02° output grid | 1–2 days |
| GOES-ABI | ABI-L2-AOD | AOD | 2 km | 1 hour |
| TEMPO NO₂ | TEMPO_NO2_L3 | `vertical_column_troposphere` | native ~0.02° grid | 1 hour |
| TEMPO O₃ Profile | TEMPO_O3PROF_L3 | configurable `ozone_profile_layer_*` | native ~0.04° grid | 1 hour |
| TEMPO PM2.5 | TEMPO PM product | deferred beyond Phase 2 | 2–8 km | 1 hour |

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
