# ChemML User Guide

ChemML is under active development. The current public workflow entry point is
an initial runner that loads and validates the selected configuration. The
incremental input-data database update mode is available as a standalone
orchestration operation. AirNow ground-monitor acquisition and preprocessing
are implemented; other source-specific acquisition, model training,
forecasting, and result evaluation remain under development.

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

### Update an AirNow database

For a region whose configuration sets
`region.ground_monitoring.provider: AirNow`, the database manager registers the
AirNow acquisition and preprocessing implementations automatically. Use the
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

The default behavior fills missing timestamps and values while preserving
existing data. Use `conflict_policy="replace_partition"` or
`override=True` only when an affected partition should be replaced. AirNow is
registered automatically for AirNow regions. Other dataset-specific
`LocalDataSource` or `RemoteDataSource` adapters must be registered with
`DatabaseManager`/`run_database_update` until their implementations are
completed; unavailable sources are reported without silently fabricating data.

Database files are stored using the partition and format configured in
`config/inputs/input_data_config.yaml`: NetCDF for gridded data and CSV for
point data. Temporary downloads and staged writes use a per-run `.tmp`
directory, which is cleaned after the update. A regenerated `catalog.json` is
written in each source directory as a confirmation of the files on disk.

For a valid configuration without credential checking, the current
`run_aqforecast()` result contains:

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

The high-level `run_aqforecast()` runner does not currently:

- Start the database-update operation automatically.
- Download or discover input data as part of `run_aqforecast()`.
- Preprocess data for DeepSensor.
- Train or load a forecasting model.
- Generate forecast outputs.
- Evaluate forecasts.
- Create output directories.
- Provide operation modes such as `train`, `forecast`, or `evaluate`.

The database update mode is currently invoked through
`aqforecast.orchestration.run_database_update()` rather than through
`run_aqforecast()`.

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
