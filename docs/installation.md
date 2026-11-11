# ChemML Installation and First-Time Setup

ChemML is under active development. These instructions set up the current
development environment and configuration files; the complete forecasting
workflow is not yet implemented.

## Clone the repository

```bash
git clone https://github.com/GEOS-ESM/ChemML.git
cd ChemML
git checkout CNPDF_aqforecast_development
```

## Create the environment

Create the Conda environment from the repository specification:

```bash
conda env create --file environment.yml
conda activate chemml
```

If the environment already exists, update it with:

```bash
conda env update --name chemml --file environment.yml
conda activate chemml
```

The configuration checker requires PyYAML, and the regression tests require
pytest. Both are included in `environment.yml`.

## Automated first-time setup

After activating the environment, the recommended setup path is the guided
setup function. It copies any missing configuration files, prompts for input
and output roots, collects the required credentials, creates the configured
directories, and verifies the result with the configuration checker:

```bash
python -m aqforecast.utils.setup
```

The same flow can be started from Python:

```python
from aqforecast.utils import setup_aqforecast

result = setup_aqforecast()
if result["status"] != "configured":
    result["configuration_report"].format()
```

Use `--verify-remote` when internet access is available and credentials should
also be checked against their services. Use
`--prompt-optional-credentials` to enter OpenAQ and AirNow credentials during
setup. The remaining sections document the equivalent manual process.

## Configure credentials

Copy the credentials template:

```bash
cp config/credentials/credentials_template.yaml \
    config/credentials/credentials.yaml
```

Fill in credentials required by the data sources and deployment environment.
The local credentials file is ignored by Git and must not be committed or
included in logs. Runs that do not use credential-dependent data may load the
configuration without credentials.

Credentials can also be collected and optionally verified from Python:

```python
from aqforecast.config_management import manage_credentials

result = manage_credentials(
    "config/default_config.yaml",
    verify_remote=True,
)
```

Remote verification requires internet access. Earthdata, OpenAQ, and AirNow
are checked when corresponding credentials are configured; NCCS access must be
verified from the NCCS environment.

## Configure paths

Copy the filepath template:

```bash
cp config/filepaths/filepaths_template.yaml \
    config/filepaths/filepaths.yaml
```

Update the input and output roots for the target machine. Data-source paths
are organized below the region-code directory, for example:

```text
{input}/{region_code}/TROPOMI
```

The loader reports nonexistent paths as warnings. It does not create output
directories; the automated setup function creates the configured roots,
working directories, and source directories.

## Configure a region

Copy the region template:

```bash
cp config/regions/region_template.yaml \
    config/regions/my_new_region.yaml
```

Set the region code, name, latitude and longitude bounds, output resolution,
ground-monitoring provider, and IANA timezone.

## Select component configurations

Review `config/default_config.yaml`. It selects the region, credentials,
filepath, input-data, AQ-forecast, DeepSensor, and validation configurations.
See [the configuration reference](configuration.md) for the ownership and
structure of each component file.

## Check the setup

Run the read-only configuration check:

```bash
python aqforecast/config_management/configuration.py \
    config/default_config.yaml
```

Use interactive mode to fill fixable missing or invalid settings:

```bash
python aqforecast/config_management/configuration.py \
    config/default_config.yaml --interactive
```

## Run the initial tests

```bash
python -m pytest tests/
```
