from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from datamasque_cli.main import app

_TERMINAL_STATUSES = frozenset({"finished", "finished_with_warnings", "failed", "cancelled"})


@pytest.fixture(scope="session", autouse=True)
def _dm_env() -> None:
    missing = [v for v in ("DM_TEST_URL", "DM_TEST_USERNAME", "DM_TEST_PASSWORD") if not os.environ.get(v)]
    if missing:
        pytest.skip(f"Integration tests need env vars: {', '.join(missing)}", allow_module_level=True)
    os.environ["DATAMASQUE_URL"] = os.environ["DM_TEST_URL"]
    os.environ["DATAMASQUE_USERNAME"] = os.environ["DM_TEST_USERNAME"]
    os.environ["DATAMASQUE_PASSWORD"] = os.environ["DM_TEST_PASSWORD"]


@pytest.fixture()
def ruleset_name(runner: CliRunner) -> Iterator[str]:
    name = f"dm_int_{uuid.uuid4().hex[:8]}"
    yield name
    for ruleset_type in ("file", "database"):
        runner.invoke(app, ["rulesets", "delete", name, "--type", ruleset_type, "--yes"])


@pytest.fixture()
def connection_name(runner: CliRunner) -> Iterator[str]:
    name = f"dm_int_{uuid.uuid4().hex[:8]}"
    yield name
    runner.invoke(app, ["connections", "delete", name, "--yes"])


@pytest.fixture()
def file_connection_pair(runner: CliRunner) -> tuple[str, str]:
    """Return (source, destination) names of file-type connections on the instance.

    Prefers `DM_TEST_SOURCE_CONN` / `DM_TEST_DESTINATION_CONN` env overrides
    for CI determinism, falls back to auto-detecting the first matching pair
    from `dm connections list`. Skips if no pair is available.
    """
    src = os.environ.get("DM_TEST_SOURCE_CONN")
    dst = os.environ.get("DM_TEST_DESTINATION_CONN")
    if src and dst:
        return src, dst

    result = runner.invoke(app, ["connections", "list", "--json"])
    if result.exit_code != 0:
        pytest.skip("Could not list connections to auto-detect a file source/destination")

    conns = json.loads(result.stdout)
    # Prefer MountedShare (local filesystem → fast) over S3/Azure (network round-trip → slow, flaky).
    type_preference = ("MountedShare", "Azure", "S3")
    source = _pick_by_role(conns, {"source", "source+destination"}, type_preference)
    destination = _pick_by_role(conns, {"destination", "source+destination"}, type_preference)
    if not source or not destination:
        pytest.skip(
            "No file-type source+destination connection pair on this instance; "
            "set DM_TEST_SOURCE_CONN / DM_TEST_DESTINATION_CONN to override"
        )
    return source, destination


def _pick_by_role(conns: list[dict[str, str]], roles: set[str], type_preference: tuple[str, ...]) -> str | None:
    """Return the first connection name matching a role, walking types in preference order."""
    for wanted_type in type_preference:
        match = next((c["name"] for c in conns if c["type"] == wanted_type and c["role"] in roles), None)
        if match:
            return match
    return None


@pytest.fixture()
def fast_file_yaml(tmp_path: Path) -> Path:
    """Minimal file ruleset whose `include` regex matches nothing.

    Exercises the run lifecycle without actually processing any files,
    so a full start→retry chain completes in seconds.
    """
    path = tmp_path / "fast.yaml"
    path.write_text(
        "version: '1.0'\n"
        "tasks:\n"
        "  - type: mask_file\n"
        "    recurse: true\n"
        "    include:\n"
        "      - regex: ^.*dm_int_no_match_ever\\.nope$\n"
        "    rules:\n"
        "      - masks:\n"
        "          - type: unstructured_text\n"
        "            matchers:\n"
        "                regex:\n"
        "                  - label: X\n"
        "                    pattern: NEVER\n"
        "            masks:\n"
        "              - label: X\n"
        "                masks:\n"
        "                  - type: from_fixed\n"
        "                    value: NEVER\n"
    )
    return path


def wait_for_run(runner: CliRunner, run_id: int, timeout_s: float = 30.0) -> str:
    """Poll `dm run status` until the run reaches a terminal state, return it."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = runner.invoke(app, ["run", "status", str(run_id), "--json"])
        if result.exit_code == 0:
            status = json.loads(result.stdout).get("status", "")
            if status in _TERMINAL_STATUSES:
                return status
        time.sleep(1)
    raise AssertionError(f"Run {run_id} did not reach terminal state within {timeout_s}s")


@pytest.fixture()
def file_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "file.yaml"
    path.write_text(
        "version: '1.0'\n"
        "tasks:\n"
        "  - type: mask_file\n"
        "    recurse: true\n"
        "    include:\n"
        "      - regex: ^.*\\.pdf$\n"
        "    rules:\n"
        "      - masks:\n"
        "          - type: unstructured_text\n"
        "            matchers:\n"
        "                regex:\n"
        "                  - label: EMAIL\n"
        "                    pattern: \\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}\\b\n"
        "            masks:\n"
        "              - label: EMAIL\n"
        "                masks:\n"
        "                  - type: from_fixed\n"
        "                    value: redacted@example.com\n"
    )
    return path


@pytest.fixture()
def db_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "db.yaml"
    path.write_text(
        "version: '1.0'\n"
        "tasks:\n"
        "  - type: mask_table\n"
        "    table: users\n"
        "    key: id\n"
        "    rules:\n"
        "      - column: email\n"
        "        masks:\n"
        "          - type: from_fixed\n"
        "            value: redacted@example.com\n"
    )
    return path
