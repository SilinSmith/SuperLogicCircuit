from __future__ import annotations

import json

from rvgen.diag import DiagnosticSink, Location


def test_exit_code_contract() -> None:
    sink = DiagnosticSink()
    assert sink.exit_code() == 0
    assert sink.exit_code(strict=True) == 0

    sink.info("I01", "windows fsync skipped")
    assert sink.exit_code() == 0
    assert sink.exit_code(strict=True) == 0

    sink.warning("W10", "missing loc")
    assert sink.exit_code() == 0
    assert sink.exit_code(strict=True) == 2

    sink.error("E09", "schema mismatch")
    assert sink.exit_code() == 1
    assert sink.exit_code(strict=True) == 1


def test_io_failure_beats_other_codes() -> None:
    sink = DiagnosticSink()
    sink.error("E09", "schema mismatch")
    sink.io_failure = True
    assert sink.exit_code() == 3


def test_location_and_text_rendering() -> None:
    sink = DiagnosticSink()
    sink.error(
        "E09",
        "width 不是整数",
        Location(file="rvgen.yaml", line=12, col=5, json_path="modules.0.ports.1.width"),
        hint="改成整数或参数名",
    )
    text = sink.render("text")
    assert "rvgen.yaml:12:5 (modules.0.ports.1.width)" in text
    assert "E09 error width 不是整数" in text
    assert "hint: 改成整数或参数名" in text


def test_json_rendering() -> None:
    sink = DiagnosticSink()
    sink.warning("W11", "plugin skipped", Location(node_id="mod:uart"))
    text = sink.render("json")
    payload = json.loads(text)
    assert payload["diagnostics"][0]["code"] == "W11"
    assert payload["diagnostics"][0]["severity"] == "warning"
    assert payload["diagnostics"][0]["location"]["node_id"] == "mod:uart"


def test_github_rendering_escapes_message() -> None:
    sink = DiagnosticSink()
    sink.error("E00", "bad\nmessage 100%", Location(file="a.yaml", line=3, col=1))
    text = sink.render("github")
    assert text.startswith("::error file=a.yaml,line=3,col=1::E00")
    assert "%25" in text
    assert "%0A" in text
