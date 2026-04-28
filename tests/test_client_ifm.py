from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from datamasque_cli.client import get_ifm_client
from datamasque_cli.config import Config, Profile


@patch("datamasque_cli.client.DataMasqueIfmInstanceConfig")
@patch("datamasque_cli.client.DataMasqueIfmClient")
@patch("datamasque_cli.client.load_config")
def test_get_ifm_client_passes_derived_ifm_url(
    mock_load: MagicMock,
    _mock_client_cls: MagicMock,
    mock_instance_cfg: MagicMock,
) -> None:
    config = Config()
    config.set_profile("dev", Profile(url="https://dm.example.com", username="u", password="p"))
    mock_load.return_value = config

    get_ifm_client(profile_name="dev")

    _, kwargs = mock_instance_cfg.call_args
    assert kwargs["admin_server_base_url"] == "https://dm.example.com"
    assert kwargs["ifm_base_url"] == "https://dm.example.com/ifm"


@patch("datamasque_cli.client.DataMasqueIfmInstanceConfig")
@patch("datamasque_cli.client.DataMasqueIfmClient")
@patch("datamasque_cli.client.load_config")
def test_get_ifm_client_strips_trailing_slash_on_admin_url(
    mock_load: MagicMock,
    _mock_client_cls: MagicMock,
    mock_instance_cfg: MagicMock,
) -> None:
    config = Config()
    config.set_profile("dev", Profile(url="https://dm.example.com/", username="u", password="p"))
    mock_load.return_value = config

    get_ifm_client(profile_name="dev")

    _, kwargs = mock_instance_cfg.call_args
    assert kwargs["ifm_base_url"] == "https://dm.example.com/ifm"


@patch("datamasque_cli.client.DataMasqueIfmInstanceConfig")
@patch("datamasque_cli.client.DataMasqueIfmClient")
@patch("datamasque_cli.client.load_config")
def test_get_ifm_client_uses_env_profile(
    _mock_load: MagicMock,
    _mock_client_cls: MagicMock,
    mock_instance_cfg: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATAMASQUE_URL", "https://env.example.com")
    monkeypatch.setenv("DATAMASQUE_USERNAME", "env_user")
    monkeypatch.setenv("DATAMASQUE_PASSWORD", "env_pass")

    get_ifm_client()

    _, kwargs = mock_instance_cfg.call_args
    assert kwargs["admin_server_base_url"] == "https://env.example.com"
    assert kwargs["ifm_base_url"] == "https://env.example.com/ifm"
