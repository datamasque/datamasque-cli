from __future__ import annotations

import uuid

import pytest
from typer.testing import CliRunner

from datamasque_cli.main import app
from datamasque_cli.output import ExitCode

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("resource", ["connections", "rulesets", "libraries"])
def test_delete_nonexistent_aborts_not_found(runner: CliRunner, resource: str) -> None:
    missing = f"dm_int_missing_{uuid.uuid4().hex[:8]}"

    result = runner.invoke(app, [resource, "delete", missing, "--yes"])

    assert result.exit_code == ExitCode.NOT_FOUND
    assert "not found" in result.stderr.lower()
