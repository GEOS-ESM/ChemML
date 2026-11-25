#!/usr/bin/env bash
# Run the configured rolling input-data database update.
#
# To use a different region or experiment, change CONFIG_PATH below to the
# appropriate master configuration YAML file before scheduling this script.

set -euo pipefail

SCRIPT_DIRECTORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd -- "${SCRIPT_DIRECTORY}/.." && pwd)"

# Edit this line to select a different master configuration file.
CONFIG_PATH="${REPOSITORY_ROOT}/config/default_config.yaml"
CONDA_ENVIRONMENT="chemml"

cd "${REPOSITORY_ROOT}"

if ! command -v conda >/dev/null 2>&1; then
    echo "ERROR: conda is not available on PATH." >&2
    exit 2
fi

CONDA_BASE="$(conda info --base)"
# shellcheck disable=SC1091
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENVIRONMENT}"

CONFIG_PATH="${CONFIG_PATH}" python - <<'PY'
import os
import sys

from aqdatafusion import run_aqdatafusion


config_path = os.environ["CONFIG_PATH"]
result = run_aqdatafusion(
    config_path,
    mode="incremental_database_update",
    require_credentials=True,
    prompt_credentials=False,
)

print(result.get("message", "Incremental database update completed."))
if result.get("report", {}).get("operational_report_path"):
    print(f"Operational report: {result['report']['operational_report_path']}")
if result.get("warnings"):
    print("Warnings:")
    for warning in result["warnings"]:
        print(f"  - {warning}")

if result.get("status") != "database_updated":
    for error in result.get("errors", []):
        print(f"ERROR: {error}", file=sys.stderr)
    sys.exit(1)
PY
