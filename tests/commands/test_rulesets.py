from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.bundle import BundleImportResult
from datamasque.client.models.ruleset import RulesetType
from datamasque.client.models.status import ValidationErrorDetails, ValidationStatus
from typer.testing import CliRunner

from datamasque_cli.errors import ExitCode
from datamasque_cli.main import app
from tests.conftest import DEFAULT_PROJECT_REFERENCE, make_project, with_projects

MODULE = "datamasque_cli.commands.rulesets"


def _ruleset(id_: int, name: str, rs_type: RulesetType) -> SimpleNamespace:
    return SimpleNamespace(id=id_, name=name, ruleset_type=rs_type, yaml="", project=DEFAULT_PROJECT_REFERENCE)


def _make_ruleset_with_status(
    is_valid: ValidationStatus | None,
    validation_errors: list[ValidationErrorDetails] | None = None,
    id_: int = 99,
) -> SimpleNamespace:
    """A ruleset as the server returns it, carrying its validation status."""
    return SimpleNamespace(
        project=DEFAULT_PROJECT_REFERENCE,
        id=id_,
        name="demo",
        ruleset_type=RulesetType.database,
        is_valid=is_valid,
        validation_errors=validation_errors or [],
    )


@patch(f"{MODULE}.get_client")
def test_unknown_type_is_rejected_before_any_request(mock_get_client: MagicMock, runner: CliRunner) -> None:
    result = runner.invoke(app, ["rulesets", "list", "--type", "banana"])

    assert result.exit_code == ExitCode.USAGE_ERROR
    assert "is not one of" in result.output
    mock_get_client.assert_not_called()


# -- create (type resolution via server lookup) ----------------------------


@patch(f"{MODULE}.get_client")
def test_create_requires_type_when_ruleset_is_new(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.list_rulesets.return_value = []

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks:\n  - type: mask_file\n")

    result = runner.invoke(app, ["rulesets", "create", "--name", "demo", "--file", str(yaml_file)])

    assert result.exit_code == ExitCode.NOT_FOUND
    client.create_or_update_ruleset.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_create_uses_existing_type_on_update(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.list_rulesets.return_value = [_ruleset(1, "demo", RulesetType.file)]

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks:\n  - type: mask_file\n")

    result = runner.invoke(app, ["rulesets", "create", "--name", "demo", "--file", str(yaml_file)])

    assert result.exit_code == 0
    args, _ = client.create_or_update_ruleset.call_args
    assert args[0].ruleset_type == RulesetType.file


@patch(f"{MODULE}.get_client")
def test_create_requires_type_when_database_and_file_rulesets_share_a_name(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.list_rulesets.return_value = [
        _ruleset(1, "demo", RulesetType.database),
        _ruleset(2, "demo", RulesetType.file),
    ]

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks: []\n")

    result = runner.invoke(app, ["rulesets", "create", "--name", "demo", "--file", str(yaml_file)])

    assert result.exit_code == ExitCode.AMBIGUOUS
    client.create_or_update_ruleset.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_create_honours_explicit_type_for_new_ruleset(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.list_rulesets.return_value = []

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks:\n  - type: mask_file\n")

    result = runner.invoke(
        app,
        ["rulesets", "create", "--name", "demo", "--file", str(yaml_file), "--type", "file"],
    )

    assert result.exit_code == 0
    args, _ = client.create_or_update_ruleset.call_args
    assert args[0].ruleset_type == RulesetType.file


@patch(f"{MODULE}.get_client")
def test_create_explicit_type_overrides_existing_type(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.list_rulesets.return_value = [_ruleset(1, "demo", RulesetType.database)]

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks: []\n")

    result = runner.invoke(
        app,
        ["rulesets", "create", "--name", "demo", "--file", str(yaml_file), "--type", "file"],
    )

    assert result.exit_code == 0
    args, _ = client.create_or_update_ruleset.call_args
    assert args[0].ruleset_type == RulesetType.file


@patch(f"{MODULE}.get_client")
def test_create_of_a_new_type_ignores_the_other_types_project(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = with_projects(MagicMock(), make_project(1, "Default"), make_project(2, "Finance"))
    mock_get_client.return_value = client
    file_ruleset = _ruleset(1, "demo", RulesetType.file)
    file_ruleset.project = "2-finance"
    client.list_rulesets.return_value = [file_ruleset]

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks: []\n")

    result = runner.invoke(
        app,
        ["rulesets", "create", "--name", "demo", "--file", str(yaml_file), "--type", "database"],
    )

    assert result.exit_code == ExitCode.AMBIGUOUS
    assert result.stderr == "Error: The instance has 2 active projects.\nHint: Pass --project to choose one.\n"
    client.create_or_update_ruleset.assert_not_called()


# -- get / delete disambiguation ------------------------------------------


@patch(f"{MODULE}.get_client")
def test_get_aborts_when_multiple_same_name_without_type(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.list_rulesets.return_value = [
        _ruleset(1, "demo", RulesetType.database),
        _ruleset(2, "demo", RulesetType.file),
    ]

    result = runner.invoke(app, ["rulesets", "get", "demo"])
    assert result.exit_code == ExitCode.AMBIGUOUS


@patch(f"{MODULE}.get_client")
def test_get_disambiguates_with_type_flag(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.list_rulesets.return_value = [
        _ruleset(1, "demo", RulesetType.database),
        _ruleset(2, "demo", RulesetType.file),
    ]
    # `get` re-fetches the single ruleset to populate `yaml` which `list_rulesets` omits.
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "id": "2",
        "name": "demo",
        "mask_type": "file",
        "config_yaml": "tasks: []\n",
    }
    client.make_request.return_value = mock_response

    result = runner.invoke(app, ["rulesets", "get", "demo", "--type", "file", "--json"])
    assert result.exit_code == 0
    client.make_request.assert_called_once_with("GET", "/api/rulesets/2/")


@patch(f"{MODULE}.get_client")
def test_delete_only_removes_matched_type(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.list_rulesets.return_value = [
        _ruleset(1, "demo", RulesetType.database),
        _ruleset(2, "demo", RulesetType.file),
    ]

    result = runner.invoke(app, ["rulesets", "delete", "demo", "--type", "file", "--yes"])

    assert result.exit_code == 0
    client.delete_ruleset_by_id_if_exists.assert_called_once_with(2)
    client.delete_ruleset_by_name_if_exists.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_delete_aborts_when_ambiguous(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.list_rulesets.return_value = [
        _ruleset(1, "demo", RulesetType.database),
        _ruleset(2, "demo", RulesetType.file),
    ]

    result = runner.invoke(app, ["rulesets", "delete", "demo", "--yes"])

    assert result.exit_code == ExitCode.AMBIGUOUS
    client.delete_ruleset_by_id_if_exists.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_delete_aborts_when_missing(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.list_rulesets.return_value = []

    result = runner.invoke(app, ["rulesets", "delete", "demo", "--yes"])

    assert result.exit_code == ExitCode.NOT_FOUND
    client.delete_ruleset_by_id_if_exists.assert_not_called()


# -- list filter -----------------------------------------------------------


@patch(f"{MODULE}.get_client")
def test_list_filters_by_type(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.list_rulesets.return_value = [
        _ruleset(1, "a", RulesetType.database),
        _ruleset(2, "b", RulesetType.file),
    ]

    result = runner.invoke(app, ["rulesets", "list", "--type", "file", "--json"])

    assert result.exit_code == 0
    assert '"b"' in result.stdout
    assert '"a"' not in result.stdout


# -- validate --------------------------------------------------------------


@patch(f"{MODULE}.get_client")
def test_validate_requires_type_flag(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks:\n  - type: mask_table\n")

    result = runner.invoke(app, ["rulesets", "validate", "--file", str(yaml_file)])

    assert result.exit_code == ExitCode.USAGE_ERROR
    client.create_or_update_ruleset.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_validate_uses_unique_temp_name_and_cleans_by_id(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.create_or_update_ruleset.return_value = _make_ruleset_with_status(ValidationStatus.valid)

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks:\n  - type: mask_table\n")

    result = runner.invoke(app, ["rulesets", "validate", "--file", str(yaml_file), "--type", "database"])

    assert result.exit_code == 0
    client.delete_ruleset_by_id_if_exists.assert_called_once_with(99)
    (sent,) = (call.args[0] for call in client.create_or_update_ruleset.call_args_list)
    assert sent.name.startswith("__dm_cli_validate_")


@patch(f"{MODULE}.print_success", side_effect=KeyboardInterrupt)
@patch(f"{MODULE}.get_client")
def test_validate_cleans_up_when_print_success_interrupted(
    mock_get_client: MagicMock,
    _mock_print: MagicMock,
    runner: CliRunner,
    tmp_path: Path,
) -> None:
    """`try/finally` guarantees the temp ruleset is deleted even if a later step raises."""
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.create_or_update_ruleset.return_value = _make_ruleset_with_status(ValidationStatus.valid)

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks:\n  - type: mask_table\n")

    runner.invoke(app, ["rulesets", "validate", "--file", str(yaml_file), "--type", "database"])

    client.delete_ruleset_by_id_if_exists.assert_called_once_with(99)


@patch(f"{MODULE}.get_client")
def test_validate_warns_when_cleanup_fails(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.create_or_update_ruleset.return_value = _make_ruleset_with_status(ValidationStatus.valid)
    client.delete_ruleset_by_id_if_exists.side_effect = DataMasqueApiError("boom", response=MagicMock())

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks:\n  - type: mask_table\n")

    result = runner.invoke(app, ["rulesets", "validate", "--file", str(yaml_file), "--type", "database"])

    assert result.exit_code == 0
    assert "left on server" in result.stderr


@patch(f"{MODULE}.get_client")
def test_validate_sync_invalid_prints_errors_and_cleans_up(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.create_or_update_ruleset.return_value = _make_ruleset_with_status(
        ValidationStatus.invalid,
        [
            ValidationErrorDetails(message="unknown mask type 'from_nowhere'", line_number=7),
            ValidationErrorDetails(message="tasks must not be empty", line_number=None),
        ],
    )

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks: []\n")

    result = runner.invoke(app, ["rulesets", "validate", "--file", str(yaml_file), "--type", "database"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "unknown mask type 'from_nowhere'" in result.stderr
    assert "line 7" in result.stderr
    assert "tasks must not be empty" in result.stderr
    client.delete_ruleset_by_id_if_exists.assert_called_once_with(99)


@patch(f"{MODULE}.get_client")
def test_validate_puts_every_reason_in_the_agent_envelope(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DM_OUTPUT", "json")
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.create_or_update_ruleset.return_value = _make_ruleset_with_status(
        ValidationStatus.invalid,
        [ValidationErrorDetails(message="unknown mask type 'from_nowhere'", line_number=7, column_number=3)],
    )

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks: []\n")

    result = runner.invoke(app, ["rulesets", "validate", "--file", str(yaml_file), "--type", "database"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "invalid_input"
    assert "unknown mask type 'from_nowhere' (line 7, column 3)" in payload["error"]["message"]


@pytest.mark.parametrize("initial_status", [None, ValidationStatus.in_progress])
@patch(f"{MODULE}.get_client")
def test_validate_nonterminal_status_reports_valid(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path, initial_status: ValidationStatus | None
) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.create_or_update_ruleset.return_value = _make_ruleset_with_status(initial_status)

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks:\n  - type: mask_table\n")

    result = runner.invoke(app, ["rulesets", "validate", "--file", str(yaml_file), "--type", "database"])

    assert result.exit_code == 0
    client.delete_ruleset_by_id_if_exists.assert_called_once_with(99)


# -- export-bundle / import-bundle ----------------------------------------


def _make_bundle_import_result(*, fallback_project: str | None = None) -> BundleImportResult:
    """Return an import result for a bundle with no items, whose items under no project went into `fallback_project`."""
    return BundleImportResult.model_validate(
        {
            "rulesets": {"metadata": {"processed": 0, "created": 0, "restored": 0, "error": 0}, "data": []},
            "fallback_project": fallback_project,
        }
    )


@pytest.mark.parametrize(("seed_flags", "is_including_seed_files"), [([], False), (["--include-seed-files"], True)])
@patch(f"{MODULE}.get_client")
def test_export_bundle_writes_the_zip_with_seed_files_only_on_request(
    mock_get_client: MagicMock,
    runner: CliRunner,
    tmp_path: Path,
    seed_flags: list[str],
    is_including_seed_files: bool,
) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.export_bundle.return_value = b"PK\x03\x04fake-zip-bytes"

    output = tmp_path / "bundle.zip"
    result = runner.invoke(app, ["rulesets", "export-bundle", "--output", str(output), *seed_flags])

    assert result.exit_code == 0
    assert output.read_bytes() == b"PK\x03\x04fake-zip-bytes"
    client.export_bundle.assert_called_once_with(include_seed_files=is_including_seed_files)


@patch(f"{MODULE}.get_client")
def test_import_bundle_requires_confirmation(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client

    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"PK\x03\x04")

    result = runner.invoke(app, ["rulesets", "import-bundle", "--file", str(bundle)], input="n\n")

    assert result.exit_code == ExitCode.CANCELLED
    client.import_bundle.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_import_bundle_passes_the_file_and_overwrite_options(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.import_bundle.return_value = _make_bundle_import_result()

    bundle = tmp_path / "my-bundle.zip"
    bundle.write_bytes(b"PK\x03\x04zip-bytes")

    result = runner.invoke(app, ["rulesets", "import-bundle", "--file", str(bundle), "--overwrite-rulesets", "--yes"])

    assert result.exit_code == 0
    client.import_bundle.assert_called_once_with(
        bundle,
        overwrite_rulesets=True,
        overwrite_libraries=False,
        overwrite_seed_files=False,
        fallback_project=None,
    )


@patch(f"{MODULE}.get_client")
def test_import_bundle_sends_the_fallback_project(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    bank = make_project(project_id=7, name="Bank")
    client = with_projects(MagicMock(), make_project(), bank)
    mock_get_client.return_value = client
    client.import_bundle.return_value = _make_bundle_import_result()

    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"PK\x03\x04")

    result = runner.invoke(
        app, ["rulesets", "import-bundle", "--file", str(bundle), "--fallback-project", "bank", "--yes"]
    )

    assert result.exit_code == 0
    assert client.import_bundle.call_args.kwargs["fallback_project"] == bank


@patch(f"{MODULE}.get_client")
def test_import_bundle_rejects_an_unknown_fallback_project(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client

    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"PK\x03\x04")

    result = runner.invoke(
        app, ["rulesets", "import-bundle", "--file", str(bundle), "--fallback-project", "nope", "--yes"]
    )

    assert result.exit_code == ExitCode.NOT_FOUND
    client.import_bundle.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_import_bundle_names_the_project_that_took_items_under_no_project(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.import_bundle.return_value = _make_bundle_import_result(fallback_project="Bank")

    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"PK\x03\x04")

    result = runner.invoke(app, ["rulesets", "import-bundle", "--file", str(bundle), "--yes"])

    assert result.exit_code == 0
    assert " ".join(result.stderr.split()) == (
        "Bundle imported successfully. Items the bundle files under no project went into project 'Bank'."
    )


@patch(f"{MODULE}.get_client")
def test_system_export_alias_warns_and_delegates(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.export_bundle.return_value = b"zip-body"

    output = tmp_path / "export.zip"
    result = runner.invoke(app, ["system", "export", "--output", str(output)])

    assert result.exit_code == 0
    assert "deprecated" in result.stderr.lower()
    assert output.read_bytes() == b"zip-body"


@patch(f"{MODULE}.get_client")
def test_validate_oversize_aborts_before_any_request(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    yaml_file = tmp_path / "big.yaml"
    yaml_file.write_text("# padding\n" * 7000)

    result = runner.invoke(app, ["rulesets", "validate", "--file", str(yaml_file), "--type", "database"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "asynchronously" in result.stderr
    assert "dm rulesets status" in result.stderr
    mock_get_client.assert_not_called()


# -- status ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("is_valid", "errors"),
    [
        (ValidationStatus.valid, []),
        (
            ValidationStatus.invalid,
            [ValidationErrorDetails(message="Missing `key` in `tasks`.", line_number=3)],
        ),
        (ValidationStatus.in_progress, []),
    ],
    ids=["valid", "invalid", "in_progress"],
)
@patch(f"{MODULE}.get_client")
def test_status_reports_state(
    mock_get_client: MagicMock,
    runner: CliRunner,
    is_valid: ValidationStatus,
    errors: list[ValidationErrorDetails],
) -> None:
    client = with_projects(MagicMock())
    mock_get_client.return_value = client
    client.list_rulesets.return_value = [_make_ruleset_with_status(is_valid, errors)]

    result = runner.invoke(app, ["rulesets", "status", "demo", "--json"])

    assert result.exit_code == ExitCode.OK
    assert f'"status": "{is_valid.value}"' in result.stdout
    for error in errors:
        assert error.message in result.stdout
