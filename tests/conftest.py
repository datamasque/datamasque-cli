from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from datamasque.client.models.ruleset import RulesetType
from typer.testing import CliRunner

from datamasque_cli.config import Config, Profile


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def mock_client() -> MagicMock:
    """Pre-configured mock with two connections and one ruleset."""
    client = MagicMock()
    client.list_connections.return_value = [
        SimpleNamespace(id=1, name="my_conn", mask_type="database"),
        SimpleNamespace(id=2, name="other_conn", mask_type="database"),
    ]
    client.list_rulesets.return_value = [
        SimpleNamespace(id=10, name="my_ruleset", ruleset_type=RulesetType.database, yaml=""),
    ]
    return client


def make_api_response(data: Any, *, is_ok: bool = True) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = data
    resp.ok = is_ok
    return resp


def make_config(
    name: str = "default",
    url: str = "https://dm.example.com",
    username: str = "admin",
    password: str = "secret",
) -> Config:
    config = Config()
    config.set_profile(name, Profile(url=url, username=username, password=password))
    config.active_profile = name
    return config
