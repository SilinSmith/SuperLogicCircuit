"""check 通路：schema lint + loader/graph 语义校验 + 与 node_graph.json 的语义 diff。

本模块保证：
- rvgen.yaml 走 loader（schema + 引用检查），再跑 graph 的静态规则码；
- node_graph.json / layout.json 按契约 lint，并与期望图逐字段比较；
- 诊断带点号 json_path；
- 退出码严格遵循 0/1/2/3；
- 除显式 `--fix` 外不写任何文件。
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError, best_match

from . import __version__
from .diag import DiagnosticSink, Location
from .graph import NodeGraph
from .graph import build as build_graph
from .graph import write as write_graph
from .loader import load
from .plugins import discover

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "schema"
SCHEMA_NAMES = ("rvgen", "node_graph", "layout", "trace")


def _render(sink: DiagnosticSink, output_format: str, *, quiet: bool) -> None:
    stream = sys.stdout if output_format == "json" else sys.stderr
    if quiet and output_format == "text":
        filtered = DiagnosticSink()
        filtered.items = [item for item in sink.items if item.severity != "I"]
        filtered.io_failure = sink.io_failure
        filtered.render("text", stream=stream)
        return
    sink.render(output_format, stream=stream)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _load_schema(name: str, sink: DiagnosticSink) -> dict[str, Any] | None:
    path = SCHEMA_DIR / f"{name}.schema.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        sink.io_failure = True
        sink.error("E09", f"读取契约失败：{exc}", Location(file=path.as_posix()))
        return None
    except json.JSONDecodeError as exc:
        sink.io_failure = True
        sink.error(
            "E09",
            f"契约不是合法 JSON：{exc.msg}",
            Location(file=path.as_posix(), line=exc.lineno, col=exc.colno),
        )
        return None


def _json_path(error: ValidationError, document: Any) -> str:
    parts = list(error.absolute_path)
    if len(parts) >= 2 and parts[0] == "modules":
        index = parts[1]
        if isinstance(index, int) and isinstance(document, dict):
            modules = document.get("modules")
            if isinstance(modules, list) and 0 <= index < len(modules):
                module = modules[index]
                if isinstance(module, dict) and isinstance(module.get("name"), str):
                    parts[1] = module["name"]
    if error.validator == "additionalProperties":
        match = re.search(r"'([^']+)' does not match", error.message)
        if match:
            parts.append(match.group(1))
    elif error.validator == "required":
        match = re.search(r"'([^']+)' is a required property", error.message)
        if match and (not parts or parts[-1] != match.group(1)):
            parts.append(match.group(1))
    return ".".join(str(part) for part in parts)


def _hint_for(error: ValidationError) -> str | None:
    if error.validator == "required":
        return "补齐必填字段"
    if error.validator == "additionalProperties":
        return "删除未声明字段；plugin 扩展字段必须使用 x- 前缀"
    if error.validator == "oneOf":
        return "检查判别式字段（kind/source/dir）与对应分支的必填项"
    if error.validator == "enum":
        return "检查取值是否在允许集合内"
    if error.validator == "pattern":
        return "检查标识符/版本号/摘要格式"
    if error.validator == "const":
        return "schema_version 必须与当前契约一致"
    return None


def _validate(
    document: Any,
    schema: dict[str, Any],
    file_label: str,
    sink: DiagnosticSink,
) -> bool:
    errors = list(Draft202012Validator(schema).iter_errors(document))
    if not errors:
        return True
    error = best_match(errors)
    if error is None:
        error = errors[0]
    sink.error(
        "E09",
        error.message,
        Location(file=file_label, json_path=_json_path(error, document)),
        hint=_hint_for(error),
    )
    return False


def _read_text(path: Path, file_label: str, sink: DiagnosticSink) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        sink.io_failure = True
        sink.error("E09", f"读取文件失败：{exc}", Location(file=file_label))
        return None


def _lint_json(
    path: Path,
    root: Path,
    schema: dict[str, Any],
    sink: DiagnosticSink,
) -> dict[str, Any] | None:
    file_label = _relative(path, root)
    text = _read_text(path, file_label, sink)
    if text is None:
        return None
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        sink.error(
            "E09",
            f"JSON 解析失败：{exc.msg}",
            Location(file=file_label, line=exc.lineno, col=exc.colno),
        )
        return None
    if not isinstance(document, dict):
        sink.error("E09", "顶层必须是 object", Location(file=file_label))
        return None
    if not _validate(document, schema, file_label, sink):
        return None
    return document


def _lint_contracts(sink: DiagnosticSink) -> None:
    for name in SCHEMA_NAMES:
        schema = _load_schema(name, sink)
        if schema is None:
            continue
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            sink.error(
                "E09",
                f"契约 {name}.schema.json 自身非法：{exc.message}",
                Location(file=f"schema/{name}.schema.json", json_path="/".join(str(p) for p in exc.path)),
            )


_IGNORED_TOP_FIELDS = {"generated_by", "source_digest"}
_MAX_DIFFS = 20


@dataclass(frozen=True)
class Change:
    path: str
    expected: Any
    actual: Any


def _short(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= 80 else text[:77] + "..."


def _keyed(items: list[Any], key: str) -> dict[str, Any] | None:
    result: dict[str, Any] = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get(key), str):
            return None
        result[item[key]] = item
    return result


def _compare(path: str, expected: Any, actual: Any, changes: list[Change]) -> None:
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            if not path and key in _IGNORED_TOP_FIELDS:
                continue
            child = f"{path}.{key}" if path else key
            if key not in actual:
                changes.append(Change(child, expected[key], "<missing>"))
            elif key not in expected:
                changes.append(Change(child, "<missing>", actual[key]))
            else:
                _compare(child, expected[key], actual[key], changes)
        return

    if isinstance(expected, list) and isinstance(actual, list):
        if path == "nodes" or path == "edges":
            key = "id"
        elif path.startswith("nodes.") and path.endswith(".ports"):
            key = "name"
        else:
            key = ""
        if key:
            expected_map = _keyed(expected, key)
            actual_map = _keyed(actual, key)
            if expected_map is not None and actual_map is not None:
                for item_key in sorted(set(expected_map) | set(actual_map)):
                    child = f"{path}.{item_key}"
                    if item_key not in actual_map:
                        changes.append(Change(child, expected_map[item_key], "<missing>"))
                    elif item_key not in expected_map:
                        changes.append(Change(child, "<missing>", actual_map[item_key]))
                    else:
                        _compare(child, expected_map[item_key], actual_map[item_key], changes)
                return
        for index, (left, right) in enumerate(zip(expected, actual)):
            _compare(f"{path}[{index}]", left, right, changes)
        if len(expected) > len(actual):
            for index in range(len(actual), len(expected)):
                changes.append(Change(f"{path}[{index}]", expected[index], "<missing>"))
        elif len(actual) > len(expected):
            for index in range(len(expected), len(actual)):
                changes.append(Change(f"{path}[{index}]", "<missing>", actual[index]))
        return

    if expected != actual:
        changes.append(Change(path, expected, actual))


def diff_graphs(expected: NodeGraph, actual: dict[str, Any]) -> list[Change]:
    """返回从 rvgen.yaml 期望图到 node_graph.json 实际值的逐字段差异。"""
    changes: list[Change] = []
    _compare("", expected.document, actual, changes)
    return changes


def _report_diff(changes: list[Change], file_label: str, sink: DiagnosticSink) -> None:
    for change in changes[:_MAX_DIFFS]:
        sink.error(
            "E16",
            f"语义不一致：{change.path} 期望 {_short(change.expected)}，实际 {_short(change.actual)}",
            Location(file=file_label, json_path=change.path),
            hint="运行 rvgen check --fix 或 rvgen graph --write 重新生成",
        )
    if len(changes) > _MAX_DIFFS:
        sink.error(
            "E16",
            f"共 {len(changes)} 处语义差异，仅显示前 {_MAX_DIFFS} 处",
            Location(file=file_label),
            hint="运行 rvgen check --fix 或 rvgen graph --write 重新生成",
        )


def _fix_graph(root: Path, sink: DiagnosticSink) -> None:
    rvgen_path = root / "rvgen.yaml"
    if not rvgen_path.exists():
        sink.error("E00", f"未找到 {rvgen_path}", hint="在项目根运行 rvgen check --fix")
        return
    plugins = discover(sink)
    model, diagnostics = load(rvgen_path, plugins, sink=sink)
    sink.extend(diagnostics)
    if model is None or sink.has_errors():
        return
    graph = build_graph(model, sink)
    if sink.has_errors():
        return
    from .atomic import AtomicWriteError

    try:
        write_graph(graph, root / "node_graph.json", sink=sink)
    except AtomicWriteError as exc:
        sink.io_failure = True
        sink.error("E12", str(exc), hint="检查文件权限/占用后重试")


def _lint_project(root: Path, sink: DiagnosticSink) -> None:
    schema_graph = _load_schema("node_graph", sink)
    schema_layout = _load_schema("layout", sink)
    if schema_graph is None or schema_layout is None:
        return

    rvgen_path = root / "rvgen.yaml"
    plugins = discover(sink)
    model, diagnostics = load(rvgen_path, plugins, sink=sink)
    sink.extend(diagnostics)
    if model is None:
        return
    before_build = len(sink.items)
    expected_graph = build_graph(model, sink)

    graph_path = root / "node_graph.json"
    if graph_path.exists():
        graph = _lint_json(graph_path, root, schema_graph, sink)
        if graph is not None:
            build_errors = [item for item in sink.items[before_build:] if item.severity == "E"]
            if not build_errors:
                _report_diff(diff_graphs(expected_graph, graph), _relative(graph_path, root), sink)
            generated_by = graph.get("generated_by")
            expected = f"rvgen {__version__}"
            if generated_by != expected:
                sink.warning(
                    "W10",
                    f"node_graph.json 的 generated_by={generated_by!r} 与当前 CLI {expected!r} 不一致",
                    Location(file=_relative(graph_path, root), json_path="generated_by"),
                    hint="运行 rvgen graph --write 重新生成；--strict 会把该 warning 当失败",
                )

    layout_path = root / "layout.json"
    if layout_path.exists():
        _lint_json(layout_path, root, schema_layout, sink)


def run_check(
    project_root: Path,
    sink: DiagnosticSink,
    *,
    strict: bool = False,
    output_format: str = "text",
    quiet: bool = False,
    fix: bool = False,
) -> int:
    root = Path(project_root).resolve()

    if fix:
        fix_sink = DiagnosticSink()
        _fix_graph(root, fix_sink)
        if fix_sink.io_failure or fix_sink.has_errors():
            sink.extend(fix_sink.items)
            sink.io_failure = fix_sink.io_failure
            _render(sink, output_format, quiet=quiet)
            return sink.exit_code(strict=strict)

    rvgen_path = root / "rvgen.yaml"
    if rvgen_path.exists():
        _lint_project(root, sink)
    elif (root / "schema" / "rvgen.schema.json").exists():
        _lint_contracts(sink)
    else:
        sink.error(
            "E00",
            f"未找到 {rvgen_path}，且当前目录不是 rvgen 仓库根",
            Location(file=str(rvgen_path)),
            hint="在项目根运行，或先执行 rvgen init",
        )

    _render(sink, output_format, quiet=quiet)
    return sink.exit_code(strict=strict)
