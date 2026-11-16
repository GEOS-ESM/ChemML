# Data sources

## VIIRS/JPSS2 VJ219A2 aerosol optical depth

ChemML acquires the VIIRS/JPSS2 Land Aerosol Optical Depth Daily L2G Global
750 m RSIN Grid V002 product through NASA Earthdata using `earthaccess`.
The configured collection is `VJ219A2`, version `002` (concept ID
`C2885060488-LPCLOUD`). The acquisition adapter downloads granules intersecting
the configured region and request interval, and the generic database manager
stores processed output in monthly NetCDF partitions.

The source preprocessor reads `Optical_Depth_055`, decodes the zonal sinusoidal
(RSIN) tile coordinates, and applies the moderate quality settings in
`config/inputs/input_data_config.yaml`: valid AOD values from 0 through 6 and
`AOD_QA & 3 <= 1`. Valid source pixels are binned by mean onto a 0.01-degree
latitude/longitude grid. Regridding occurs before temporal aggregation, so
multiple 750 m pixels may contribute to each target cell.

The product contains orbit slices with UTC acquisition timestamps. The
preprocessor averages all quality-controlled, regridded observations for each
calendar day and assigns the timestamp to the center of the overpass hour
(for example, `17:30:00`). When multiple overpasses are available, the time
with the most valid source pixels is retained as that day's representative
timestamp. The stored scientific variable is named `optical_depth_055`.

## PACE OCI trace gases

ChemML accesses the standard NASA PACE OCI Level-2 trace-gas collection
`PACE_OCI_L2_TRGAS` through `earthaccess`. The preprocessor reads the source
variables `total_column_no2` (molecules/cm²) and `total_column_o3` (Dobson
Units), together with their corresponding binary quality variables.

Only pixels with `quality_no2 == 0` or `quality_o3 == 0`, respectively, are
retained. The two variables are filtered independently, then binned by mean
onto a 0.02-degree latitude/longitude grid. Daily averaging occurs after this
quality control and regridding. Multiple overpasses are averaged, and the UTC
timestamp aligned to the center of the overpass hour with the most combined
valid pixels is retained for each day.
