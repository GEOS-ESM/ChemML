# ChemML Data Sources

This document records how each configured source is acquired, normalized, and
stored in the ChemML input-data database. Source-specific API and file-format
handling lives in acquisition adapters; common validation, merging,
partitioning, and catalog generation live in the database manager.

## AirNow

AirNow is the first implemented source-specific ingest. The adapter queries
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
