# ChemML Configuration

ChemML uses `config/default_config.yaml` as the entry point for a collection of component configuration files. This organization keeps region definitions, data locations, model settings, forecasting choices, and validation choices independent and reusable.

> The configuration system includes a validator and runtime loader that resolve the master configuration into a dictionary. The schemas and downstream consumers remain provisional as the ingest, DeepSensor, forecasting, and validation systems are developed.

## Configuration layout

```text
config/
├── default_config.yaml
├── aqdatafusion/
│   └── aqdatafusion_config.yaml
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
  aqdatafusion: "aqdatafusion/aqdatafusion_config.yaml"
  validation: "validation/validation_config.yaml"
  input_data: "inputs/input_data_config.yaml"
```

The master file also defines `config_version`, `experiment_code`, and the experiment-name template. The current template uses `{region_code}` and `{experiment_code}`.

## Validation and runtime loading

The configuration-management module validates the master file and all referenced
component files, then resolves them into one runtime configuration mapping.
Validation and setup commands are documented in the
[Installation Guide](installation.md), while runtime use is documented in the
[User Guide](user_guide.md). The validator checks required fields, value types,
source-key consistency, path templates, and references between component
files. It reports missing credentials and paths as warnings when appropriate.

The loader resolves `{region_code}`, `{experiment_code}`, `{experiment_name}`,
`{input}`, and `{output}` where those values are known. Dataset filename
placeholders such as `{month_string}` remain unresolved for the ingest code to
fill later. Loading does not create directories or acquire data.

## Region configuration

Region files live in `config/regions/`. A region file owns:

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

The credentials template defines NASA Earthdata, OpenAQ, AirNow, and NCCS
credential fields. The local credentials file is ignored by Git and must never
be committed or written to logs.

Credential collection, local validation, and optional remote verification are
described in the [Installation Guide](installation.md). Earthdata, OpenAQ,
AirNow, and NCCS credentials must be stored securely; the local credentials
file is ignored by Git and credential values must not appear in logs.

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
  through 17:00 in the configured local region timezone; those sources are
  deferred future work and their settings can be revised when adapters are
  developed.
- Point-data sources may define `site_id` and
  `site_coordinate_tolerance`. These identify the stable site column and the
  maximum allowed coordinate difference for generic site-coordinate checks.
- `ground_monitoring.provider` selects the ground-data provider. Regions with
  provider `AirNow` or `OpenAQ` automatically use the corresponding ChemML
  acquisition and preprocessing implementations. Only one ground-monitor
  provider is active for a region; other providers require their own registered
  adapters.

The input-data configuration is authoritative for source schemas, timestamp
conventions, storage partitions, access modes, quality-control defaults, and
regridding settings. Source behavior and preprocessing details are summarized
in [docs/data_sources.md](data_sources.md); update commands and database
semantics are described in [docs/user_guide.md](user_guide.md).

## Air-quality data-fusion configuration

`config/aqdatafusion/aqdatafusion_config.yaml` selects inputs and owns forecast behavior. Its current settings include:

- Enabled input categories and whether ground monitors are used as context.
- The ground-monitor training fraction.
- Forecast lead times of 1, 3, 6, 12, 24, 48, and 72 hours.
- Output variables `pm25`, `o3`, and `no2`.
- Confidence levels of 50% and 90%.
- Optional input lags and additional features, currently including `time_of_day`.
- Database update defaults, including the `fill_missing` conflict policy.
- Rolling database-update windows, including lookback/lookahead durations,
  UTC hourly alignment, and a maximum-window safeguard.
- Operational report retention, configured by
  `database.operational_logging.retain_days` (365 days by default). Reports
  are written beneath the resolved `filepaths.working.logs_directory`.
- The logging prefix, configured by `logging.prefix` (`aqdatafusion` by
  default). This controls the default logger namespace.
- The default log filename is derived from the resolved
  `experiment_name_template` as `<experiment_name>_log.log`. An explicit
  `log_filename` passed to `configure_logging()` still overrides this default.

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
| `aqdatafusion/aqdatafusion_config.yaml` | Input selection, forecast outputs, lags, and features |
| `deepsensor/deepsensor_config.yaml` | DeepSensor model, processing, task-loader, and training settings |
| `validation/validation_config.yaml` | Cross-validation, baselines, metrics, stratifications, and plots |

Keep each setting in its owning file rather than duplicating it across configurations.
Runtime behavior and command examples belong in the [User Guide](user_guide.md);
first-time setup belongs in the [Installation Guide](installation.md).
Deferred source and model settings remain provisional until their
implementations are developed.
