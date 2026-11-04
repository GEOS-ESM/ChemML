# Repository Guidelines

## Project Structure & Module Organization

This repository contains research materials for machine-learning-based air-quality analysis:

- `deepsensor_demo/` contains progressively refined Jupyter demonstrations and the Conda environment specification (`deepsensor_cenv.yml`).
- `deepsensor_run/` contains the Discover batch runner (`ASIAAQ_Deepsensor_Run.py`) and notebooks for configuring and interpreting batches.
- `README.md`, the folder READMEs, `CHANGELOG.md`, and `CONTRIBUTING.md` document usage, history, and contribution policy.
- `.github/workflows/` contains CI checks; there is currently no dedicated `tests/` directory.

Large input and output datasets are external to the repository. Do not commit generated NetCDF files, model outputs, or local environment directories.

## Build, Test, and Development Commands

There is no project build or automated Python test command. For local checks:

- `yamllint -d relaxed --no-warnings .github/workflows/*.yml .yamllint.yml` validates YAML in the same style as CI.
- Open notebooks with Jupyter in the environment described by `deepsensor_demo/deepsensor_cenv.yml`; run cells incrementally and confirm referenced data paths are available.
- On NCCS Discover, run a configured batch entry with `python deepsensor_run/ASIAAQ_Deepsensor_Run.py <run_name>`. The script expects its JSON settings and input data in the configured Discover directories.

## Coding Style & Naming Conventions

Use LF line endings, trim trailing whitespace, and keep a final newline. Follow `.editorconfig`: four spaces for Python, two spaces for YAML and CMake, and no tabs. Use descriptive `snake_case` for new Python variables and functions; retain existing uppercase-style names when editing the legacy runner unless a focused cleanup is intended. Keep notebooks readable and explain non-obvious scientific assumptions in Markdown cells.

## Testing Guidelines

No unit-test framework or coverage threshold is configured. For changes to analysis code, perform a representative notebook or Discover run and record the data/configuration assumptions in the PR. Validate changed YAML with `yamllint`; check that notebooks open and execute through the affected cells.

## Commit & Pull Request Guidelines

Use short, imperative commit subjects that describe the change (for example, `Update CHANGELOG.md` or `Add ...`). Pull requests should explain the scientific or operational impact, identify affected notebooks/scripts, and include relevant execution details or screenshots for notebook/output changes. Add at least one required repository label and update `CHANGELOG.md` using Keep a Changelog format; trivial changes may use the repository's documented changelog-skip label. External contributors must complete the GEOS-ESM CLA described in `CONTRIBUTING.md`.
