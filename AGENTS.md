# Repository Guidelines

## Project Structure & Module Organization

This repository is under active development as a set of codes implementing a machine-learning-based air-quality forecasting workflow. It is not necessarily intended to become a standalone installable Python package.

- `docs/examples/deepsensor_demo/` contains progressively refined Jupyter demonstrations and the Conda environment specification (`deepsensor_cenv.yml`).
- `docs/examples/deepsensor_run/` contains the Discover batch runner (`ASIAAQ_Deepsensor_Run.py`) and notebooks for configuring and interpreting batches.
- `config/` contains the master configuration and component YAML files.
- `aqforecast/config_management/` contains reusable configuration validation and configuration-loading utilities.
- `aqforecast/config_management/credentials.py` contains local credential collection and optional remote verification.
- `aqforecast/utils/logging.py` contains shared console/file logging and credential redaction.
- `aqforecast/utils/setup.py` contains the explicit first-time setup flow for copying configuration files, collecting paths and credentials, creating configured directories, and verifying configuration.
- `aqforecast/contracts.py` contains the shared data contracts (`DataRequest`,
  `DatasetBundle`, `ForecastRequest`, `ForecastResult`, `ValidationResult`,
  and `WorkflowContext`) used to keep future stages composable.
- `aqforecast/data_acquisition/`, `aqforecast/preprocessing/`,
  `aqforecast/forecasting/`, `aqforecast/validation/`, and
  `aqforecast/orchestration/` contain interface-only package scaffolds. Their
  `base.py` modules define the boundaries between stages; substantive
  implementations are still planned.
- `aqforecast/aqforecast.py` contains the initial configuration-only `run_aqforecast()` entry point.
- `tests/` contains the initial pytest regression tests.
- `README.md`, the folder READMEs, `CHANGELOG.md`, and `CONTRIBUTING.md` document usage, history, and contribution policy.
- `.github/workflows/` contains CI checks.

Large input and output datasets are external to the repository. Do not commit generated NetCDF files, model outputs, or local environment directories.

## Build, Test, and Development Commands

There is no project build command. For local checks:

- `yamllint -d relaxed --no-warnings .github/workflows/*.yml .yamllint.yml config/default_config.yaml config/*/*.yaml` validates YAML in the same style as CI.
- `python -m pytest tests/` runs the Python regression tests.
- `python aqforecast/config_management/configuration.py config/default_config.yaml` checks the referenced configuration files.
- `python aqforecast/config_management/configuration.py config/default_config.yaml --interactive` interactively fills fixable missing or invalid configuration values.
- `python -m aqforecast.utils.setup` runs the guided first-time setup flow after the conda environment is activated.
- Open notebooks with Jupyter in the environment described by `docs/examples/deepsensor_demo/deepsensor_cenv.yml`; run cells incrementally and confirm referenced data paths are available.
- On NCCS Discover, run a configured batch entry with `python docs/examples/deepsensor_run/ASIAAQ_Deepsensor_Run.py <run_name>`. The script expects its JSON settings and input data in the configured Discover directories.

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
contract first, then add a focused implementation and tests. Keep the current
configuration-only `run_aqforecast()` behavior intact until a complete stage
is ready to be integrated. Do not make package imports perform downloads,
create directories, train models, or require credentials.

## Testing Guidelines

An initial pytest test structure exists, including tests for configuration loading, credential collection, the guided setup flow, and the configuration-only `run_aqforecast()` entry point, but no coverage threshold or comprehensive test coverage is configured yet. Remote credential verification is opt-in and should not be required for the network-free test suite. Run `python -m pytest tests/` for Python changes. For changes to analysis code, perform a representative notebook or Discover run and record the data/configuration assumptions in the PR. Validate changed YAML with `yamllint`; check that notebooks open and execute through the affected cells.

## Commit & Pull Request Guidelines

Use short, imperative commit subjects that describe the change (for example, `Update CHANGELOG.md` or `Add ...`). Pull requests should explain the scientific or operational impact, identify affected notebooks/scripts, and include relevant execution details or screenshots for notebook/output changes. Add at least one required repository label. Maintain `CHANGELOG.md` by recording major new additions and changes under the appropriate Keep a Changelog section, including the date of the change. Trivial changes may use the repository's documented changelog-skip label. External contributors must complete the GEOS-ESM CLA described in `CONTRIBUTING.md`.
