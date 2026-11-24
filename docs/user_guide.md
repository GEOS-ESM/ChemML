# ChemML User Guide

ChemML is under active development. Configuration validation, bounded and
incremental input-data database updates, operational reports, and scheduler
support are available. AirNow, OpenAQ, TROPOMI, VIIRS, PACE, TEMPO, MCD12Q1,
and GOES-ABI acquisition and preprocessing paths are implemented; GEOS-CF
ingestion is developed. See [PROJECT.md](../PROJECT.md) for
implementation-testing status. Model training, forecasting,
and result evaluation remain under development.

## Validate a configuration

Run the configuration checker before a run:

```bash
python aqdatafusion/config_management/configuration.py config/default_config.yaml
```

Checking mode reports structural errors and warnings without modifying files.
Missing credentials and nonexistent configured paths are warnings unless
credentials are explicitly required.

Interactive mode prompts for fixable missing or invalid values:

```bash
python aqdatafusion/config_management/configuration.py \
    config/default_config.yaml --interactive
```

If credentials are needed, collect them separately with
`manage_credentials()` as described in the configuration reference. Credential
verification is optional and remote verification requires internet access.

## Run the current AQ-data-fusion skeleton

The runner is exposed as `run_aqdatafusion()`:

```python
from aqdatafusion import run_aqdatafusion

result = run_aqdatafusion("config/default_config.yaml")
print(result["status"])
print(result["message"])
```

When a run needs credentials, request credential collection and verification:

```python
result = run_aqdatafusion(
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
result = run_aqdatafusion(
    "config/default_config.yaml",
    mode="database_update",
    start_time="2026-08-04T00:00:00Z",
    end_time="2026-08-08T00:00:00Z",
    source_keys=["ground_monitors"],
    require_credentials=True,
)
print(result["report"])
```

To update the configured rolling window around the current UTC hour, use the
incremental mode. It does not require explicit start or end times:

```python
result = run_aqdatafusion(
    "config/default_config.yaml",
    mode="incremental_database_update",
    source_keys=["GEOS-CF", "ground_monitors"],
    require_credentials=True,
)
print(result["report"])
```

The rolling window is controlled by `database.incremental_update` in
`config/aqdatafusion/aqdatafusion_config.yaml`. The example configuration looks
back two days and forward five days, aligned to the current UTC hour, and
rejects windows longer than 14 days. A cron or NCCS wrapper can invoke this
mode at the desired cadence; the repository includes a Bash scheduler
entry point described below.

## Update the input-data database

Database updates use a half-open UTC interval, `[start_time, end_time)`. By
default, every input marked `enabled: true` in
`config/aqdatafusion/aqdatafusion_config.yaml` is checked. Existing partitioned
files are inspected for expected timestamps, missing intervals are requested
from the registered source adapters, processed data are merged using the
`fill_missing` policy, and each source catalog is regenerated.

The update operation can be started from Python after loading the resolved
configuration:

```python
from aqdatafusion.config_management.configuration import load_configuration
from aqdatafusion.orchestration import run_database_update

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
from aqdatafusion.config_management.configuration import load_configuration
from aqdatafusion.orchestration import run_database_update

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
Built-in acquisition and preprocessing adapters are selected through the
`SourceRegistry`. Custom registries can be passed to `DatabaseManager`, while
explicit `data_sources` and `preprocessors` mappings continue to override the
registered defaults.
Each update also returns an `integrity` section for every selected source.
Availability gaps appear as warnings; malformed partitions, duplicate records,
grid/schema mismatches, and catalog inconsistencies mark that source as failed.
To check an existing database without acquiring data, use
`DatabaseManager.verify_database_integrity(source_key)`.

For a scheduled rolling update, call `run_incremental_database_update()`:

```python
from aqdatafusion.orchestration import run_incremental_database_update

report = run_incremental_database_update(configuration)
```

The function reads `database.incremental_update` from the AQ-data-fusion
configuration, aligns the system time to the UTC hour, and updates the
configured lookback/lookahead window. `max_window_days` rejects accidentally
oversized requests. Scheduling is intentionally left to cron or an NCCS batch
wrapper; there is no enable/disable flag in the Python configuration.

Every explicit or rolling database update also writes a human-readable report
under the configured `filepaths.working.logs_directory`. Reports are named with
the operation and UTC run-start time, for example
`incremental_database_update_20261118T190000.000000Z.txt`. The returned report
contains the generated path under `operational_report_path`. Reports older than
`database.operational_logging.retain_days` are removed during a later update;
the default retention period is 365 days. Cleanup only targets these
per-operation text reports and does not remove the general experiment log.
Each source result also records its elapsed wall time in seconds, both in the
structured report and in the source summary section of the text report.

### Schedule rolling database updates

The repository includes `scripts/update_database_incremental.sh` as a
scheduler entry point. It activates the `chemml` Conda environment and runs
`run_aqdatafusion(mode="incremental_database_update")` with credential checking
enabled. It uses `config/default_config.yaml` by default; edit the
`CONFIG_PATH` line in the script to select another master configuration.

Make the script executable and test it manually before scheduling it:

```bash
chmod +x scripts/update_database_incremental.sh
scripts/update_database_incremental.sh
```

For example, a daily cron entry from the repository root could be:

```cron
15 2 * * * /path/to/ChemML/scripts/update_database_incremental.sh >> /path/to/ChemML/cron.log 2>&1
```

The script exits with status 1 when the update reports failures and status 2
when Conda is unavailable. Detailed per-run reports are written to the
configured `logs_directory`; cron installation and scheduler-specific setup
remain operator responsibilities.

For configuration-only mode, a valid `run_aqdatafusion()` result contains:

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

The current operational workflow covers configuration and input-data database
updates. DeepSensor conditioning, model training, forecasting, and validation
are not yet implemented. See [PROJECT.md](../PROJECT.md) for implementation-
testing status and remaining validation work.

## Tests

Activate the project environment before running tests:

```bash
conda activate chemml
```

Run the configuration, credential-management, and runner tests with:

```bash
python -m pytest tests/
```
