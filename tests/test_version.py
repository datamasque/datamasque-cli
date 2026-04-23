"""Smoke test to verify the CLI loads."""

from __future__ import annotations

from typer.testing import CliRunner

from datamasque_cli.main import app

_runner = CliRunner()


def test_version() -> None:
    result = _runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "DataMasque CLI" in result.output


def test_help() -> None:
    result = _runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "connections" in result.output
    assert "rulesets" in result.output
    assert "run" in result.output
