"""Prompt for, validate, and optionally verify ChemML credentials.

Credential collection is deliberately separate from configuration loading:
missing credentials do not prevent a configuration from being loaded, because
some workflows do not use every external service.
"""

from __future__ import annotations

import getpass
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import yaml

from .configuration import load_configuration


CredentialInput = Callable[[str], str]
PLACEHOLDER_PATTERN = re.compile(r"<[^>]+>")

REQUIRED_CREDENTIALS: Tuple[Tuple[str, str, bool], ...] = (
    ("earthdata", "username", False),
    ("earthdata", "password", True),
    ("nccs", "username", False),
    ("nccs", "project", False),
)

OPTIONAL_CREDENTIALS: Tuple[Tuple[str, str, bool], ...] = (
    ("openaq", "api_key", True),
    ("airnow", "api_key", True),
)


def _configured(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not PLACEHOLDER_PATTERN.search(value)


def _load_credentials(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("credentials file must contain a top-level YAML mapping")
    return value


def _get_value(credentials: Mapping[str, Any], section: str, key: str) -> Any:
    section_values = credentials.get(section, {})
    if not isinstance(section_values, Mapping):
        return None
    return section_values.get(key)


def _set_value(credentials: Dict[str, Any], section: str, key: str, value: str) -> None:
    section_values = credentials.setdefault(section, {})
    if not isinstance(section_values, dict):
        section_values = {}
        credentials[section] = section_values
    section_values[key] = value


def _credential_path(configuration: Mapping[str, Any]) -> Path:
    paths = configuration.get("configuration_files", {})
    credential_path = paths.get("credentials") if isinstance(paths, Mapping) else None
    if not isinstance(credential_path, str) or not credential_path:
        raise ValueError("master configuration does not specify a credentials file")
    return Path(credential_path).expanduser()


def _prompt_for_credential(
    section: str,
    key: str,
    secret: bool,
    *,
    input_fn: CredentialInput,
    secret_input_fn: CredentialInput,
) -> str:
    prompt = f"Enter {section}.{key}: "
    return (secret_input_fn if secret else input_fn)(prompt).strip()


def _local_credential_errors(
    credentials: Mapping[str, Any],
    fields: Sequence[Tuple[str, str, bool]],
) -> List[str]:
    errors = []
    for section, key, _ in fields:
        if not _configured(_get_value(credentials, section, key)):
            errors.append(f"{section}.{key} is missing or still contains a placeholder")
    return errors


def _response_status(response: Any) -> str:
    if 200 <= response.status_code < 300:
        return "valid"
    if response.status_code in {401, 403}:
        return "invalid"
    return "unverified"


def _verify_with_retry(verify_fn: Callable[[], Dict[str, str]], max_retries: int) -> Dict[str, str]:
    """Retry transiently unverified checks without retrying invalid credentials."""

    result = verify_fn()
    for _ in range(max_retries):
        if result.get("status") != "unverified":
            break
        result = verify_fn()
    return result


def _verify_earthdata(username: str, password: str, timeout: float) -> Dict[str, str]:
    """Verify Earthdata credentials using earthaccess when available."""

    try:
        import earthaccess
    except ImportError:
        earthaccess = None

    if earthaccess is not None:
        try:
            auth = earthaccess.login(
                username=username,
                password=password,
                persist=False,
            )
            if auth is not None and getattr(auth, "authenticated", False):
                return {
                    "status": "valid",
                    "message": "Earthdata credentials verified with earthaccess",
                }
            return {"status": "invalid", "message": "Earthdata authentication failed"}
        except Exception as exc:
            # A direct request is retained as a fallback for earthaccess
            # version differences or authentication implementation errors.
            earthaccess_error = str(exc)
    else:
        earthaccess_error = "earthaccess is not installed"

    try:
        import requests
        response = requests.get(
            "https://urs.earthdata.nasa.gov/api/users",
            auth=(username, password),
            timeout=timeout,
        )
        return {
            "status": _response_status(response),
            "message": f"Earthdata fallback endpoint returned HTTP {response.status_code}",
        }
    except ImportError:
        return {
            "status": "unverified",
            "message": f"Could not verify Earthdata: {earthaccess_error}; requests is not installed",
        }
    except requests.RequestException as exc:
        return {"status": "unverified", "message": str(exc)}


def _verify_openaq(api_key: str, timeout: float) -> Dict[str, str]:
    """Verify an OpenAQ v3 API key and response structure."""

    try:
        import requests
        response = requests.get(
            "https://api.openaq.org/v3/locations",
            headers={"X-API-Key": api_key},
            params={"limit": 1, "page": 1},
            timeout=timeout,
        )
        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError:
                return {"status": "unverified", "message": "OpenAQ returned invalid JSON"}
            if isinstance(payload, dict) and "results" in payload:
                return {"status": "valid", "message": "OpenAQ API key verified successfully"}
            return {"status": "unverified", "message": "OpenAQ response lacked a results field"}
        return {
            "status": _response_status(response),
            "message": f"OpenAQ endpoint returned HTTP {response.status_code}",
        }
    except ImportError:
        return {"status": "unverified", "message": "requests is not installed"}
    except requests.RequestException as exc:
        return {"status": "unverified", "message": str(exc)}


def _verify_airnow(api_key: str, timeout: float) -> Dict[str, str]:
    """Verify an AirNow API key using a recent data request."""

    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    start_date = yesterday.strftime("%Y-%m-%dT00-0000")
    end_date = yesterday.strftime("%Y-%m-%dT01-0000")
    try:
        import requests
        response = requests.get(
            "https://www.airnowapi.org/aq/data/",
            params={
                "startDate": start_date,
                "endDate": end_date,
                "parameters": "PM25",
                "BBOX": "-130,20,-60,55",
                "dataType": "A",
                "format": "application/json",
                "verbose": 0,
                "monitorType": 0,
                "includerawconcentrations": 0,
                "API_KEY": api_key,
            },
            timeout=timeout,
        )
        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError:
                return {"status": "unverified", "message": "AirNow returned invalid JSON"}
            if isinstance(payload, list):
                return {"status": "valid", "message": "AirNow API key verified successfully"}
            if isinstance(payload, dict) and "error" in str(payload).lower():
                return {"status": "invalid", "message": f"AirNow API error: {payload}"}
            return {"status": "unverified", "message": "AirNow response format was not recognized"}
        return {
            "status": _response_status(response),
            "message": f"AirNow endpoint returned HTTP {response.status_code}",
        }
    except ImportError:
        return {"status": "unverified", "message": "requests is not installed"}
    except requests.RequestException as exc:
        return {"status": "unverified", "message": str(exc)}


def _verify_remote(
    credentials: Mapping[str, Any],
    timeout: float,
    max_retries: int = 2,
) -> Dict[str, Dict[str, str]]:
    """Verify configured credentials through their service APIs."""

    results: Dict[str, Dict[str, str]] = {}

    earthdata_username = _get_value(credentials, "earthdata", "username")
    earthdata_password = _get_value(credentials, "earthdata", "password")
    if _configured(earthdata_username) and _configured(earthdata_password):
        results["earthdata"] = _verify_with_retry(
            lambda: _verify_earthdata(earthdata_username, earthdata_password, timeout),
            max_retries,
        )

    openaq_key = _get_value(credentials, "openaq", "api_key")
    if _configured(openaq_key):
        results["openaq"] = _verify_with_retry(
            lambda: _verify_openaq(openaq_key, timeout),
            max_retries,
        )

    airnow_key = _get_value(credentials, "airnow", "api_key")
    if _configured(airnow_key):
        results["airnow"] = _verify_with_retry(
            lambda: _verify_airnow(airnow_key, timeout),
            max_retries,
        )

    if _configured(_get_value(credentials, "nccs", "username")):
        results["nccs"] = {
            "status": "not_checked",
            "message": "NCCS access must be verified from the NCCS environment",
        }
    return results


def manage_credentials(
    config_path: Union[str, Path] = "config/default_config.yaml",
    *,
    verify_remote: bool = False,
    prompt_optional: bool = False,
    timeout: float = 10.0,
    remote_retries: int = 2,
    input_fn: CredentialInput = input,
    secret_input_fn: Optional[CredentialInput] = None,
    output_fn: Callable[[str], None] = print,
) -> Dict[str, Any]:
    """Prompt for and validate credentials referenced by a master configuration.

    The function first calls :func:`load_configuration` to resolve the
    credentials-file location. Required fields are prompted when missing or
    placeholder values are present. Optional OpenAQ and AirNow fields are only
    prompted when ``prompt_optional`` is true.

    Remote verification is opt-in because it requires internet access and may
    contact external services. Earthdata, OpenAQ, and AirNow are checked with
    authenticated requests; transiently unverified checks are retried, and
    NCCS is reported as ``not_checked``.
    """

    secret_input_fn = secret_input_fn or getpass.getpass
    configuration = load_configuration(
        config_path,
        require_credentials=False,
    )
    credentials_path = _credential_path(configuration)
    credentials = _load_credentials(credentials_path)
    fields = list(REQUIRED_CREDENTIALS)
    if prompt_optional:
        fields.extend(OPTIONAL_CREDENTIALS)

    updated_fields: List[str] = []
    prompt_errors: List[str] = []
    for section, key, secret in fields:
        if _configured(_get_value(credentials, section, key)):
            continue
        value = _prompt_for_credential(
            section,
            key,
            secret,
            input_fn=input_fn,
            secret_input_fn=secret_input_fn,
        )
        if not _configured(value):
            prompt_errors.append(f"{section}.{key} was left blank or contains a placeholder")
            continue
        _set_value(credentials, section, key, value)
        updated_fields.append(f"{section}.{key}")

    local_errors = prompt_errors + _local_credential_errors(credentials, REQUIRED_CREDENTIALS)
    if local_errors:
        return {
            "status": "invalid",
            "message": "Required credentials are incomplete.",
            "credentials_file": str(credentials_path),
            "updated_fields": updated_fields,
            "verification": {},
            "warnings": configuration.get("warnings", []),
            "errors": sorted(set(local_errors)),
        }

    credentials_path.parent.mkdir(parents=True, exist_ok=True)
    with credentials_path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(credentials, stream, sort_keys=False, default_flow_style=False)
    try:
        credentials_path.chmod(0o600)
    except OSError as exc:
        output_fn(f"Warning: could not restrict credentials-file permissions: {exc}")

    verification = (
        _verify_remote(credentials, timeout, max_retries=remote_retries)
        if verify_remote
        else {}
    )
    invalid_remote = [
        provider
        for provider, result in verification.items()
        if result.get("status") == "invalid"
    ]
    status = "invalid" if invalid_remote else "updated"
    message = "Credentials were saved and locally validated."
    if verify_remote:
        message += " Remote verification was requested."
    return {
        "status": status,
        "message": message,
        "credentials_file": str(credentials_path),
        "updated_fields": updated_fields,
        "verification": verification,
        "warnings": configuration.get("warnings", []),
        "errors": [f"Remote verification failed for: {', '.join(invalid_remote)}"] if invalid_remote else [],
    }


__all__ = ["manage_credentials"]
