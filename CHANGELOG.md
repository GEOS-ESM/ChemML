# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and releases follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Incremental partitioned input-data database management with per-source
  catalogs and integrity verification.
- AirNow, OpenAQ, VIIRS, TROPOMI, PACE, TEMPO NO₂/O₃ Profiles, MCD12Q1,
  GOES-ABI, and developed GEOS-CF acquisition/preprocessing paths.
- Authenticated NASA Earthdata DAP4/OpenDAP access through xarray and pydap,
  including resumable TEMPO subset caching and chunked GEOS-CF access.
- Rolling database-update mode with configurable lookback, lookahead, and
  maximum-window safeguards.
- Human-readable per-run database-update reports with configurable retention.
- Per-source wall-time measurements in database-update reports.
- Adapter registry supporting lazy built-in registration, custom registries,
  and explicit adapter overrides.
- `scripts/update_database_incremental.sh` for Conda-based cron or NCCS
  scheduler integration.
- Configuration management, credential handling, shared regridding, and
  network-free regression and integration fixtures.
- A database-acquisition example notebook, public database reading, and shared
  offline-safe Cartopy plotting with first-time Natural Earth layer caching.

### Changed

- `run_aqdatafusion()` now supports explicit and rolling database-update modes.
- Source-specific adapter registration moved from `DatabaseManager` into a
  reusable registry.
- Database updates now keep partitions from older filename/grid families out of
  active merges, retain them with warnings, and allow configured GEOS-CF
  missing variables to be reported as availability warnings.
- Point-monitor merges now normalize site IDs and let newer records replace
  older records with the same site ID and timestamp.
- Documentation was organized by audience across the README, agent guidance,
  roadmap, configuration reference, data-source reference, installation guide,
  and user guide.

### Fixed

- Timestamp normalization, monthly/yearly partition boundaries, leap-year
  handling, duplicate merging, coordinate consistency, and catalog validation.
- Operational cleanup now removes only expired per-run reports and preserves
  the general application log.

### Removed

### Deprecated

## Versioning notes

No public release has been cut yet. Future release entries should use a
version heading such as `## [0.1.0] - YYYY-MM-DD` and move the corresponding
items out of `Unreleased`.
