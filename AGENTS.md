# Repository Guidelines

## Project Structure & Module Organization

This repository is under active development as a set of codes implementing a machine-learning-based air-quality forecasting workflow. It is not necessarily intended to become a standalone installable Python package.

- `docs/examples/deepsensor_demo/` contains progressively refined Jupyter demonstrations and the Conda environment specification (`deepsensor_cenv.yml`).
- `docs/examples/deepsensor_run/` contains the Discover batch runner (`ASIAAQ_Deepsensor_Run.py`) and notebooks for configuring and interpreting batches.
- `config/` contains the master configuration and component YAML files.
- `aqforecast/config_management/` contains reusable configuration validation and interactive setup utilities.
- `aqforecast/config_management/credentials.py` contains local credential collection and optional remote verification.
- `aqforecast/utils/logging.py` contains shared console/file logging and credential redaction.
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
- Open notebooks with Jupyter in the environment described by `docs/examples/deepsensor_demo/deepsensor_cenv.yml`; run cells incrementally and confirm referenced data paths are available.
- On NCCS Discover, run a configured batch entry with `python docs/examples/deepsensor_run/ASIAAQ_Deepsensor_Run.py <run_name>`. The script expects its JSON settings and input data in the configured Discover directories.

## Coding Style & Naming Conventions

Use LF line endings, trim trailing whitespace, and keep a final newline. Follow `.editorconfig`: four spaces for Python, two spaces for YAML and CMake, and no tabs. Use descriptive `snake_case` for new Python variables and functions; retain existing uppercase-style names when editing the legacy runner unless a focused cleanup is intended. Keep notebooks readable and explain non-obvious scientific assumptions in Markdown cells. Specific Python and dependency versions are provisional; check and update them as the workflow is built out and its compatibility is established.

## Testing Guidelines

An initial pytest test structure exists, including tests for configuration loading, credential collection, and the configuration-only `run_aqforecast()` entry point, but no coverage threshold or comprehensive test coverage is configured yet. Remote credential verification is opt-in and should not be required for the network-free test suite. Run `python -m pytest tests/` for Python changes. For changes to analysis code, perform a representative notebook or Discover run and record the data/configuration assumptions in the PR. Validate changed YAML with `yamllint`; check that notebooks open and execute through the affected cells.

## Commit & Pull Request Guidelines

Use short, imperative commit subjects that describe the change (for example, `Update CHANGELOG.md` or `Add ...`). Pull requests should explain the scientific or operational impact, identify affected notebooks/scripts, and include relevant execution details or screenshots for notebook/output changes. Add at least one required repository label. Maintain `CHANGELOG.md` by recording major new additions and changes under the appropriate Keep a Changelog section, including the date of the change. Trivial changes may use the repository's documented changelog-skip label. External contributors must complete the GEOS-ESM CLA described in `CONTRIBUTING.md`.
