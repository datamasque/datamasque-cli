from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from datamasque_cli.client import resolve_connection


def test_resolve_connection_by_name() -> None:
    client = MagicMock()
    client.list_connections.return_value = [SimpleNamespace(id="conn-1", name="input")]

    match = resolve_connection(client, "input")

    assert match.id == "conn-1"


def test_resolve_connection_by_id() -> None:
    client = MagicMock()
    client.list_connections.return_value = [SimpleNamespace(id="conn-1", name="input")]

    match = resolve_connection(client, "conn-1")

    assert match.name == "input"


def test_resolve_connection_not_found_aborts() -> None:
    client = MagicMock()
    client.list_connections.return_value = [SimpleNamespace(id="conn-1", name="input")]

    with pytest.raises(SystemExit):
        resolve_connection(client, "nope")
