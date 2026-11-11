"""Regression tests for the guided first-time setup flow."""

from pathlib import Path

from aqforecast.utils.setup import setup_aqforecast


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_setup_aqforecast_copies_configures_and_validates(tmp_path: Path) -> None:
    target_config = tmp_path / "config"
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    responses = iter([str(input_root), str(output_root), "earthdata-user", "nccs-user", "nccs-project"])
    secret_responses = iter(["earthdata-password"])

    result = setup_aqforecast(
        target_config,
        source_config_directory=REPOSITORY_ROOT / "config",
        input_fn=lambda _prompt: next(responses),
        secret_input_fn=lambda _prompt: next(secret_responses),
        output_fn=lambda _message: None,
    )

    assert result["status"] == "configured"
    assert result["configuration_report"].is_valid
    assert (target_config / "default_config.yaml").is_file()
    assert (target_config / "credentials" / "credentials.yaml").is_file()
    assert input_root.is_dir()
    assert output_root.is_dir()
    assert result["created_directories"]
