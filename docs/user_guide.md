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

## Run the current AQ-forecast skeleton

The runner is exposed as `run_aqforecast()`:

```python
from aqforecast import run_aqforecast

result = run_aqforecast("config/default_config.yaml")
print(result["status"])
print(result["message"])
```

For a valid configuration, the current result contains:

- `status`: currently `configuration_loaded`.
- `message`: explains that the remaining workflow functions are not implemented.
- `configuration`: the resolved configuration dictionary.
- `warnings`: missing credentials, unavailable paths, and other non-fatal warnings.

If the configuration cannot be loaded, the runner returns
`configuration_failed` with an `errors` list. It does not start data access,
preprocessing, training, forecasting, or evaluation yet.

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

Run the configuration and runner tests with:

```bash
python -m pytest tests/
```
