from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.ruleset import RulesetType
from typer.testing import CliRunner

from datamasque_cli.main import app

MODULE = "datamasque_cli.commands.rulesets"


def _ruleset(id_: int, name: str, rs_type: RulesetType) -> SimpleNamespace:
    return SimpleNamespace(id=id_, name=name, ruleset_type=rs_type, yaml="")


# -- create (type resolution via server lookup) ----------------------------


@patch(f"{MODULE}.get_client")
def test_create_requires_type_when_ruleset_is_new(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_rulesets.return_value = []

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks:\n  - type: mask_file\n")

    result = runner.invoke(app, ["rulesets", "create", "--name", "demo", "--file", str(yaml_file)])

    assert result.exit_code != 0
    client.create_or_update_ruleset.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_create_uses_existing_type_on_update(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_rulesets.return_value = [_ruleset(1, "demo", RulesetType.file)]

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks:\n  - type: mask_file\n")

    result = runner.invoke(app, ["rulesets", "create", "--name", "demo", "--file", str(yaml_file)])

    assert result.exit_code == 0
    args, _ = client.create_or_update_ruleset.call_args
    assert args[0].ruleset_type == RulesetType.file


@patch(f"{MODULE}.get_client")
def test_create_requires_type_when_both_namespaces_hold_same_name(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_rulesets.return_value = [
        _ruleset(1, "demo", RulesetType.database),
        _ruleset(2, "demo", RulesetType.file),
    ]

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks: []\n")

    result = runner.invoke(app, ["rulesets", "create", "--name", "demo", "--file", str(yaml_file)])

    assert result.exit_code != 0
    client.create_or_update_ruleset.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_create_honours_explicit_type_for_new_ruleset(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = MagicMock()
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
    client = MagicMock()
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


# -- get / delete disambiguation ------------------------------------------


@patch(f"{MODULE}.get_client")
def test_get_aborts_when_multiple_same_name_without_type(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_rulesets.return_value = [
        _ruleset(1, "demo", RulesetType.database),
        _ruleset(2, "demo", RulesetType.file),
    ]

    result = runner.invoke(app, ["rulesets", "get", "demo"])
    assert result.exit_code != 0


@patch(f"{MODULE}.get_client")
def test_get_disambiguates_with_type_flag(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
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
    client = MagicMock()
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
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_rulesets.return_value = [
        _ruleset(1, "demo", RulesetType.database),
        _ruleset(2, "demo", RulesetType.file),
    ]

    result = runner.invoke(app, ["rulesets", "delete", "demo", "--yes"])

    assert result.exit_code != 0
    client.delete_ruleset_by_id_if_exists.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_delete_aborts_when_missing(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    client.list_rulesets.return_value = []

    result = runner.invoke(app, ["rulesets", "delete", "demo", "--yes"])

    assert result.exit_code != 0
    client.delete_ruleset_by_id_if_exists.assert_not_called()


# -- list filter -----------------------------------------------------------


@patch(f"{MODULE}.get_client")
def test_list_filters_by_type(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = MagicMock()
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
    client = MagicMock()
    mock_get_client.return_value = client

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks:\n  - type: mask_table\n")

    result = runner.invoke(app, ["rulesets", "validate", "--file", str(yaml_file)])

    assert result.exit_code != 0
    client.create_or_update_ruleset.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_validate_uses_unique_temp_name_and_cleans_by_id(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = MagicMock()
    mock_get_client.return_value = client

    def fake_create(rs: object) -> object:
        rs.id = 99  # type: ignore[attr-defined]
        return rs

    client.create_or_update_ruleset.side_effect = fake_create

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
    client = MagicMock()
    mock_get_client.return_value = client

    def fake_create(rs: object) -> object:
        rs.id = 99  # type: ignore[attr-defined]
        return rs

    client.create_or_update_ruleset.side_effect = fake_create

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks:\n  - type: mask_table\n")

    runner.invoke(app, ["rulesets", "validate", "--file", str(yaml_file), "--type", "database"])

    client.delete_ruleset_by_id_if_exists.assert_called_once_with(99)


@patch(f"{MODULE}.get_client")
def test_validate_warns_when_cleanup_fails(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client

    def fake_create(rs: object) -> object:
        rs.id = 99  # type: ignore[attr-defined]
        return rs

    client.create_or_update_ruleset.side_effect = fake_create
    client.delete_ruleset_by_id_if_exists.side_effect = DataMasqueApiError("boom", response=MagicMock())

    yaml_file = tmp_path / "rs.yaml"
    yaml_file.write_text("tasks:\n  - type: mask_table\n")

    result = runner.invoke(app, ["rulesets", "validate", "--file", str(yaml_file), "--type", "database"])

    assert result.exit_code == 0
    assert "left on server" in result.stderr


# -- export-bundle / import-bundle ----------------------------------------


@patch(f"{MODULE}.get_client")
def test_export_bundle_writes_binary_zip(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    mock_response = MagicMock()
    mock_response.content = b"PK\x03\x04fake-zip-bytes"
    client.make_request.return_value = mock_response

    output = tmp_path / "bundle.zip"
    result = runner.invoke(app, ["rulesets", "export-bundle", "--output", str(output)])

    assert result.exit_code == 0
    assert output.read_bytes() == b"PK\x03\x04fake-zip-bytes"
    client.make_request.assert_called_once_with("GET", "/api/export/v1/")


@patch(f"{MODULE}.get_client")
def test_import_bundle_requires_confirmation(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client

    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(b"PK\x03\x04")

    result = runner.invoke(app, ["rulesets", "import-bundle", "--file", str(bundle)], input="n\n")

    assert result.exit_code != 0
    client.make_request.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_import_bundle_uploads_zip_archive_as_multipart(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    mock_response = MagicMock()
    mock_response.content = b""
    client.make_request.return_value = mock_response

    bundle = tmp_path / "my-bundle.zip"
    bundle.write_bytes(b"PK\x03\x04zip-bytes")

    result = runner.invoke(
        app,
        [
            "rulesets",
            "import-bundle",
            "--file",
            str(bundle),
            "--overwrite-rulesets",
            "--yes",
        ],
    )

    assert result.exit_code == 0
    (call,) = client.make_request.call_args_list
    assert call.args == ("POST", "/api/import/v1/")
    assert call.kwargs["data"] == {
        "overwrite_rulesets": "true",
        "overwrite_libraries": "false",
        "overwrite_seed_files": "false",
    }
    (upload,) = call.kwargs["files"]
    assert upload.field_name == "zip_archive"
    assert upload.filename == "my-bundle.zip"
    assert upload.content_type == "application/zip"


@patch(f"{MODULE}.get_client")
def test_system_export_alias_warns_and_delegates(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = MagicMock()
    mock_get_client.return_value = client
    mock_response = MagicMock()
    mock_response.content = b"zip-body"
    client.make_request.return_value = mock_response

    output = tmp_path / "export.zip"
    result = runner.invoke(app, ["system", "export", "--output", str(output)])

    assert result.exit_code == 0
    assert "deprecated" in result.stderr.lower()
    assert output.read_bytes() == b"zip-body"
