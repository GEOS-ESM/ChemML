# ChemML Configuration

ChemML uses `config/default_config.yaml` as the entry point for a collection of component configuration files. This organization keeps region definitions, data locations, model settings, forecasting choices, and validation choices independent and reusable.

> The configuration system is currently a draft. A general loader that resolves references into one runtime configuration is planned. The repository now includes a validator for the current schema, but several settings will be refined as the ingest, DeepSensor, forecasting, and validation systems are developed.

## Configuration layout

```text
config/
├── default_config.yaml
├── aqforecast/aqforecast_config.yaml
├── credentials/credentials.yaml
├── credentials/credentials_template.yaml
├── deepsensor/deepsensor_config.yaml
├── filepaths/filepaths.yaml
├── filepaths/filepaths_template.yaml
├── inputs/input_data_config.yaml
├── regions/example_region.yaml
├── regions/region_template.yaml
└── validation/validation_config.yaml

aqforecast/
└── config_management/
    ├── __init__.py
    └── configuration.py
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
from aqforecast.config_management.configuration import check_configuration

report = check_configuration("config/default_config.yaml", mode="check")
if not report.is_valid:
    print(report.format())
```

Checking mode does not require the git-ignored credentials file or real credentials; those are reported as warnings. Interactive mode requires credentials by default. This can also be controlled explicitly with the API using `require_credentials=True` or `False`.

The repository regression test runs the default configuration through the checker:

```bash
pytest tests/test_configuration.py
```

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

## Filepaths

`config/filepaths/filepaths.yaml` owns machine-specific paths. Use `filepaths_template.yaml` when configuring another machine. `roots.input` and `roots.output` define the high-level locations; working-directory templates use `{input}`, `{output}`, `{region_code}`, and `{experiment_name}`.

Each data source is stored below its region-code directory, using the source name as the subfolder:

```yaml
data_sources:
  ground_monitors: "{input}/{region_code}/ground_monitors"
  GEOS-CF: "{input}/{region_code}/GEOS-CF"
  TEMPO: "{input}/{region_code}/TEMPO"
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

Detailed definitions currently exist for `ground_monitors`, `GEOS-CF`, `TROPOMI`, `GEMS`, `GCAS`, and `land_cover`. `TEMPO`, `PACE`, `VIIRS`, and `GOES-ABI` are placeholder categories to be completed as their data-ingest and preprocessing code is developed.

## Air-quality forecasting configuration

`config/aqforecast/aqforecast_config.yaml` selects inputs and owns forecast behavior. Its current settings include:

- Enabled input categories and whether ground monitors are used as context.
- The ground-monitor training fraction.
- Forecast lead times of 1, 3, 6, 12, 24, 48, and 72 hours.
- Output variables `pm25`, `o3`, and `no2`.
- Confidence levels of 50% and 90%.
- Optional input lags and additional features, currently including `time_of_day`.

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

- A general runtime configuration loader is not yet implemented; the current validator checks the known schema without merging files.
- `ASIAAQ_Deepsensor_Run.py` still reads legacy JSON settings and hard-coded paths.
- Several source definitions and model settings are placeholders.
- File templates must be reconciled with the actual outputs of future ingest codes.
