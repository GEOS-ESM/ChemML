# ChemML User Guide

ChemML is under active development. The current public workflow entry point is
an initial runner that loads and validates the selected configuration. The
incremental input-data database update mode is available as a standalone
orchestration operation. AirNow, OpenAQ, TROPOMI, VIIRS, PACE, and TEMPO NO₂/O₃
acquisition and preprocessing are implemented; model training, forecasting,
and result evaluation remain under development.

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

The implemented database-update mode is also available through the same
runner:

```python
result = run_aqforecast(
    "config/default_config.yaml",
    mode="database_update",
    start_time="2026-08-04T00:00:00Z",
    end_time="2026-08-08T00:00:00Z",
    source_keys=["ground_monitors"],
    require_credentials=True,
)
print(result["report"])
```

## Update the input-data database

Database updates use a half-open UTC interval, `[start_time, end_time)`. By
default, every input marked `enabled: true` in
`config/aqforecast/aqforecast_config.yaml` is checked. Existing partitioned
files are inspected for expected timestamps, missing intervals are requested
from the registered source adapters, processed data are merged using the
`fill_missing` policy, and each source catalog is regenerated.

The update operation can be started from Python after loading the resolved
configuration:

```python
from aqforecast.config_management.configuration import load_configuration
from aqforecast.orchestration import run_database_update

configuration = load_configuration("config/default_config.yaml")
report = run_database_update(
    configuration,
    "2025-01-01T00:00:00Z",
    "2025-02-01T00:00:00Z",
)
print(report)
```

To update only selected sources, pass `source_keys`:

```python
report = run_database_update(
    configuration,
    "2025-01-01T00:00:00Z",
    "2025-02-01T00:00:00Z",
    source_keys=["GEOS-CF", "ground_monitors"],
)
```

### Update a ground-monitor database

For a region whose configuration sets
`region.ground_monitoring.provider: AirNow` or `OpenAQ`, the database manager
registers the corresponding acquisition and preprocessing implementations
automatically. Only one ground-monitor provider is active for a region. Use the
local credentials file and select only `ground_monitors` while testing:

```python
from aqforecast.config_management.configuration import load_configuration
from aqforecast.orchestration import run_database_update

configuration = load_configuration(
    "config/testing_config.yaml",
    require_credentials=True,
)
report = run_database_update(
    configuration,
    "2026-08-04T00:00:00Z",
    "2026-08-08T00:00:00Z",
    source_keys=["ground_monitors"],
    conflict_policy="fill_missing",
)
print(report)
```

Database-update intervals are half-open: `[start_time, end_time)`. The example
therefore includes August 4–7. The AirNow adapter translates this interval to
the API's inclusive hourly `endDate`, uses the configured region bounds, and
retrieves the verified historical response format (`dataType=C`,
`monitorType=2`). It returns preliminary AQS site identifiers and temporary
unit columns; the AirNow preprocessor converts gaseous PPM to PPB, applies
source-specific QC, maps the AQS identifier to ChemML's `site_id`, and removes
temporary unit columns before archiving.

The testing configuration writes point-data CSV partitions beneath its
configured `ground_monitors` path. Existing valid values are preserved and a
later `fill_missing` run can back-fill observations returned by a repeat API
query. An empty source directory is treated as an empty database and is
initialized by the first update.

For OpenAQ, the adapter discovers locations in the configured region and
queries the sensor-specific v3 measurements endpoint. It converts PM2.5 and
PM10 to µg/m³ and trace gases to ppb, applies the same configured bounds as
AirNow, and reconciles multiple sensors by filling missing values and selecting
the highest sensor ID when valid values conflict.

The default behavior fills missing timestamps and values while preserving
existing data. Implemented dataset-specific adapters are registered
automatically when their configured sources are selected. Use
`conflict_policy="replace_partition"` or
`override=True` only when an affected partition should be replaced. AirNow is
registered automatically for AirNow regions; unavailable or still-planned
sources are reported without silently fabricating data.

Database files are stored using the partition and format configured in
`config/inputs/input_data_config.yaml`: NetCDF for gridded data and CSV for
point data. Temporary downloads and staged writes use a per-run `.tmp`
directory, which is cleaned after the update. A regenerated `catalog.json` is
written in each source directory as a confirmation of the files on disk.

For configuration-only mode, a valid `run_aqforecast()` result contains:

- `status`: `configuration_loaded`.
- `message`: explains that configuration-only mode does not start a database update.
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

Configuration-only mode does not currently:

- Download or discover input data.
- Preprocess data for DeepSensor.
- Train or load a forecasting model.
- Generate forecast outputs.
- Evaluate forecasts.
- Create output directories.
- Provide operation modes such as `train`, `forecast`, or `evaluate`.

The database update mode is available through both
`run_aqforecast(mode="database_update")` and
`aqforecast.orchestration.run_database_update()`.

These stages will be added as their respective systems are implemented. The
runner will remain the high-level orchestration entry point, while directory
creation will be handled by a separate setup utility.

## Tests

Activate the project environment before running tests:

```bash
conda activate chemml
```

Run the configuration, credential-management, and runner tests with:

```bash
python -m pytest tests/
```
