from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from datamasque_cli.client import get_client
from datamasque_cli.config import Config, Profile


@patch("datamasque_cli.client.DataMasqueClient")
@patch("datamasque_cli.client.load_config")
def test_get_client_uses_env_vars(
    _mock_load: MagicMock, mock_client_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATAMASQUE_URL", "https://env.example.com")
    monkeypatch.setenv("DATAMASQUE_USERNAME", "env_user")
    monkeypatch.setenv("DATAMASQUE_PASSWORD", "env_pass")

    get_client()

    _mock_load.assert_not_called()
    mock_client_cls.return_value.authenticate.assert_called_once()


@patch("datamasque_cli.client.DataMasqueClient")
@patch("datamasque_cli.client.load_config")
def test_get_client_named_profile_overrides_env(
    mock_load: MagicMock, mock_client_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATAMASQUE_URL", "https://env.example.com")
    monkeypatch.setenv("DATAMASQUE_USERNAME", "env_user")
    monkeypatch.setenv("DATAMASQUE_PASSWORD", "env_pass")

    config = Config()
    config.set_profile("prod", Profile(url="https://prod", username="admin", password="secret"))
    mock_load.return_value = config

    get_client(profile_name="prod")

    mock_load.assert_called_once()


@patch("datamasque_cli.client.DataMasqueInstanceConfig")
@patch("datamasque_cli.client.DataMasqueClient")
@patch("datamasque_cli.client.load_config")
def test_get_client_passes_profile_verify_ssl(
    mock_load: MagicMock,
    _mock_client_cls: MagicMock,
    mock_instance_cfg: MagicMock,
) -> None:
    config = Config()
    config.set_profile("dev", Profile(url="https://localhost", username="admin", password="x", verify_ssl=False))
    mock_load.return_value = config

    get_client(profile_name="dev")

    _, kwargs = mock_instance_cfg.call_args
    assert kwargs["verify_ssl"] is False


@patch("datamasque_cli.client.DataMasqueInstanceConfig")
@patch("datamasque_cli.client.DataMasqueClient")
@patch("datamasque_cli.client.load_config")
def test_env_verify_ssl_overrides_profile(
    mock_load: MagicMock,
    _mock_client_cls: MagicMock,
    mock_instance_cfg: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATAMASQUE_VERIFY_SSL", "false")
    config = Config()
    # Profile defaults verify_ssl=True; env should win and disable it.
    config.set_profile("p", Profile(url="https://x", username="u", password="x"))
    mock_load.return_value = config

    get_client(profile_name="p")

    _, kwargs = mock_instance_cfg.call_args
    assert kwargs["verify_ssl"] is False
