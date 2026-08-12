from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from datamasque_cli.main import app


def test_catalog_compact_json_lists_every_subcommand(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    monkeypatch.setenv("DM_OUTPUT", "json")
    result = runner.invoke(app, ["catalog", "--compact"])
    assert result.exit_code == 0

    payload = json.loads(result.stdout)
    paths = {entry["path"] for entry in payload["commands"]}

    # Spot-check a few entries from different subgroups.
    assert "connections list" in paths
    assert "rulesets get" in paths
    assert "run start" in paths
    assert "auth login" in paths

    # Nested discovery-config groups surface as `discover <group> <command>` paths.
    assert "discover schema" in paths
    assert "discover configs list" in paths
    assert "discover libraries create" in paths
    assert "discover config-snapshot" in paths


def test_catalog_full_includes_options(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    monkeypatch.setenv("DM_OUTPUT", "json")
    result = runner.invoke(app, ["catalog"])
    assert result.exit_code == 0

    payload = json.loads(result.stdout)
    list_cmd = next(c for c in payload["commands"] if c["path"] == "connections list")

    json_flag = next(o for o in list_cmd["options"] if o.get("flags") == ["--json"])
    assert json_flag["is_flag"] is True


def test_catalog_human_mode_renders_indented_text(monkeypatch: pytest.MonkeyPatch, runner: CliRunner) -> None:
    monkeypatch.setenv("DM_OUTPUT", "table")
    result = runner.invoke(app, ["catalog", "--compact"])
    assert result.exit_code == 0
    # Human view is plain text with command paths, not JSON.
    assert "{" not in result.stdout
    assert "connections list" in result.stdout
