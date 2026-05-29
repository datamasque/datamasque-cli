"""Integration tests for `dm system` commands that hit anonymous endpoints.

These end-to-end exercise the `get_unauthenticated_client` path against a real
DataMasque instance, the regression they guard against (silently re-introducing
`get_client` on either command) can only be caught against a real server: a unit
test can mock the factory, but only a live instance reveals that the auth call
fails on a fresh server.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest
from typer.testing import CliRunner

from datamasque_cli.main import app

pytestmark = pytest.mark.integration


def _is_installed(runner: CliRunner) -> bool:
    """Check installation state via the dm CLI's health-style probe.

    `/api/app/check/` is what the admin frontend uses to decide whether to show
    the install wizard, so it's the canonical signal for "this instance is
    already set up".

    Implemented via the python client directly because there's no `dm` command
    for `/api/app/check/` yet; that's the only thing here that bypasses the CLI.
    """
    # Build a URL-only client so this works on a fresh instance too.
    from datamasque_cli.client import get_unauthenticated_client

    client = get_unauthenticated_client()
    response = client.make_request("GET", "/api/app/check/", requires_authorization=False)
    return bool(response.json().get("installed"))


def test_health_works_without_authentication(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """`dm system health` must succeed even when no credentials are configured.

    The whole point of a health probe is to be the lowest-friction "is the
    server up?" signal -- it shouldn't depend on a valid login.
    """
    monkeypatch.delenv("DATAMASQUE_USERNAME", raising=False)
    monkeypatch.delenv("DATAMASQUE_PASSWORD", raising=False)

    result = runner.invoke(app, ["system", "health", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "healthy"


def test_admin_install_creates_admin_user_on_fresh_instance(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end admin-install against a real instance.

    Skips when the instance is already configured -- the endpoint is gated on
    "no user has been created yet" and reusing a server between runs is the
    common case. To exercise this path, point the integration suite at a
    freshly-restarted DataMasque (e.g. `docker compose down -v && up -d`).
    """
    if _is_installed(runner):
        pytest.skip(
            "Instance is already installed. Reset it (e.g. `docker compose down -v && up -d`) "
            "to exercise the admin-install path."
        )

    # `dm system admin-install` needs no credentials -- the password is passed
    # via --password and the endpoint itself is anonymous. Clear the env vars
    # the parent fixture set so this test proves the no-creds path works.
    monkeypatch.delenv("DATAMASQUE_USERNAME", raising=False)
    monkeypatch.delenv("DATAMASQUE_PASSWORD", raising=False)

    # Use the same credentials the parent fixture configures, so any
    # subsequent authenticated tests in this session can log in.
    username = os.environ["DM_TEST_USERNAME"]
    password = os.environ["DM_TEST_PASSWORD"]
    email = f"{uuid.uuid4().hex[:8]}@dm-integration.test"

    result = runner.invoke(
        app,
        [
            "system", "admin-install",
            "--email", email,
            "--username", username,
            "--password", password,
        ],
    )

    assert result.exit_code == 0, result.output
    assert _is_installed(runner), "Instance should be marked installed after admin-install"
