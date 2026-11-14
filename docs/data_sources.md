# ChemML Data Sources

This document records how each configured source is acquired, normalized, and
stored in the ChemML input-data database. Source-specific API and file-format
handling lives in acquisition adapters; common validation, merging,
partitioning, and catalog generation live in the database manager.

## AirNow

AirNow is one of the implemented ground-monitor ingests. The adapter queries
the AirNow API for the configured region's geographic bounding box and the
requested pollutants (PM2.5, PM10, NO2, O3, SO2, and CO). Requests are made in
bounded hourly chunks and use the configured AirNow API key. Returned AQS
station codes are retained as the stable ChemML `site_id` after preprocessing.

AirNow timestamps are interpreted as UTC source-hour timestamps and shifted to
the midpoint of the hour. Gaseous concentrations reported in PPM are converted
to PPB where needed. The preprocessor applies the configurable minimum and
maximum concentration limits in `config/inputs/input_data_config.yaml`; values
outside those limits, including negative values, are replaced with missing
values. Temporary source unit columns are removed before the standardized
point-data CSV partitions are merged into the database.

## OpenAQ

OpenAQ is the alternative ground-monitor provider. Each region selects either
OpenAQ or AirNow through `region.ground_monitoring.provider`; both providers
use the shared `ground_monitors` configuration and archive schema, and are not
acquired simultaneously for the same region.

The OpenAQ adapter discovers locations inside the configured geographic bounds
through the OpenAQ v3 `/locations` endpoint. It then queries the
sensor-specific `/sensors/{sensor_id}/measurements` endpoint using the
requested half-open UTC interval. Source measurement periods are converted to
midpoint-of-period UTC timestamps. Location IDs become the stable ChemML
`site_id` values, while coordinates are retained from the location metadata.

OpenAQ PM2.5 and PM10 values are standardized to µg/m³. Trace gases are
standardized to ppb: ppm values are multiplied by 1000, and trace-gas µg/m³
values use the documented molecular-weight conversion at 25°C and one
atmosphere. The same configurable per-pollutant minimum and maximum bounds are
then applied to OpenAQ and AirNow data.

When multiple OpenAQ sensors report the same site, pollutant, and timestamp,
valid values fill missing values from another sensor. Equal valid values are
accepted without warning. Conflicting valid values produce a structured
warning, and the value from the sensor with the highest ID is retained. The
preprocessed result is written as the shared standardized point-data CSV
database and handled by the generic database manager.
