from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from datamasque.client.exceptions import DataMasqueApiError
from datamasque.client.models.ruleset import RulesetId
from datamasque.client.models.status import ValidationErrorDetails, ValidationStatus

from datamasque_cli.errors import (
    EXIT_CODE_BY_ERROR,
    ErrorCode,
    ExitCode,
    abort,
    abort_if_invalid,
    extract_server_error_reason,
    require_id_or_abort,
)
from datamasque_cli.fileio import (
    read_json_object_or_abort,
    read_text_or_abort,
    write_bytes_or_abort,
    write_text_or_abort,
)
from datamasque_cli.output import (
    is_agent_context,
    print_json,
    print_success,
    print_table,
    redact_sensitive_fields,
    render_output,
    should_emit_json,
)


def test_print_json_outputs_indented(capsys: pytest.CaptureFixture[str]) -> None:
    print_json({"key": "value"})
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data == {"key": "value"}
    assert "\n" in captured.out


def test_render_output_json_mode(capsys: pytest.CaptureFixture[str]) -> None:
    render_output([{"a": 1}], is_json=True)
    data = json.loads(capsys.readouterr().out)
    assert data == [{"a": 1}]


def test_render_output_empty_data(capsys: pytest.CaptureFixture[str]) -> None:
    render_output([], is_json=False)
    captured = capsys.readouterr()
    assert "no results" in captured.err.lower()


def test_render_output_dict_mode(capsys: pytest.CaptureFixture[str]) -> None:
    render_output({"name": "test"}, is_json=False)
    captured = capsys.readouterr()
    assert "name" in captured.out


def test_render_output_plain_string(capsys: pytest.CaptureFixture[str]) -> None:
    render_output("hello world", is_json=False)
    captured = capsys.readouterr()
    assert "hello world" in captured.out


def test_abort_exits_with_code_1() -> None:
    with pytest.raises(SystemExit) as exc_info:
        abort("something broke")
    assert exc_info.value.code == 1


def test_redact_sensitive_fields_replaces_password_values() -> None:
    out = redact_sensitive_fields({"host": "db.example.com", "password": "s3cret"})
    assert out["host"] == "db.example.com"
    assert out["password"] == "<redacted>"


def test_redact_sensitive_fields_matches_on_substrings() -> None:
    out = redact_sensitive_fields(
        {
            "access_token": "abc",
            "api_key": "def",
            "aws_secret_access_key": "ghi",
            "database_credential": "jkl",
            "name": "public",
        }
    )
    assert out["access_token"] == "<redacted>"
    assert out["api_key"] == "<redacted>"
    assert out["aws_secret_access_key"] == "<redacted>"
    assert out["database_credential"] == "<redacted>"
    assert out["name"] == "public"


def test_redact_sensitive_fields_is_case_insensitive() -> None:
    out = redact_sensitive_fields({"PASSWORD": "s3cret", "DB_Password": "t0p"})
    assert out["PASSWORD"] == "<redacted>"
    assert out["DB_Password"] == "<redacted>"


def test_print_table_does_not_truncate_long_ids_in_narrow_terminal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Force a narrow console so Rich would have to compress columns.
    monkeypatch.setenv("COLUMNS", "80")
    uuid = "529ed6f4-77b8-47be-9afb-0dffe6dbb9ef"
    print_table(
        ["id", "name", "type"],
        [[uuid, "db_postgres_long_name_here", "Database"]],
    )
    out = capsys.readouterr().out
    # UUID must be present in full (with no ellipsis truncation) — possibly folded across lines.
    flattened = out.replace("\n", "").replace(" ", "").replace("│", "").replace("┃", "")
    assert uuid in flattened
    assert "…" not in out


def test_is_agent_context_respects_dm_output_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DM_OUTPUT", "table")
    monkeypatch.setenv("AI_AGENT", "1")
    assert is_agent_context() is False


def test_is_agent_context_detects_dm_output_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DM_OUTPUT", "json")
    assert is_agent_context() is True


def test_is_agent_context_detects_ai_agent_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DM_OUTPUT", raising=False)
    monkeypatch.setenv("AI_AGENT", "claude-code/2.x")
    assert is_agent_context() is True


def test_should_emit_json_flag_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    # DM_OUTPUT=table forces human mode — but explicit --json must still win.
    monkeypatch.setenv("DM_OUTPUT", "table")
    assert should_emit_json(is_json_flag=True) is True


def test_render_output_auto_json_in_agent_context(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DM_OUTPUT", "json")
    render_output([{"id": "abc", "name": "foo"}], is_json=False)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data == [{"id": "abc", "name": "foo"}]


def test_abort_emits_structured_envelope_in_agent_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DM_OUTPUT", "json")
    with pytest.raises(SystemExit) as exc_info:
        abort("Connection 'foo' not found.", code=ErrorCode.NOT_FOUND, hint="Run dm connections list.")
    assert exc_info.value.code == 3  # not_found exit code
    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload == {
        "error": {
            "code": "not_found",
            "message": "Connection 'foo' not found.",
            "hint": "Run dm connections list.",
        }
    }
    # Stdout must stay clean on error so an agent's pipeline doesn't trip.
    assert captured.out == ""


def test_abort_human_mode_prints_red_error(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("DM_OUTPUT", "table")
    with pytest.raises(SystemExit):
        abort("nope", code=ErrorCode.NOT_FOUND)
    captured = capsys.readouterr()
    assert "nope" in captured.err
    # In human mode we don't dump JSON.
    assert "{" not in captured.err


def test_abort_folds_details_into_the_envelope_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DM_OUTPUT", "json")
    with pytest.raises(SystemExit):
        abort(
            "Ruleset 'rs.yaml' is invalid",
            code=ErrorCode.INVALID_INPUT,
            details=["unknown mask type (line 7)", "tasks must not be empty"],
        )
    payload = json.loads(capsys.readouterr().err)
    assert payload["error"]["message"] == (
        "Ruleset 'rs.yaml' is invalid: unknown mask type (line 7); tasks must not be empty"
    )


def test_abort_prints_one_detail_per_line_in_human_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DM_OUTPUT", "table")
    with pytest.raises(SystemExit):
        abort(
            "Ruleset 'rs.yaml' is invalid",
            code=ErrorCode.INVALID_INPUT,
            details=["unknown mask type (line 7)", "tasks must not be empty"],
        )
    lines = [line.rstrip() for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert lines == [
        "Error: Ruleset 'rs.yaml' is invalid:",
        "  unknown mask type (line 7)",
        "  tasks must not be empty",
    ]


def test_abort_keeps_the_shape_of_a_multi_line_detail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DM_OUTPUT", "table")
    detail = "unknown property on line 3, column 1:\n    garbage: true\n    ^ (line: 3)"

    with pytest.raises(SystemExit):
        abort("Library 'lib.yaml' is invalid", code=ErrorCode.INVALID_INPUT, details=[detail])

    lines = [line.rstrip() for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert lines == [
        "Error: Library 'lib.yaml' is invalid:",
        "  unknown property on line 3, column 1:",
        "      garbage: true",
        "      ^ (line: 3)",
    ]


def test_abort_if_invalid_returns_when_validation_passed() -> None:
    abort_if_invalid("Ruleset 'rs.yaml'", ValidationStatus.valid, [])


def test_abort_if_invalid_reports_every_error_with_its_position(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DM_OUTPUT", "json")
    errors = [
        ValidationErrorDetails(message="unknown property `badkey5`", line_number=11, column_number=13),
        ValidationErrorDetails(message="unknown mask type", line_number=7),
        ValidationErrorDetails(message="tasks must not be empty"),
    ]

    with pytest.raises(SystemExit) as exc_info:
        abort_if_invalid("Ruleset 'rs.yaml' (database)", ValidationStatus.invalid, errors)

    assert exc_info.value.code == ExitCode.INVALID_INPUT
    assert json.loads(capsys.readouterr().err)["error"]["message"] == (
        "Ruleset 'rs.yaml' (database) is invalid: "
        "unknown property `badkey5` (line 11, column 13); "
        "unknown mask type (line 7); "
        "tasks must not be empty"
    )


def test_abort_if_invalid_without_errors_still_aborts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DM_OUTPUT", "json")
    with pytest.raises(SystemExit) as exc_info:
        abort_if_invalid("Ruleset 'rs.yaml'", ValidationStatus.invalid, [])

    assert exc_info.value.code == ExitCode.INVALID_INPUT
    assert json.loads(capsys.readouterr().err)["error"]["message"] == "Ruleset 'rs.yaml' is invalid."


@pytest.mark.parametrize(
    ("code", "expected_exit"),
    [
        (ErrorCode.ERROR, 1),
        (ErrorCode.NOT_FOUND, 3),
        (ErrorCode.INVALID_INPUT, 4),
        (ErrorCode.AMBIGUOUS, 5),
        (ErrorCode.AUTH_REQUIRED, 6),
        (ErrorCode.AUTH_FAILED, 7),
        (ErrorCode.CONFLICT, 8),
        (ErrorCode.TRANSPORT_ERROR, 9),
        (ErrorCode.CANCELLED, 10),
        (ErrorCode.FORBIDDEN, 11),
    ],
)
def test_abort_maps_code_to_documented_exit_code(code: ErrorCode, expected_exit: int) -> None:
    with pytest.raises(SystemExit) as exc_info:
        abort("...", code=code)
    assert exc_info.value.code == expected_exit


def test_exit_code_table_covers_every_error_code() -> None:
    # Guard: every ErrorCode member must have an exit-code mapping. This trips
    # if a new ErrorCode is added without updating EXIT_CODE_BY_ERROR.
    assert set(EXIT_CODE_BY_ERROR.keys()) == set(ErrorCode)


def test_require_id_returns_the_id_when_present() -> None:
    assert require_id_or_abort(RulesetId("rs-1"), "ruleset 'payroll'") == "rs-1"


def test_require_id_aborts_when_the_server_omitted_it(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        require_id_or_abort(None, "ruleset 'payroll'")

    assert exc_info.value.code == ExitCode.ERROR
    assert "ruleset 'payroll' without an id" in _unwrapped(capsys.readouterr().err)


def test_print_success_suppressed_in_agent_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DM_OUTPUT", "json")
    print_success("looks good")
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""


# -- file helpers ----------------------------------------------------------


def _unwrapped(text: str) -> str:
    """Rejoin a message Rich broke across lines to fit the terminal."""
    return " ".join(text.split())


def _without_whitespace(text: str) -> str:
    """Drop every space, for paths Rich may have split mid-token."""
    return "".join(text.split())


def test_read_text_returns_utf8_content(tmp_path: Path) -> None:
    file = tmp_path / "rules.yaml"
    file.write_text("name: café\n", encoding="utf-8")

    assert read_text_or_abort(file) == "name: café\n"


def test_read_text_rejects_other_encodings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    file = tmp_path / "latin1.yaml"
    file.write_bytes("name: café\n".encode("latin-1"))

    with pytest.raises(SystemExit) as exc_info:
        read_text_or_abort(file)

    assert exc_info.value.code == ExitCode.INVALID_INPUT
    assert "is not valid UTF-8" in _unwrapped(capsys.readouterr().err)


@pytest.mark.parametrize("content", ["", "\n", "   \n\t\n"])
def test_read_text_rejects_empty_content(tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str) -> None:
    file = tmp_path / "empty.yaml"
    file.write_text(content, encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        read_text_or_abort(file)

    assert exc_info.value.code == ExitCode.INVALID_INPUT
    assert "is empty" in _unwrapped(capsys.readouterr().err)


def test_read_text_missing_file_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        read_text_or_abort(tmp_path / "absent.yaml")

    assert exc_info.value.code == ExitCode.NOT_FOUND


def test_read_text_directory_is_invalid_input(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        read_text_or_abort(tmp_path)

    assert exc_info.value.code == ExitCode.INVALID_INPUT


def test_read_errors_name_the_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    file = tmp_path / "absent.yaml"

    with pytest.raises(SystemExit):
        read_text_or_abort(file)

    assert _without_whitespace(str(file)) in _without_whitespace(capsys.readouterr().err)


def test_read_json_object_parses_content(tmp_path: Path) -> None:
    file = tmp_path / "request.json"
    file.write_text('{"connection": "abc"}', encoding="utf-8")

    assert read_json_object_or_abort(file) == {"connection": "abc"}


def test_read_json_object_rejects_malformed_content(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    file = tmp_path / "broken.json"
    file.write_text('{"connection": ', encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        read_json_object_or_abort(file)

    assert exc_info.value.code == ExitCode.INVALID_INPUT
    assert "is not valid JSON" in _unwrapped(capsys.readouterr().err)


@pytest.mark.parametrize("content", ['["a", "b"]', '"just a string"', "42", "null"])
def test_read_json_object_rejects_non_objects(tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str) -> None:
    """Valid JSON that is not an object would crash the callers, which index into it."""
    file = tmp_path / "array.json"
    file.write_text(content, encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        read_json_object_or_abort(file)

    assert exc_info.value.code == ExitCode.INVALID_INPUT
    assert "must contain a JSON object" in _unwrapped(capsys.readouterr().err)


def test_write_text_round_trips_utf8(tmp_path: Path) -> None:
    file = tmp_path / "out.yaml"

    write_text_or_abort(file, "name: café\n")

    assert file.read_bytes() == "name: café\n".encode()


def test_write_text_to_missing_directory_aborts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "no_such_dir" / "out.yaml"

    with pytest.raises(SystemExit) as exc_info:
        write_text_or_abort(target, "content")

    assert exc_info.value.code == ExitCode.INVALID_INPUT
    assert _without_whitespace(str(target)) in _without_whitespace(capsys.readouterr().err)


def test_write_bytes_to_a_directory_aborts(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        write_bytes_or_abort(tmp_path, b"PK\x03\x04")

    assert exc_info.value.code == ExitCode.INVALID_INPUT


# -- server error reasons --------------------------------------------------


def _api_error(body: object) -> DataMasqueApiError:
    response = MagicMock(status_code=400)
    response.json.return_value = body
    return DataMasqueApiError("boom", response=response)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"detail": "The requested run was not found."}, "The requested run was not found."),
        ({"detail": [{"loc": ["body", "name"], "msg": "field required"}]}, "name: field required"),
        ({"error": "boom"}, "boom"),
        ({"ruleset": ['Ruleset "x" is invalid.']}, 'ruleset: Ruleset "x" is invalid.'),
        ({"non_field_errors": ["Exactly one option must be provided."]}, "Exactly one option must be provided."),
        ({"host": ["required"], "port": ["not an int"]}, "host: required; port: not an int"),
    ],
    ids=["detail", "detail_list", "error", "field", "non_field", "multiple_fields"],
)
def test_server_error_reason_reads_every_body_shape(body: object, expected: str) -> None:
    assert extract_server_error_reason(_api_error(body)) == expected


@pytest.mark.parametrize(
    "body", [{}, {"id": 5, "name": "x"}, [], "plain text"], ids=["empty", "no_errors", "list", "str"]
)
def test_server_error_reason_is_none_without_one(body: object) -> None:
    assert extract_server_error_reason(_api_error(body)) is None


def test_server_error_reason_is_none_when_body_is_not_json() -> None:
    response = MagicMock(status_code=404)
    response.json.side_effect = ValueError("no json")

    assert extract_server_error_reason(DataMasqueApiError("404", response=response)) is None
