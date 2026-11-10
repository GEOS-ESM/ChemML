# ChemML User Guide

ChemML is under active development. The current public workflow entry point is
an initial runner that loads and validates the selected configuration. Data
acquisition, preprocessing, model training, forecasting, and result
evaluation have not yet been connected to this runner.

## Validate a configuration

Run the configuration checker before a run:

```bash
python aqforecast/config_management/configuration.py config/default_config.yaml
```

Checking mode reports structural errors and warnings without modifying files.
Missing credentials and nonexistent configured paths are warnings unless
credentials are explicitly required.

Interactive mode prompts for fixable missing or invalid values:

```bash
python aqforecast/config_management/configuration.py \
    config/default_config.yaml --interactive
```

If credentials are needed, collect them separately with
`manage_credentials()` as described in the configuration reference. Credential
verification is optional and remote verification requires internet access.

## Run the current AQ-forecast skeleton

The runner is exposed as `run_aqforecast()`:

```python
from aqforecast import run_aqforecast

result = run_aqforecast("config/default_config.yaml")
print(result["status"])
print(result["message"])
```

When a run needs credentials, request credential collection and verification:

```python
result = run_aqforecast(
    "config/default_config.yaml",
    require_credentials=True,
)
```

This prompts for missing required credentials, performs the configured remote
checks, reloads the configuration with credentials required, and returns
`credentials_checked` or `credentials_failed`.

Use `require_credentials=False` for runs that do not need credential-dependent
data. Missing credentials then remain warnings rather than stopping the run.

For a valid configuration without credential checking, the current result contains:

- `status`: currently `configuration_loaded`.
- `message`: explains that the remaining workflow functions are not implemented.
- `configuration`: the resolved configuration dictionary.
- `warnings`: missing credentials, unavailable paths, and other non-fatal warnings.

When `require_credentials=True`, a successful run returns `credentials_checked`.
If credential collection fails or a remote check reports invalid credentials,
it returns `credentials_failed` with an `errors` list. Network failures that
prevent verification are reported as warnings. If the configuration itself
cannot be loaded, it returns `configuration_failed` with an `errors` list. It
does not start data access, preprocessing, training, forecasting, or
evaluation yet.

## Current limitations

The runner does not currently:

- Download or discover input data.
- Preprocess data for DeepSensor.
- Train or load a forecasting model.
- Generate forecast outputs.
- Evaluate forecasts.
- Create output directories.
- Provide operation modes such as `train`, `forecast`, or `evaluate`.

These stages will be added as their respective systems are implemented. The
runner will remain the high-level orchestration entry point, while directory
creation will be handled by a separate setup utility.

## Tests

Run the configuration, credential-management, and runner tests with:

```bash
python -m pytest tests/
```
