from __future__ import annotations

import json

import pytest

from datamasque_cli.output import abort, print_json, redact_sensitive_fields, render_output


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
