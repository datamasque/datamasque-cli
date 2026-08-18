from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from datamasque.client import DataMasqueClient
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.table_reference import TableReference, TableReferenceFormat, TableReferenceOptions
from typer.testing import CliRunner

from datamasque_cli.errors import ExitCode
from datamasque_cli.main import app

MODULE = "datamasque_cli.commands.table_references"


def _mock_client() -> MagicMock:
    return MagicMock(spec=DataMasqueClient)


def _reference(**overrides: object) -> TableReference:
    defaults: dict[str, object] = {"name": "customer_identities", "connection": "conn-1", "source": "in/customers.csv"}
    defaults.update(overrides)
    return TableReference(**defaults)


def _api_error(status: HTTPStatus, detail: object = "boom") -> DataMasqueApiError:
    response = MagicMock()
    response.status_code = status
    response.json.return_value = {"detail": detail}
    return DataMasqueApiError("request failed", response=response)


# -- list -------------------------------------------------------------------


@patch(f"{MODULE}.get_client")
def test_list_references(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.list_table_references.return_value = [_reference(id="ref-1")]

    result = runner.invoke(app, ["table-references", "list", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == [
        {"id": "ref-1", "name": "customer_identities", "connection": "conn-1", "source": "in/customers.csv"}
    ]


def test_list_references_table_output(runner: CliRunner) -> None:
    with patch(f"{MODULE}.get_client") as mock_get_client:
        client = _mock_client()
        mock_get_client.return_value = client
        client.list_table_references.return_value = [_reference(id="ref-1")]

        result = runner.invoke(app, ["table-references", "list"])

    assert result.exit_code == 0
    assert "ref-1" in result.stdout
    assert "customer_identities" in result.stdout


@patch(f"{MODULE}.get_client")
def test_list_references_not_supported_by_server(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.list_table_references.side_effect = _api_error(HTTPStatus.NOT_FOUND)

    result = runner.invoke(app, ["table-references", "list"])

    assert result.exit_code == ExitCode.NOT_FOUND
    assert "not supported by this datamasque version" in result.stderr.lower()


@patch(f"{MODULE}.get_client")
def test_list_references_non_404_error_surfaces_cleanly(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.list_table_references.side_effect = _api_error(HTTPStatus.INTERNAL_SERVER_ERROR, "service unavailable")

    result = runner.invoke(app, ["table-references", "list"])

    assert result.exit_code == ExitCode.ERROR
    assert "service unavailable" in " ".join(result.stderr.lower().split())
    assert "Traceback" not in result.stderr


# -- get ----------------------------------------------------------------------


@patch(f"{MODULE}.get_client")
def test_get_reference(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.get_table_reference_by_name.return_value = _reference(
        id="ref-1", options=TableReferenceOptions(format=TableReferenceFormat.parquet)
    )

    result = runner.invoke(app, ["table-references", "get", "customer_identities", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["format"] == "parquet"
    assert payload["connection"] == "conn-1"


@patch(f"{MODULE}.get_client")
def test_get_reference_with_no_options_shows_null_not_fabricated_defaults(
    mock_get_client: MagicMock, runner: CliRunner
) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.get_table_reference_by_name.return_value = _reference(id="ref-1")

    result = runner.invoke(app, ["table-references", "get", "customer_identities", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["format"] is None
    assert payload["delimiter"] is None


@patch(f"{MODULE}.get_client")
def test_get_reference_not_found(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.get_table_reference_by_name.return_value = None

    result = runner.invoke(app, ["table-references", "get", "missing"])

    assert result.exit_code == ExitCode.NOT_FOUND
    assert "not found" in result.stderr.lower()


@patch(f"{MODULE}.get_client")
def test_get_reference_not_supported_by_server(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.get_table_reference_by_name.side_effect = _api_error(HTTPStatus.NOT_FOUND)

    result = runner.invoke(app, ["table-references", "get", "customer_identities"])

    assert result.exit_code == ExitCode.NOT_FOUND
    assert "not supported by this datamasque version" in result.stderr.lower()


# -- create (flags) -----------------------------------------------------------


@patch(f"{MODULE}.get_client")
def test_create_reference_by_connection_name(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.list_connections.return_value = [SimpleNamespace(id="conn-1", name="input")]

    result = runner.invoke(
        app,
        [
            "table-references",
            "create",
            "--name",
            "customer_identities",
            "--connection",
            "input",
            "--source",
            "in/customers.csv",
        ],
    )

    assert result.exit_code == 0
    client.create_or_update_table_reference.assert_called_once()
    created = client.create_or_update_table_reference.call_args[0][0]
    assert created.connection == "conn-1"
    assert created.options is None


@patch(f"{MODULE}.get_client")
def test_create_reference_by_connection_id(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.list_connections.return_value = [SimpleNamespace(id="conn-1", name="input")]

    result = runner.invoke(
        app,
        [
            "table-references",
            "create",
            "--name",
            "customer_identities",
            "--connection",
            "conn-1",
            "--source",
            "public.customers",
        ],
    )

    assert result.exit_code == 0
    created = client.create_or_update_table_reference.call_args[0][0]
    assert created.connection == "conn-1"


@patch(f"{MODULE}.get_client")
def test_create_reference_unknown_connection_aborts(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.list_connections.return_value = [SimpleNamespace(id="conn-1", name="input")]

    result = runner.invoke(
        app,
        [
            "table-references",
            "create",
            "--name",
            "customer_identities",
            "--connection",
            "nope",
            "--source",
            "in/customers.csv",
        ],
    )

    assert result.exit_code == ExitCode.NOT_FOUND
    client.create_or_update_table_reference.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_create_reference_with_csv_options(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.list_connections.return_value = [SimpleNamespace(id="conn-1", name="input")]

    result = runner.invoke(
        app,
        [
            "table-references",
            "create",
            "--name",
            "customer_identities",
            "--connection",
            "input",
            "--source",
            "in/customers.csv",
            "--format",
            "csv",
            "--delimiter",
            ";",
            "--encoding",
            "latin-1",
            "--quotechar",
            "'",
            "--null-string",
            "NULL",
        ],
    )

    assert result.exit_code == 0
    created = client.create_or_update_table_reference.call_args[0][0]
    assert created.options == TableReferenceOptions(
        format=TableReferenceFormat.csv, delimiter=";", encoding="latin-1", quotechar="'", null_string="NULL"
    )


@patch(f"{MODULE}.get_client")
def test_create_reference_parquet_with_csv_options_passes_through(
    mock_get_client: MagicMock, runner: CliRunner
) -> None:
    """CSV options are unfiltered pass-through — the server, not the CLI, decides whether they apply."""
    client = _mock_client()
    mock_get_client.return_value = client
    client.list_connections.return_value = [SimpleNamespace(id="conn-1", name="input")]

    result = runner.invoke(
        app,
        [
            "table-references",
            "create",
            "--name",
            "customer_identities",
            "--connection",
            "input",
            "--source",
            "in/customers.parquet",
            "--format",
            "parquet",
            "--delimiter",
            ";",
        ],
    )

    assert result.exit_code == 0
    created = client.create_or_update_table_reference.call_args[0][0]
    assert created.options == TableReferenceOptions(format=TableReferenceFormat.parquet, delimiter=";")


@patch(f"{MODULE}.get_client")
def test_create_reference_missing_required_flags_aborts(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client

    result = runner.invoke(app, ["table-references", "create", "--name", "customer_identities"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "provide either --file" in result.stderr.lower()
    client.create_or_update_table_reference.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_create_reference_server_validation_error_surfaces_cleanly(
    mock_get_client: MagicMock, runner: CliRunner
) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.list_connections.return_value = [SimpleNamespace(id="conn-1", name="input")]
    client.create_or_update_table_reference.side_effect = _api_error(
        HTTPStatus.BAD_REQUEST, "table reference with this name already exists"
    )

    result = runner.invoke(
        app,
        [
            "table-references",
            "create",
            "--name",
            "customer_identities",
            "--connection",
            "input",
            "--source",
            "in/customers.csv",
        ],
    )

    assert result.exit_code == ExitCode.INVALID_INPUT
    assert "already exists" in " ".join(result.stderr.lower().split())
    assert "Traceback" not in result.stderr


@patch(f"{MODULE}.get_client")
def test_create_reference_not_supported_by_server(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.list_connections.return_value = [SimpleNamespace(id="conn-1", name="input")]
    client.create_or_update_table_reference.side_effect = _api_error(HTTPStatus.NOT_FOUND)

    result = runner.invoke(
        app,
        [
            "table-references",
            "create",
            "--name",
            "customer_identities",
            "--connection",
            "input",
            "--source",
            "in/customers.csv",
        ],
    )

    assert result.exit_code == ExitCode.NOT_FOUND
    assert "not supported by this datamasque version" in result.stderr.lower()


# -- create (--file) ------------------------------------------------------------


@patch(f"{MODULE}.get_client")
def test_create_reference_from_json_file(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = _mock_client()
    mock_get_client.return_value = client

    reference_file = tmp_path / "reference.json"
    reference_file.write_text(
        json.dumps(
            {
                "name": "customer_identities",
                "connection": "conn-1",
                "source": "in/customers.csv",
                "options": {"format": "csv", "delimiter": ";"},
            }
        )
    )

    result = runner.invoke(app, ["table-references", "create", "--file", str(reference_file)])

    assert result.exit_code == 0
    created = client.create_or_update_table_reference.call_args[0][0]
    assert created.name == "customer_identities"
    assert created.connection == "conn-1"
    assert created.source == "in/customers.csv"
    assert created.options == TableReferenceOptions(delimiter=";")
    client.list_connections.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_create_reference_file_not_found_aborts(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = _mock_client()
    mock_get_client.return_value = client

    result = runner.invoke(app, ["table-references", "create", "--file", str(tmp_path / "missing.json")])

    assert result.exit_code == ExitCode.NOT_FOUND
    client.create_or_update_table_reference.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_create_reference_file_bad_json_aborts(mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not valid json")

    result = runner.invoke(app, ["table-references", "create", "--file", str(bad_file)])

    assert result.exit_code == ExitCode.INVALID_INPUT
    client.create_or_update_table_reference.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_create_reference_file_with_other_flags_aborts(
    mock_get_client: MagicMock, runner: CliRunner, tmp_path: Path
) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    reference_file = tmp_path / "reference.json"
    reference_file.write_text(
        json.dumps({"name": "customer_identities", "connection": "conn-1", "source": "in/customers.csv"})
    )

    result = runner.invoke(
        app, ["table-references", "create", "--file", str(reference_file), "--source", "override.csv"]
    )

    assert result.exit_code == ExitCode.INVALID_INPUT
    client.create_or_update_table_reference.assert_not_called()


# -- update ---------------------------------------------------------------------


@patch(f"{MODULE}.get_client")
def test_update_reference_merges_only_passed_fields(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.get_table_reference_by_name.return_value = _reference(
        id="ref-1", options=TableReferenceOptions(delimiter=",", encoding="utf-8")
    )

    result = runner.invoke(
        app, ["table-references", "update", "customer_identities", "--source", "in/new.csv", "--delimiter", ";"]
    )

    assert result.exit_code == 0
    client.update_table_reference.assert_called_once()
    updated = client.update_table_reference.call_args[0][0]
    assert updated.id == "ref-1"
    assert updated.source == "in/new.csv"
    assert updated.connection == "conn-1"
    assert updated.options.delimiter == ";"
    assert updated.options.encoding == "utf-8"


@patch(f"{MODULE}.get_client")
def test_update_reference_format_when_options_previously_none(mock_get_client: MagicMock, runner: CliRunner) -> None:
    """A reference whose options were never set has no existing values to preserve on a full PUT."""
    client = _mock_client()
    mock_get_client.return_value = client
    client.get_table_reference_by_name.return_value = _reference(id="ref-1")

    result = runner.invoke(app, ["table-references", "update", "customer_identities", "--format", "parquet"])

    assert result.exit_code == 0
    updated = client.update_table_reference.call_args[0][0]
    assert updated.id == "ref-1"
    assert updated.options == TableReferenceOptions(format=TableReferenceFormat.parquet)


@patch(f"{MODULE}.get_client")
def test_update_reference_connection_by_name(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.get_table_reference_by_name.return_value = _reference(id="ref-1")
    client.list_connections.return_value = [SimpleNamespace(id="conn-2", name="other")]

    result = runner.invoke(app, ["table-references", "update", "customer_identities", "--connection", "other"])

    assert result.exit_code == 0
    updated = client.update_table_reference.call_args[0][0]
    assert updated.id == "ref-1"
    assert updated.connection == "conn-2"


@patch(f"{MODULE}.get_client")
def test_update_reference_unknown_connection_aborts(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.get_table_reference_by_name.return_value = _reference(id="ref-1")
    client.list_connections.return_value = [SimpleNamespace(id="conn-2", name="other")]

    result = runner.invoke(app, ["table-references", "update", "customer_identities", "--connection", "nope"])

    assert result.exit_code == ExitCode.NOT_FOUND
    client.update_table_reference.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_update_reference_aborts_without_any_fields(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.get_table_reference_by_name.return_value = _reference(id="ref-1")

    result = runner.invoke(app, ["table-references", "update", "customer_identities"])

    assert result.exit_code == ExitCode.INVALID_INPUT
    client.get_table_reference_by_name.assert_not_called()
    client.update_table_reference.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_update_reference_aborts_when_missing(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.get_table_reference_by_name.return_value = None

    result = runner.invoke(app, ["table-references", "update", "missing", "--source", "in/new.csv"])

    assert result.exit_code == ExitCode.NOT_FOUND
    client.update_table_reference.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_update_reference_not_supported_by_server(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.get_table_reference_by_name.side_effect = _api_error(HTTPStatus.NOT_FOUND)

    result = runner.invoke(app, ["table-references", "update", "customer_identities", "--source", "in/new.csv"])

    assert result.exit_code == ExitCode.NOT_FOUND
    assert "not supported by this datamasque version" in result.stderr.lower()


@patch(f"{MODULE}.get_client")
def test_update_reference_missing_on_write_is_not_reported_as_unsupported(
    mock_get_client: MagicMock, runner: CliRunner
) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.get_table_reference_by_name.return_value = _reference(id="ref-1")
    client.update_table_reference.side_effect = _api_error(HTTPStatus.NOT_FOUND, "Not found.")

    result = runner.invoke(app, ["table-references", "update", "customer_identities", "--source", "in/new.csv"])

    assert result.exit_code == ExitCode.NOT_FOUND
    assert "not supported" not in result.stderr.lower()


# -- delete -----------------------------------------------------------------


@patch(f"{MODULE}.get_client")
def test_delete_reference_confirmed(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.get_table_reference_by_name.return_value = _reference(id="ref-1")

    result = runner.invoke(app, ["table-references", "delete", "customer_identities", "--yes"])

    assert result.exit_code == 0
    client.delete_table_reference_by_name_if_exists.assert_called_once_with("customer_identities")


@patch(f"{MODULE}.get_client")
def test_delete_reference_declined(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.get_table_reference_by_name.return_value = _reference(id="ref-1")

    result = runner.invoke(app, ["table-references", "delete", "customer_identities"], input="n\n")

    assert result.exit_code == ExitCode.CANCELLED
    client.delete_table_reference_by_name_if_exists.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_delete_reference_aborts_when_missing(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.get_table_reference_by_name.return_value = None

    result = runner.invoke(app, ["table-references", "delete", "missing", "--yes"])

    assert result.exit_code == ExitCode.NOT_FOUND
    client.delete_table_reference_by_name_if_exists.assert_not_called()


@patch(f"{MODULE}.get_client")
def test_delete_reference_not_supported_by_server(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.get_table_reference_by_name.side_effect = _api_error(HTTPStatus.NOT_FOUND)

    result = runner.invoke(app, ["table-references", "delete", "customer_identities", "--yes"])

    assert result.exit_code == ExitCode.NOT_FOUND
    assert "not supported by this datamasque version" in result.stderr.lower()


@patch(f"{MODULE}.get_client")
def test_delete_reference_non_404_error_surfaces_cleanly(mock_get_client: MagicMock, runner: CliRunner) -> None:
    client = _mock_client()
    mock_get_client.return_value = client
    client.get_table_reference_by_name.return_value = _reference(id="ref-1")
    client.delete_table_reference_by_name_if_exists.side_effect = _api_error(HTTPStatus.CONFLICT, "referenced by a run")

    result = runner.invoke(app, ["table-references", "delete", "customer_identities", "--yes"])

    assert result.exit_code == ExitCode.CONFLICT
    assert "referenced by a run" in " ".join(result.stderr.lower().split())
