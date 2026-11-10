"""Network-free tests for credential collection."""

import shutil
from pathlib import Path

import yaml

from aqforecast.config_management.credentials import manage_credentials


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_manage_credentials_prompts_and_writes_required_values(tmp_path: Path) -> None:
    temporary_config = tmp_path / "config"
    shutil.copytree(REPOSITORY_ROOT / "config", temporary_config)
    credentials_path = temporary_config / "credentials" / "credentials.yaml"
    if credentials_path.exists():
        credentials_path.unlink()

    regular_values = iter(["earthdata-user", "nccs-user", "nccs-project"])
    secret_values = iter(["earthdata-password"])

    result = manage_credentials(
        temporary_config / "default_config.yaml",
        input_fn=lambda _prompt: next(regular_values),
        secret_input_fn=lambda _prompt: next(secret_values),
    )

    assert result["status"] == "updated"
    assert result["credentials_file"] == str(credentials_path)
    with credentials_path.open(encoding="utf-8") as stream:
        credentials = yaml.safe_load(stream)
    assert credentials["earthdata"]["username"] == "earthdata-user"
    assert credentials["earthdata"]["password"] == "earthdata-password"
    assert credentials["nccs"]["project"] == "nccs-project"


def test_manage_credentials_does_not_require_optional_services(tmp_path: Path) -> None:
    temporary_config = tmp_path / "config"
    shutil.copytree(REPOSITORY_ROOT / "config", temporary_config)
    credentials_path = temporary_config / "credentials" / "credentials.yaml"
    if credentials_path.exists():
        credentials_path.unlink()

    regular_values = iter(["earthdata-user", "nccs-user", "nccs-project"])
    secret_values = iter(["earthdata-password"])
    result = manage_credentials(
        temporary_config / "default_config.yaml",
        input_fn=lambda _prompt: next(regular_values),
        secret_input_fn=lambda _prompt: next(secret_values),
        prompt_optional=False,
    )

    with credentials_path.open(encoding="utf-8") as stream:
        credentials = yaml.safe_load(stream)
    assert result["status"] == "updated"
    assert "openaq" not in credentials
    assert "airnow" not in credentials
