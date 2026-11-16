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

## TROPOMI

TROPOMI is the first implemented satellite-data ingest. The adapter searches
NASA Earthdata for the version-2 high-resolution collections
`S5P_L2__NO2____HiR` and `S5P_L2__O3_TOT_HiR`, using the configured UTC interval
and region bounding box. Earthdata credentials are read from the resolved
`credentials.earthdata` configuration. Native granules are swath NetCDF-4
files; the collection short name appears in Earthdata collection/path
metadata, while native filenames use the standard `S5P_OFFL_L2__...` convention.

The preprocessor reads the science and support-data groups and applies the
configured moderate-quality filter before aggregation: `qa_value > 0.5`, cloud
fraction `< 0.5`, solar zenith angle `< 80°`, tropospheric NO₂ greater than
`-5e-5 mol m⁻²`, and total-column O₃ between `0.05` and `0.25 mol m⁻²`.

Valid swath pixels are regridded with the shared irregular-point regridder to
cell-centered 0.05° latitude/longitude cells. Each day is averaged after
regridding; when multiple overpasses are available, the UTC timestamp centered
on the hour containing the most valid source pixels represents that day. The
standardized variables are `tropospheric_no2_column` and `total_o3_column`.
Both variables are combined in the same monthly NetCDF partition and managed
by the generic database manager. Daily completeness and merges compare
calendar dates rather than exact overpass timestamps.

The ATL integration tests ingested August 4–12, 2026, into
`TROPOMI_ATL_202608_grid_005_d.nc` with a regenerated source catalog.
