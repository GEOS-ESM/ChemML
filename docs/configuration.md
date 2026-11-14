# ChemML Configuration

ChemML uses `config/default_config.yaml` as the entry point for a collection of component configuration files. This organization keeps region definitions, data locations, model settings, forecasting choices, and validation choices independent and reusable.

> The configuration system includes a validator and runtime loader that resolve the master configuration into a dictionary. The schemas and downstream consumers remain provisional as the ingest, DeepSensor, forecasting, and validation systems are developed.

## Configuration layout

```text
config/
├── default_config.yaml
├── aqforecast/
│   └── aqforecast_config.yaml
├── credentials/
│   ├── credentials.yaml
│   └── credentials_template.yaml
├── deepsensor/
│   └── deepsensor_config.yaml
├── filepaths/
│   ├── filepaths.yaml
│   └── filepaths_template.yaml
├── inputs/
│   └── input_data_config.yaml
├── regions/
│   ├── example_region.yaml
│   └── region_template.yaml
└── validation/
    └── validation_config.yaml
```

Only `default_config.yaml` is the master entry point. Its `configuration_files` mapping references files relative to the `config` directory:

```yaml
configuration_files:
  region: "regions/example_region.yaml"
  credentials: "credentials/credentials.yaml"
  filepaths: "filepaths/filepaths.yaml"
  deepsensor: "deepsensor/deepsensor_config.yaml"
  aqforecast: "aqforecast/aqforecast_config.yaml"
  validation: "validation/validation_config.yaml"
  input_data: "inputs/input_data_config.yaml"
```

The master file also defines `config_version`, `experiment_code`, and the experiment-name template. The current template uses `{region_code}` and `{experiment_code}`.

## Checking configuration files

`aqforecast/config_management/configuration.py` provides the reusable `check_configuration()` function and a command-line interface. It follows the references in a selected master file and checks the referenced YAML files for required settings, valid types, source-key consistency, path-template structure, and deferred dataset definitions.

Run read-only checking mode with:

```bash
python aqforecast/config_management/configuration.py config/default_config.yaml
```

Use `--check-paths` when the configured input and output roots should also be required to exist. The command returns exit code 0 when there are no errors and exit code 1 when errors remain. Deferred sources that contain only their `source_key` are reported as warnings until their ingest and preprocessing settings are implemented.

Interactive mode prompts for fixable missing or invalid values and writes accepted values to the owning YAML file:

```bash
python aqforecast/config_management/configuration.py config/default_config.yaml --interactive
```

The Python API returns a `ConfigurationReport` with `errors`, `warnings`, `changed_files`, and an `is_valid` property:

```python
from aqforecast.config_management.configuration import check_configuration, load_configuration

report = check_configuration("config/default_config.yaml", mode="check")
if not report.is_valid:
    print(report.format())
```

Checking mode does not require the git-ignored credentials file or real credentials; those are reported as warnings. Interactive mode requires credentials by default. This can also be controlled explicitly with the API using `require_credentials=True` or `False`.

The repository regression test runs the default configuration through the checker:

```bash
pytest tests/test_configuration.py
```

## Loading configuration at runtime

`load_configuration()` uses the same validation rules and returns a single dictionary containing the component configurations:

```python
from aqforecast.config_management.configuration import load_configuration

configuration = load_configuration("config/default_config.yaml")
experiment_name = configuration["experiment_name"]
tropomi_path = configuration["filepaths"]["data_sources"]["TROPOMI"]
```

The loader resolves `{region_code}`, `{experiment_code}`, `{experiment_name}`, `{input}`, and `{output}` where those values are known. Dataset filename placeholders such as `{month_string}` remain unresolved for the ingest code to fill later.

Missing credentials and nonexistent configured paths are returned in `configuration["warnings"]` and do not stop loading. Structural errors, missing non-credential references, malformed values, and conflicting source definitions raise `ConfigurationError`. The loader does not create directories; a separate setup utility will own that responsibility.

The high-level `run_aqforecast()` function can request credential checking by
passing `require_credentials=True`. It loads the configuration first so the
credential manager can locate the configured credentials file, then saves and
revalidates the credentials before continuing.

The runtime loader is integrated with `run_aqforecast()`. The new runner uses
the resolved configuration dictionary; the older example runner remains a
separate legacy workflow that uses JSON settings and hard-coded paths.

## Region configuration

Region files live in `config/regions/`. Copy `region_template.yaml` to create a new region. A region file owns:

- `region_code` and the human-readable `name`.
- Inclusive latitude and longitude `bounds` in decimal degrees.
- The target output-grid resolution.
- The ground-monitoring `provider`.
- The top-level IANA `timezone`.

Latitude and longitude coordinate names default to `lat` and `lon` and are not repeated in the region file.

The current example is:

```yaml
region_code: "Seoul"
name: "Seoul metropolitan area"
bounds:
  latitude: [36.0, 38.0]
  longitude: [126.0, 128.0]
output_grid:
  resolution_degrees: 0.01
ground_monitoring:
  provider: "AirKorea"
timezone: "Asia/Seoul"
```

## Credentials

Copy `config/credentials/credentials_template.yaml` to `config/credentials/credentials.yaml` and fill it in locally:

```bash
cp config/credentials/credentials_template.yaml config/credentials/credentials.yaml
```

The template contains NASA Earthdata, OpenAQ, AirNow, and NCCS credential fields. `credentials.yaml` is ignored by Git and must never be committed or written to logs.

Credential collection is available through `manage_credentials()`:

```python
from aqforecast.config_management import manage_credentials

result = manage_credentials("config/default_config.yaml")
```

The function uses `load_configuration()` to locate the credentials file,
prompts for missing required values, performs local validation, and writes the
accepted values with restrictive file permissions. OpenAQ and AirNow are
optional unless `prompt_optional=True` is used. Remote verification is opt-in:

```python
result = manage_credentials(
    "config/default_config.yaml",
    verify_remote=True,
)
```

Remote verification requires internet access. Earthdata is checked with
`earthaccess` when available, with a direct HTTPS fallback; OpenAQ and AirNow
are checked through authenticated requests. Transiently unverified checks are
retried. NCCS access is reported as not checked because it must be verified
from the NCCS environment.

## Filepaths

`config/filepaths/filepaths.yaml` owns machine-specific paths. Use `filepaths_template.yaml` when configuring another machine. `roots.input` and `roots.output` define the high-level locations; working-directory templates use `{input}`, `{output}`, `{region_code}`, and `{experiment_name}`.

Each data source is stored below its region-code directory, using the source name as the subfolder:

```yaml
data_sources:
  ground_monitors: "{input}/{region_code}/ground_monitors"
  GEOS-CF: "{input}/{region_code}/GEOS-CF"
  TEMPO_NO2: "{input}/{region_code}/TEMPO_NO2"
  TEMPO_O3: "{input}/{region_code}/TEMPO_O3"
  GEMS: "{input}/{region_code}/GEMS"
  TROPOMI: "{input}/{region_code}/TROPOMI"
  PACE: "{input}/{region_code}/PACE"
  VIIRS: "{input}/{region_code}/VIIRS"
  land_cover: "{input}/{region_code}/land_cover"
  GCAS: "{input}/{region_code}/GCAS"
  GOES-ABI: "{input}/{region_code}/GOES-ABI"
```

Source names are case-sensitive and must match `source_key` values in `input_data_config.yaml`. File names are owned by the input-data configuration, not by this file.

## Input-data configuration

`config/inputs/input_data_config.yaml` describes how datasets are loaded and prepared. Each configured dataset can define:

- `source_key`, which links it to a filepath source.
- `file_template` and filename placeholders such as `{region_code}`, `{month_string}`, `{date_string}`, or `{year_string}`.
- Variables to load and an optional `variable_prefix`.
- Source coordinate names and timestamp handling.
- Regridding method and source resolution.
- `storage.partition` (`daily`, `monthly`, or `yearly`) and `storage.format`
  (`csv` for point data or `netcdf` for gridded data).
- `access.mode` (`local` or `remote`) and a per-source `.tmp` staging folder.
- `time.availability`, which supports continuous timestamps or configured
  daily observation windows. The initial GEMS and GCAS defaults assume 08:00
  through 17:00 in the configured local region timezone and can be revised by
  their source adapters.

The database manager stores timestamps in UTC and treats update intervals as
half-open (`[start_time, end_time)`). Existing files are checked for expected
timestamps before acquisition. Missing timestamps trigger a registered source
adapter, after which processed data are merged using the default
`fill_missing` policy. A regenerated `catalog.json` in each source directory
records the files found, time coverage, variables, dimensions, and spatial
extent; configuration remains authoritative.

Detailed definitions currently exist for `ground_monitors`, `GEOS-CF`, `TROPOMI`, `GEMS`, `TEMPO_NO2`, `TEMPO_O3`, `GCAS`, and `land_cover`. `PACE`, `VIIRS`, and `GOES-ABI` are placeholder categories to be completed as their data-ingest and preprocessing code is developed.

## Air-quality forecasting configuration

`config/aqforecast/aqforecast_config.yaml` selects inputs and owns forecast behavior. Its current settings include:

- Enabled input categories and whether ground monitors are used as context.
- The ground-monitor training fraction.
- Forecast lead times of 1, 3, 6, 12, 24, 48, and 72 hours.
- Output variables `pm25`, `o3`, and `no2`.
- Confidence levels of 50% and 90%.
- Optional input lags and additional features, currently including `time_of_day`.
- Database update defaults, including the `fill_missing` conflict policy.

This file should be kept synchronized with the forecasting implementation as its required settings are defined.

## DeepSensor configuration

`config/deepsensor/deepsensor_config.yaml` owns DeepSensor/PyTorch settings:

- ConvNP model architecture and U-Net channel sizes.
- Data-processor coordinate names and normalization methods.
- Task-loader context and target sampling.
- Learning rate, maximum epochs, task stride, and best-model saving.

The file is an initial draft and should be revisited during Phase 4 when the DeepSensor wrapper, training, inference, and model-versioning systems are implemented.

## Validation configuration

`config/validation/validation_config.yaml` owns validation settings. It currently defines spatial cross-validation by monitoring site, optional temporal/month splits, forecast validation, and the comparison baselines:

```yaml
baseline_models:
  - "GEOS-CF"
  - "diel_cycle"
  - "persistence"
```

Configured metrics include bias, MAE, RMSE, Pearson correlation, overall/spatial/temporal R², normalized-residual diagnostics, and confidence-interval coverage. Validation is stratified by hour of day and monitoring site. Plot categories include prediction and uncertainty maps, observation overlays, hourly metrics, residual histograms, and context-sensitivity maps.

This file should be kept up to date as the Phase 5 validation system, baseline implementations, metrics, and plots are built out.

## Configuration ownership

| File | Owns |
| --- | --- |
| `default_config.yaml` | Experiment identity and component-file references |
| `regions/*.yaml` | Region identity, bounds, output resolution, provider, and timezone |
| `credentials/credentials.yaml` | Local credentials and account identifiers |
| `filepaths/filepaths.yaml` | Machine-specific roots and source directories |
| `inputs/input_data_config.yaml` | Dataset files, variables, timestamps, coordinates, and regridding |
| `aqforecast/aqforecast_config.yaml` | Input selection, forecast outputs, lags, and features |
| `deepsensor/deepsensor_config.yaml` | DeepSensor model, processing, task-loader, and training settings |
| `validation/validation_config.yaml` | Cross-validation, baselines, metrics, stratifications, and plots |

Keep each setting in its owning file rather than duplicating it across configurations.

## Current limitations

- The new runtime loader is not yet integrated with the legacy example runner; new runners will consume the loaded dictionary directly.
- `ASIAAQ_Deepsensor_Run.py` still reads legacy JSON settings and hard-coded paths.
- Several source definitions and model settings are placeholders.
- File templates must be reconciled with the actual outputs of future ingest codes.
