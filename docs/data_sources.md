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

The adapter searches
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


## VIIRS/JPSS2 VJ219A2 aerosol optical depth

ChemML acquires the VIIRS/JPSS2 Land Aerosol Optical Depth Daily L2G Global
750 m RSIN Grid V002 product through NASA Earthdata using `earthaccess`.
The configured collection is `VJ219A2`, version `002` (concept ID
`C2885060488-LPCLOUD`). The adapter searches granules for the configured
region and UTC interval, and the database manager stores monthly NetCDF output.

The preprocessor reads `Optical_Depth_055`, converts granule-specific RSIN
geolocation to latitude/longitude, and applies the configured moderate filter:
valid AOD values from 0 through 6 and `AOD_QA & 3 <= 1`. Valid 750 m pixels
are averaged onto the 0.01-degree target grid before daily aggregation.

## PACE OCI trace gases

ChemML accesses `PACE_OCI_L2_TRGAS` through `earthaccess`. The preprocessor
reads `total_column_no2` and `total_column_o3` with their binary quality
variables. Only quality value 0 pixels are retained; values are averaged onto
a 0.02-degree grid before daily aggregation, with the UTC timestamp centered
on the overpass hour containing the most valid data.

## TEMPO NO₂

ChemML accesses `TEMPO_NO2_L3` (`C3685896708-LARC_CLOUD`) through NASA
Earthdata. Granules are found with `earthaccess`, while regional subsets are
read through authenticated DAP4/OpenDAP using xarray and pydap. The product
variables `vertical_column_troposphere` and `main_data_quality_flag` are
loaded using coordinate-derived native index slices.

Finite science values with `main_data_quality_flag <= 1` are retained,
including negative NO₂ values. The native approximately 0.02-degree grid is
preserved, duplicate granules in an hour are averaged, and timestamps are UTC
and centered on the hour. Subsets are cached under the source `.tmp` directory
for interruption recovery and removed after successful database storage.

## TEMPO O₃ Profile

ChemML accesses `TEMPO_O3PROF_L3` (`C3685896402-LARC_CLOUD`) through
authenticated DAP4/OpenDAP. `ozone_profile` is read from `product`,
`eff_cloud_fraction` from `support_data`, and the solar and viewing zenith
angles from `geolocation`.

The configurable `profile_layers` setting uses 1-indexed names while the
source layer dimension is zero-indexed. Thus `profile_layers: [24]` selects
source index 23, the lowest approximately 0–2 km layer, and produces
`ozone_profile_layer_24`. Multiple configured layers produce corresponding
variables. QC removes non-finite/fill-value data, cloud fractions above 0.5,
and solar or viewing zenith angles above 80°. The native approximately 0.04°
grid is preserved, duplicate hourly granules are averaged, and cached subsets
are removed after successful storage.

## MCD12Q1 land cover

ChemML accesses the MODIS/Terra+Aqua MCD12Q1 Collection 6.1 yearly land-cover
product through `earthaccess`. The adapter searches for the requested calendar
year and, when no granules are available, tries preceding years up to the
configured `access.max_year_fallback` limit. A fallback is recorded in the
NetCDF attributes so the source year remains auditable.

MCD12Q1 HDF4 tiles provide `LC_Type1` on a native 500 m sinusoidal grid. The
preprocessor converts the native projection to latitude/longitude and uses
categorical mode aggregation on the configured 0.005-degree grid. `LW` and
`QC` values are read for quality-control support, but their filters are
disabled by default with bounds spanning the full byte range. The output
timestamp is January 1 of the actual source year, including when an earlier
year was used as a fallback. Yearly completeness recognizes configured
fallback source years, and the generic database manager writes yearly NetCDF
partitions and catalogs.

## GEOS-CF

GEOS-CF v2 is acquired from the public unauthenticated OpenDAP service with
xarray and pydap. The adapter reads analysis data and available dated forecast
initializations for the configured interval, using the AQC, MET, and XGC
collections selected in `input_data_config.yaml`; CHM PM-speciation fields are
optional. Requests are subset to the configured region and time interval on
the native 0.25-degree grid, split into configurable time and variable chunks,
and retried when transient collection requests fail.

The preprocessor decodes the service's raw year-1 time coordinate using GrADS
timestamp metadata, normalizes valid times to UTC center-of-hour timestamps,
retains finite values, and replaces NaN or infinite values with missing data.
Analysis and forecast records are combined with a `forecast_lead_day`
dimension: analysis is 0 and forecast lead days are 1–5. Forecast dates absent
from the public rolling archive are reported as warning gaps without stopping
other available data. Scientific valid-range filters beyond finite-value
handling remain to be added.

The default access mode is OpenDAP (`access.mode: "remote"`). On NCCS, switch
to `access.mode: "local"` and provide `access.local_root` for the operational
GEOS-CF v2 tree. The local adapter searches configured stream/date directories
for selected collection files, including `.nc4` and compressed layouts. The
local NCCS path has not yet received an end-to-end ChemML database test.

The adapter has network-free regression tests, but a complete local end-to-end
test has not yet been completed because the public OpenDAP service has
intermittently returned 502 responses and stalled data transfers.

GOES-ABI AOD is acquired from the public NOAA `noaa-goes19`, `noaa-goes16`,
`noaa-goes18`, and `noaa-goes17` S3 buckets using the `ABI-L2-AODC` CONUS
product. The adapter checks those satellites in configured order, stages all
available candidate granules for each hour, and the preprocessor selects the
first satellite with valid regional retrievals. It converts the GOES fixed
grid to latitude/longitude, retains `DQF <= 1`, rejects fill and out-of-range
AOD values, regrids to the configured target grid (0.02 degrees by default),
and averages to UTC hourly timestamps centered at `:30`. GEMS, GCAS,
and TEMPO PM2.5 are deferred beyond the immediate Phase 2 implementation
scope; TEMPO PM2.5 is expected to become available around April 2027.

## Planned sources

GEMS, GCAS, and TEMPO PM2.5 are deferred beyond the immediate Phase 2
implementation scope; TEMPO PM2.5 is expected to become available around
April 2027.
