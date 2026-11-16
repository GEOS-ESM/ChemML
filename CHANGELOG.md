# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- **16 November 2026**: Add standard PACE OCI trace-gas acquisition,
  quality-variable filtering, 0.02-degree regridding, daily aggregation,
  database integration, configuration, documentation, and tests.
- **16 November 2026**: Add VIIRS/JPSS2 VJ219A2 version-002 AOD acquisition,
  moderate quality filtering, RSIN geolocation, 0.01-degree regridding, daily
  aggregation, database integration, configuration, documentation, and tests.
- **14 November 2026**: Expose database updates through `run_aqforecast()`, add generic point-site
  coordinate validation and structured acquisition diagnostics, and make
  AirNow concentration bounds configurable.
- **14 November 2026**: Add OpenAQ v3 ground-monitor acquisition,
  preprocessing, sensor reconciliation, provider registration, and mocked API
  tests.
- **14 November 2026**: Add configurable OpenAQ request pacing and select
  OpenAQ for the example Seoul region.
- Document the AirNow ingest and correct the agent implementation-notes path.

### Added
- **13 November 2026**: Added the incremental input-data database manager,
  regenerable per-source catalogs, local/remote acquisition adapter contracts,
  generic preprocessing support, and database-update orchestration mode.
- **1 October 2025**: Added several notebooks and scripts related to running the DeepSensor workflow on Discover for analysis of data from the ASIA-AQ campaign.

### Changed

### Fixed

### Removed

### Deprecated

