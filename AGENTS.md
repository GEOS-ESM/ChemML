# Repository Guidelines

## Project Structure & Module Organization

This repository is under active development as a set of codes implementing a machine-learning-based air-quality forecasting workflow. It is not necessarily intended to become a standalone installable Python package.

- `docs/examples/deepsensor_demo/` contains progressively refined Jupyter demonstrations and the Conda environment specification (`deepsensor_cenv.yml`).
- `docs/examples/deepsensor_run/` contains the Discover batch runner (`ASIAAQ_Deepsensor_Run.py`) and notebooks for configuring and interpreting batches.
- `docs/implementation_instructions_for_agents/` is an agent-only working area
  for implementation guidance, including dataset/API access instructions. Its
  contents are local notes and must not be committed.
- `config/` contains the master configuration and component YAML files.
- `aqforecast/config_management/` contains reusable configuration validation and configuration-loading utilities.
- `aqforecast/config_management/credentials.py` contains local credential collection and optional remote verification.
- `aqforecast/utils/logging.py` contains shared console/file logging and credential redaction.
- `aqforecast/utils/operational_logging.py` writes human-readable per-run database-update reports and removes expired operational reports according to configured retention.
- `aqforecast/utils/regridding.py` contains the generic irregular-point to
  latitude/longitude-grid regridder. Future source preprocessors should use
  this utility for regridding rather than duplicating source-specific binning
  logic; it uses each dataset's configured `regridding.latlon_resolution` and
  preserves non-spatial dimensions.
- `aqforecast/utils/opendap.py` contains the reusable authenticated NASA
  Earthdata DAP4 subset client. It uses Earthaccess sessions with xarray's
  pydap backend and applies coordinate-derived index slices before loading
  science arrays.
- `aqforecast/utils/setup.py` contains the explicit first-time setup flow for copying configuration files, collecting paths and credentials, creating configured directories, and verifying configuration.
- `aqforecast/data_management/` contains the incremental partitioned input-data database manager, post-update integrity verification, and regenerable per-source catalogs.
- `aqforecast/data_acquisition/generic.py` contains local and remote acquisition adapter wrappers and shared acquisition behavior. Source-specific acquisition implementations belong in new modules under `aqforecast/data_acquisition/`, with corresponding preprocessing implementations in new modules under `aqforecast/preprocessing/`.
- `aqforecast/data_acquisition/airnow.py` and `aqforecast/preprocessing/airnow.py` provide the AirNow source-specific implementation; `openaq.py` provides the corresponding OpenAQ implementation. Use these point-monitor providers as references for adding other datasets.
- `aqforecast/data_acquisition/tropomi.py` and `aqforecast/preprocessing/tropomi.py` provide the implemented version-2 TROPOMI NO₂ and total-column O₃ satellite ingest.
- `aqforecast/data_acquisition/viirs.py` and `aqforecast/preprocessing/viirs.py` provide the implemented VIIRS/JPSS2 VJ219A2 version-002 AOD ingest.
- `aqforecast/data_acquisition/pace.py` and `aqforecast/preprocessing/pace.py` provide the implemented PACE OCI trace-gas ingest.
- `aqforecast/data_acquisition/tempo.py` and `aqforecast/preprocessing/tempo.py` provide the implemented TEMPO NO₂ DAP4/OpenDAP ingest, including resumable subset caching.
- `aqforecast/data_acquisition/tempo_o3.py` and `aqforecast/preprocessing/tempo_o3.py` provide the implemented configurable-layer TEMPO O₃ Profile DAP4/OpenDAP ingest.
- `aqforecast/data_acquisition/land_cover.py` and `aqforecast/preprocessing/land_cover.py` provide the implemented MCD12Q1 yearly land-cover ingest, including source-year fallback and categorical regridding from the native sinusoidal grid.
- `aqforecast/data_acquisition/goes_abi.py` and `aqforecast/preprocessing/goes_abi.py` provide the implemented NOAA S3 GOES-ABI AOD ingest, including ordered GOES-19/16/18/17 fallback, fixed-grid geolocation, DQF filtering, configurable 0.02-degree regridding, and hourly center-timestamp aggregation.
- `aqforecast/data_acquisition/geos_cf.py` and `aqforecast/preprocessing/geos_cf.py` provide the developed GEOS-CF v2 analysis/forecast ingest, including chunked public OpenDAP access, optional NCCS-local access, native-grid processing, and `forecast_lead_day` indexing. The adapter has network-free tests but no completed local end-to-end database test because public OpenDAP transfers have been intermittent.
- `aqforecast/preprocessing/generic.py` contains shared fill-value and basic quality-control preprocessing.
- `aqforecast/contracts.py` contains the shared data contracts (`DataRequest`,
  `DatasetBundle`, `ForecastRequest`, `ForecastResult`, `ValidationResult`,
  and `WorkflowContext`) used to keep future stages composable.
- `aqforecast/data_acquisition/`, `aqforecast/preprocessing/`,
  `aqforecast/forecasting/`, `aqforecast/validation/`, and
  `aqforecast/orchestration/` contain the stage interfaces. Database updating
  is the first implemented orchestration workflow; most source-specific and
  forecasting implementations remain planned.
- `aqforecast/aqforecast.py` contains the `run_aqforecast()` entry point. Its
  default forecast mode remains configuration-only, while its explicit
  `database_update` mode runs the implemented incremental ingest workflow.
- `aqforecast/orchestration/database_update.py` contains the standalone `run_database_update()` mode and `DatabaseUpdateStage`.
- `aqforecast/orchestration/database_update.py` also contains `run_incremental_database_update()`, which computes a UTC-hour rolling update window from configuration; scheduling remains external.
- `tests/` contains the pytest regression suite for configuration, database
  management, AirNow/OpenAQ/TROPOMI/VIIRS/PACE/TEMPO/MCD12Q1/GOES-ABI/GEOS-CF
  ingest, OpenDAP access, and shared regridding.
- `README.md`, the folder READMEs, `CHANGELOG.md`, and `CONTRIBUTING.md` document usage, history, and contribution policy.
- `.github/workflows/` contains CI checks.

Large input and output datasets are external to the repository. Do not commit generated NetCDF files, model outputs, or local environment directories.

## Build, Test, and Development Commands

There is no project build command. For local checks:

- `yamllint -d relaxed --no-warnings .github/workflows/*.yml .yamllint.yml config/default_config.yaml config/*/*.yaml` validates YAML in the same style as CI.
- Activate the `chemml` Conda environment before running Python commands during development: `conda activate chemml`.
- `python -m pytest tests/` runs the Python regression tests from the activated `chemml` environment.
- `python aqforecast/config_management/configuration.py config/default_config.yaml` checks the referenced configuration files.
- `python aqforecast/config_management/configuration.py config/default_config.yaml --interactive` interactively fills fixable missing or invalid configuration values.
- `python -m aqforecast.utils.setup` runs the guided first-time setup flow after the conda environment is activated.
- Open notebooks with Jupyter in the environment described by `docs/examples/deepsensor_demo/deepsensor_cenv.yml`; run cells incrementally and confirm referenced data paths are available.
- On NCCS Discover, run a configured batch entry with `python docs/examples/deepsensor_run/ASIAAQ_Deepsensor_Run.py <run_name>`. The script expects its JSON settings and input data in the configured Discover directories.
- Start an incremental database update from Python with `run_database_update()` as documented in `docs/user_guide.md`. AirNow or OpenAQ is automatically registered for regions whose `ground_monitoring.provider` selects that provider; TROPOMI, VIIRS, PACE, TEMPO NO₂, and TEMPO O₃ are automatically registered when their configured datasets are selected.
- When conducting system tests during development, use `config/testing_config.yaml` unless otherwise specified.

## Coding Style & Naming Conventions

Use LF line endings, trim trailing whitespace, and keep a final newline. Follow `.editorconfig`: four spaces for Python, two spaces for YAML and CMake, and no tabs. Use descriptive `snake_case` for new Python variables and functions; retain existing uppercase-style names when editing the legacy runner unless a focused cleanup is intended. Keep notebooks readable and explain non-obvious scientific assumptions in Markdown cells. Specific Python and dependency versions are provisional; check and update them as the workflow is built out and its compatibility is established.

### Workflow module design

Keep the stage boundaries consistent as the package is implemented:

- Data-acquisition implementations should accept a `DataRequest` and resolved
  configuration, and return a `DatasetBundle` keyed by the configured source.
  Source-specific downloading and parsing belongs in this layer; orchestration
  should not contain source-specific API logic.
- Preprocessors should accept and return `DatasetBundle` objects. Keep quality
  control, timestamp/coordinate normalization, regridding, and feature
  preparation here rather than duplicating them in models or runners.
- Forecasting models should implement `fit()` and `predict()` using
  `ForecastRequest` and `ForecastResult`. Model-specific settings belong in
  the forecasting configuration files, while workflow control belongs in
  orchestration.
- Validators should accept forecast results plus observations and return a
  `ValidationResult`; metrics and plots should be selected from validation
  configuration rather than hard-coded in the runner.
- Orchestration stages should pass a `WorkflowContext` and coordinate the
  stages without reimplementing their scientific logic. Preserve warnings and
  metadata so later logging can report provenance and partial failures.

When adding a stage, update the relevant `base.py` interface and shared
contract first, then add a focused implementation and tests. Follow the
AirNow acquisition/preprocessing modules as the concrete example of this
boundary: acquisition returns a preliminary `DatasetBundle`, preprocessing
applies source-specific normalization and QC, and the database manager owns
merging and partitioning. Keep the current
configuration-only `run_aqforecast()` behavior intact until a complete stage
is ready to be integrated. The database-update mode is a separate explicit
operation and must not run during package import. Do not make package imports
perform downloads, create directories, train models, or require credentials.

### Recommended data-ingest pattern

Use the AirNow implementation as the model for future source integrations:

```text
resolved configuration + DataRequest
    → source-specific acquisition module
        → remote/local access, retries, response parsing, preliminary schema
    → source-specific preprocessing module
        → unit/timestamp normalization, QC, canonical names and site IDs
    → generic DatasetBundle contract
    → generic DatabaseManager
        → completeness checks, coordinate validation, merge policy,
          partitioning, and catalog generation
```

Keep source-specific API or file-format logic out of orchestration and the
generic manager. Generic ingest/database functions should provide reusable
coordinate validation, structured error propagation to logging, and schema
checks; each source module should supply only its source-specific request,
parsing, and scientific normalization behavior.

## Testing Guidelines

The pytest suite covers configuration loading, credential collection, setup,
database-manager site identity and timestamp handling, the AirNow, OpenAQ,
TROPOMI, VIIRS, PACE, and TEMPO adapters and preprocessors using mocked responses or
fixtures, and the shared regridder.
No coverage threshold is configured yet. Remote credential verification and
live API access are opt-in and should not be required for the network-free test
suite. Run `python -m pytest tests/` for Python changes. For changes to
analysis code, perform a representative notebook or Discover run and record
the data/configuration assumptions in the PR. Validate changed YAML with
`yamllint`; check that notebooks open and execute through the affected cells.

## Commit & Pull Request Guidelines

Use short, imperative commit subjects that describe the change (for example, `Update CHANGELOG.md` or `Add ...`). Pull requests should explain the scientific or operational impact, identify affected notebooks/scripts, and include relevant execution details or screenshots for notebook/output changes. Add at least one required repository label. Maintain `CHANGELOG.md` by recording major new additions and changes under the appropriate Keep a Changelog section, including the date of the change. Trivial changes may use the repository's documented changelog-skip label. External contributors must complete the GEOS-ESM CLA described in `CONTRIBUTING.md`.
