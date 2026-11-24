"""P1 checker 内部通路：渲染、路径、契约读取与 schema 提示的边界。"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema.exceptions import ValidationError

import rvgen.checker as checker
from rvgen.diag import DiagnosticSink


def test_render_quiet_drops_info_lines(capsys) -> None:
    sink = DiagnosticSink()
    sink.info("I02", "只是提示")
    sink.warning("W03", "需要关注")
    checker._render(sink, "text", quiet=True)
    err = capsys.readouterr().err
    assert "W03" in err
    assert "I02" not in err


def test_relative_falls_back_when_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "elsewhere" / "f.txt"
    assert checker._relative(outside, root) == outside.as_posix()


def test_load_schema_missing_file_marks_io_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(checker, "SCHEMA_DIR", tmp_path)
    sink = DiagnosticSink()
    assert checker._load_schema("nope", sink) is None
    assert sink.io_failure is True
    assert [item.code for item in sink.items] == ["E09"]


def test_load_schema_invalid_json_reports_position(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "bad.schema.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(checker, "SCHEMA_DIR", tmp_path)
    sink = DiagnosticSink()
    assert checker._load_schema("bad", sink) is None
    assert sink.io_failure is True
    assert sink.items[0].where.line == 1


def test_json_path_maps_module_index_to_name() -> None:
    document = {"modules": [{"name": "uart"}]}
    error = ValidationError(
        "'stage' does not match any of the regexes: '^x-'",
        validator="additionalProperties",
        path=deque(["modules", 0]),
    )
    assert checker._json_path(error, document) == "modules.uart.stage"


def test_json_path_keeps_index_for_unnamed_module() -> None:
    document = {"modules": [{"kind": "module"}]}
    error = ValidationError(
        "'x' does not match any of the regexes", validator="additionalProperties", path=deque(["modules", 0])
    )
    assert checker._json_path(error, document) == "modules.0.x"


def test_json_path_appends_required_field() -> None:
    document = {"modules": [{"name": "uart"}]}
    error = ValidationError("'ports' is a required property", validator="required", path=deque(["modules", 0]))
    assert checker._json_path(error, document) == "modules.uart.ports"


def test_json_path_appends_required_field_at_root() -> None:
    error = ValidationError("'top' is a required property", validator="required", path=deque())
    assert checker._json_path(error, {}) == "top"


@pytest.mark.parametrize(
    ("validator", "expected"),
    [
        ("required", "补齐必填字段"),
        ("additionalProperties", "删除未声明字段；plugin 扩展字段必须使用 x- 前缀"),
        ("oneOf", "检查判别式字段（kind/source/dir）与对应分支的必填项"),
        ("enum", "检查取值是否在允许集合内"),
        ("pattern", "检查标识符/版本号/摘要格式"),
        ("const", "schema_version 必须与当前契约一致"),
        ("type", None),
    ],
)
def test_hint_for_covers_each_validator(validator: str, expected: str | None) -> None:
    assert checker._hint_for(SimpleNamespace(validator=validator)) == expected


def test_read_text_failure_marks_io(tmp_path: Path) -> None:
    sink = DiagnosticSink()
    assert checker._read_text(tmp_path, "dir", sink) is None
    assert sink.io_failure is True
    assert sink.items[0].code == "E09"


def test_lint_json_unreadable_file_returns_none(tmp_path: Path) -> None:
    sink = DiagnosticSink()
    assert checker._lint_json(tmp_path, tmp_path, {"type": "object"}, sink) is None
    assert sink.io_failure is True


def test_lint_json_non_object_top_level(tmp_path: Path) -> None:
    path = tmp_path / "node_graph.json"
    path.write_text("[]", encoding="utf-8")
    sink = DiagnosticSink()
    schema = {"type": "object"}
    assert checker._lint_json(path, tmp_path, schema, sink) is None
    assert sink.items[0].message == "顶层必须是 object"


def test_lint_contracts_reports_broken_schema(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "broken.schema.json").write_text(json.dumps({"type": 123}), encoding="utf-8")
    monkeypatch.setattr(checker, "SCHEMA_DIR", tmp_path)
    monkeypatch.setattr(checker, "SCHEMA_NAMES", ("broken",))
    sink = DiagnosticSink()
    checker._lint_contracts(sink)
    assert sink.items[0].code == "E09"
    assert "自身非法" in sink.items[0].message


def test_lint_contracts_skips_unreadable_schema(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(checker, "SCHEMA_DIR", tmp_path)
    monkeypatch.setattr(checker, "SCHEMA_NAMES", ("missing",))
    sink = DiagnosticSink()
    checker._lint_contracts(sink)
    assert [item.code for item in sink.items] == ["E09"]


def test_lint_project_stops_when_graph_schema_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(checker, "_load_schema", lambda name, sink: None)
    sink = DiagnosticSink()
    checker._lint_project(tmp_path, sink)
    assert sink.items == []
