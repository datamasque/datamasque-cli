from __future__ import annotations

import json

import pytest

from datamasque_cli.output import (
    EXIT_CODE_BY_ERROR,
    ErrorCode,
    abort,
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


def test_print_success_suppressed_in_agent_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DM_OUTPUT", "json")
    print_success("looks good")
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""
