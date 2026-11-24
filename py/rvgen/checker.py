"""check 的 P0 通路：只读 schema lint。

语义 diff（YAML 期望 vs node_graph.json 实际）从 P1 开始实现；本模块现在只保证：
- rvgen.yaml / node_graph.json / layout.json 能按契约校验；
- 诊断带点号 json_path；
- 退出码严格遵循 0/1/2/3；
- 不写任何文件。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError, best_match

from . import __version__
from .diag import DiagnosticSink, Location

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


def _lint_yaml(
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
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = Location(file=file_label)
        if mark is not None:
            where = Location(file=file_label, line=mark.line + 1, col=mark.column + 1)
        sink.error("E09", f"YAML 解析失败：{exc}", where, hint="检查缩进、冒号与引号")
        return None
    if not isinstance(document, dict):
        sink.error("E09", "顶层必须是 mapping", Location(file=file_label))
        return None
    if not _validate(document, schema, file_label, sink):
        return None
    return document


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


def _lint_project(root: Path, sink: DiagnosticSink) -> None:
    schema_rvgen = _load_schema("rvgen", sink)
    schema_graph = _load_schema("node_graph", sink)
    schema_layout = _load_schema("layout", sink)
    if schema_rvgen is None or schema_graph is None or schema_layout is None:
        return

    rvgen_path = root / "rvgen.yaml"
    if _lint_yaml(rvgen_path, root, schema_rvgen, sink) is None:
        return

    graph_path = root / "node_graph.json"
    if graph_path.exists():
        graph = _lint_json(graph_path, root, schema_graph, sink)
        if graph is not None:
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
        sink.error("E00", "check --fix 尚未实现：P0 的 check 不写文件；--fix 属 P2")
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
