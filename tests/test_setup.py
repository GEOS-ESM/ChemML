"""Regression tests for the guided first-time setup flow."""

from pathlib import Path

from aqdatafusion.utils.setup import setup_aqdatafusion


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_setup_aqdatafusion_copies_configures_and_validates(tmp_path: Path) -> None:
    target_config = tmp_path / "config"
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    responses = iter([str(input_root), str(output_root), "earthdata-user", "nccs-user", "nccs-project"])
    secret_responses = iter(["earthdata-password"])

    result = setup_aqdatafusion(
        target_config,
        source_config_directory=REPOSITORY_ROOT / "config",
        input_fn=lambda _prompt: next(responses),
        secret_input_fn=lambda _prompt: next(secret_responses),
        output_fn=lambda _message: None,
        download_basemap=False,
    )

    assert result["status"] == "configured"
    assert result["configuration_report"].is_valid
    assert (target_config / "default_config.yaml").is_file()
    assert (target_config / "credentials" / "credentials.yaml").is_file()
    assert input_root.is_dir()
    assert output_root.is_dir()
    assert result["created_directories"]


def test_setup_aqdatafusion_can_create_named_master_configuration(
    tmp_path: Path,
) -> None:
    target_config = tmp_path / "config"
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    responses = iter(
        [str(input_root), str(output_root), "earthdata-user", "nccs-user", "nccs-project"]
    )
    secret_responses = iter(["earthdata-password"])

    result = setup_aqdatafusion(
        target_config,
        configuration_filename="atl_config.yaml",
        source_config_directory=REPOSITORY_ROOT / "config",
        input_fn=lambda _prompt: next(responses),
        secret_input_fn=lambda _prompt: next(secret_responses),
        output_fn=lambda _message: None,
        download_basemap=False,
    )

    assert result["status"] == "configured"
    assert result["config_path"] == target_config / "atl_config.yaml"
    assert (target_config / "atl_config.yaml").is_file()
    assert not (target_config / "default_config.yaml").exists()


def test_setup_aqdatafusion_reuses_existing_roots_and_credentials(tmp_path: Path) -> None:
    target_config = tmp_path / "config"
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    first_responses = iter(
        [str(input_root), str(output_root), "earthdata-user", "nccs-user", "nccs-project"]
    )
    first_secret_responses = iter(["earthdata-password"])
    setup_aqdatafusion(
        target_config,
        source_config_directory=REPOSITORY_ROOT / "config",
        input_fn=lambda _prompt: next(first_responses),
        secret_input_fn=lambda _prompt: next(first_secret_responses),
        output_fn=lambda _message: None,
        download_basemap=False,
    )

    def unexpected_prompt(_prompt: str) -> str:
        raise AssertionError("setup prompted despite valid existing paths and credentials")

    result = setup_aqdatafusion(
        target_config,
        source_config_directory=REPOSITORY_ROOT / "config",
        input_fn=unexpected_prompt,
        secret_input_fn=unexpected_prompt,
        output_fn=lambda _message: None,
        download_basemap=False,
    )

    assert result["status"] == "configured"
