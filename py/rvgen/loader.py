"""YAML → DesignModel：schema 校验、版本兼容、行号与语义引用检查。

loader 只依赖 model/diag/plugins，禁止 import graph/emitter。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from .diag import Diagnostic, DiagnosticSink, Location
from .model import (
    CORE_KINDS,
    Cdc,
    Clock,
    DesignModel,
    InterfaceLib,
    InterfaceSignal,
    InterfaceUse,
    ModuleDecl,
    Param,
    Port,
    PortDir,
    PortKind,
    Project,
    ResetCfg,
    Tieoff,
    Top,
    TopPort,
    YAML_FILE,
)
from .plugins import Plugin

SCHEMA_VERSION = "1.1.0"
SUPPORTED_MAJOR = 1
MAX_ANCHOR_DEPTH = 10

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "rvgen.schema.json"

_LINE_KEYS: tuple[tuple[str, str], ...] = (
    ("modules", "name"),
    ("clocks", "name"),
    ("cdc", "id"),
    ("interfaces", "name"),
    ("top", "name"),
)


def _load_schema() -> dict[str, Any]:
    import json

    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _segment(part: Any) -> str:
    if isinstance(part, int):
        return f"[{part}]"
    if isinstance(part, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part):
        return f".{part}"
    return f"[{part!r}]"


def format_json_path(parts: Sequence[Any]) -> str:
    text = ""
    for index, part in enumerate(parts):
        if index == 0:
            text = str(part)
        else:
            text += _segment(part)
    return text


def json_path(error: Any, document: Mapping[str, Any]) -> str:
    """把 jsonschema 的 absolute_path 还原成用户可搜的点号路径。"""

    path = list(error.absolute_path)
    if error.validator == "additionalProperties":
        match = re.search(r"'([^']+)'", error.message)
        if match:
            path.append(match.group(1))
    elif error.validator == "required":
        match = re.search(r"'([^']+)'", error.message)
        if match:
            path.append(match.group(1))
    if len(path) >= 2 and path[0] == "modules" and isinstance(path[1], int):
        try:
            path[1] = document["modules"][path[1]]["name"]
        except (IndexError, KeyError, TypeError):
            pass
    return format_json_path(path)


_HINTS = {
    "additionalProperties": "核心 schema 不接受该字段；领域字段请写成 x-<plugin>-* 并由 plugin 校验",
    "required": "缺少必填字段",
    "enum": "取值不在允许集合内",
    "oneOf": "多态分支不匹配：确认判别字段（source/kind/dir）与其余字段组合",
    "type": "字段类型不符合契约",
    "minLength": "字符串过短",
    "minimum": "数值小于允许下限",
}


def _schema_diagnostic(error: Any, document: Mapping[str, Any], source_name: str) -> Diagnostic:
    return Diagnostic(
        code="E09",
        severity="E",
        message=error.message,
        where=Location(file=source_name, json_path=json_path(error, document)),
        hint=_HINTS.get(error.validator),
    )


def _find_key(node: yaml.nodes.Node | None, key: str) -> yaml.nodes.Node | None:
    if not isinstance(node, yaml.nodes.MappingNode):
        return None
    for key_node, value_node in node.value:
        if isinstance(key_node, yaml.nodes.ScalarNode) and key_node.value == key:
            return value_node
    return None


def _line_index(text: str) -> dict[str, dict[str, tuple[int, int]]]:
    try:
        root = yaml.compose(text)
    except yaml.YAMLError:
        return {}
    if not isinstance(root, yaml.nodes.MappingNode):
        return {}
    index: dict[str, dict[str, tuple[int, int]]] = {}
    for section, name_key in _LINE_KEYS:
        sequence = _find_key(root, section)
        if not isinstance(sequence, yaml.nodes.SequenceNode):
            continue
        entries: dict[str, tuple[int, int]] = {}
        for item in sequence.value:
            if not isinstance(item, yaml.nodes.MappingNode):
                continue
            name_node = _find_key(item, name_key)
            if isinstance(name_node, yaml.nodes.ScalarNode):
                entries[str(name_node.value)] = (item.start_mark.line + 1, item.end_mark.line + 1)
        index[section] = entries
    return index


_ANCHOR_RE = re.compile(r"&([A-Za-z0-9_-]+)")
_ALIAS_RE = re.compile(r"\*([A-Za-z0-9_-]+)")


def _anchor_depth(text: str) -> int:
    """按行统计锚点引用链长度；YAML 的嵌套锚点会形成 anchor→alias 依赖。"""

    definitions: dict[str, list[str]] = {}
    for line in text.splitlines():
        anchors = _ANCHOR_RE.findall(line)
        aliases = _ALIAS_RE.findall(line)
        for anchor in anchors:
            definitions.setdefault(anchor, []).extend(aliases)

    def depth_of(name: str, seen: frozenset[str]) -> int:
        if name in seen:
            return 0
        children = definitions.get(name, ())
        return 1 + max((depth_of(child, seen | {name}) for child in children), default=0)

    return max((depth_of(name, frozenset()) for name in definitions), default=0)


def _ext(data: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if isinstance(key, str) and key.startswith("x-")}


def _port_dir(value: Any) -> PortDir:
    try:
        return PortDir(value)
    except ValueError:
        return PortDir.input


def _port_kind(value: Any) -> PortKind:
    try:
        return PortKind(value)
    except ValueError:
        return PortKind.data


def _parse_reset(data: Mapping[str, Any]) -> ResetCfg:
    return ResetCfg(
        name=str(data["name"]),
        polarity=str(data.get("polarity", "active_low")),
        sync=bool(data.get("sync", True)),
        levels=int(data.get("levels", 2)),
        extensions=_ext(data),
    )


def _parse_project(data: Mapping[str, Any]) -> Project:
    return Project(
        name=str(data["name"]),
        top=str(data["top"]),
        default_clock=str(data["default_clock"]),
        reset=_parse_reset(data["reset"]),
        extensions=_ext(data),
    )


def _parse_clock(data: Mapping[str, Any], lines: Mapping[str, tuple[int, int]]) -> Clock:
    name = str(data["name"])
    start, end = lines.get(name, (None, None))
    return Clock(
        name=name,
        freq_hz=data["freq_hz"],
        domain_id=str(data["domain_id"]),
        source=str(data["source"]),
        parent=data.get("parent"),
        extensions=_ext(data),
        line=start,
        end_line=end,
    )


def _parse_cdc(data: Mapping[str, Any], lines: Mapping[str, tuple[int, int]]) -> Cdc:
    cdc_id = str(data["id"])
    start, _ = lines.get(cdc_id, (None, None))
    return Cdc(
        id=cdc_id,
        from_domain=str(data["from"]),
        to_domain=str(data["to"]),
        kind=str(data["kind"]),
        width=data.get("width"),
        depth=data.get("depth"),
        almost_full=data.get("almost_full"),
        extensions=_ext(data),
        line=start,
    )


def _parse_signal(data: Mapping[str, Any]) -> InterfaceSignal:
    return InterfaceSignal(
        name=str(data["name"]),
        dir=_port_dir(data["dir"]),
        width=data.get("width"),
        kind=_port_kind(data.get("kind", "data")),
        domain=data.get("domain"),
        default=data.get("default"),
        connect=data.get("connect"),
        doc=data.get("doc"),
        extensions=_ext(data),
    )


def _parse_library(data: Mapping[str, Any]) -> InterfaceLib:
    return InterfaceLib(
        name=str(data["name"]),
        type=str(data["type"]),
        params=dict(data.get("params") or {}),
        signals=tuple(_parse_signal(item) for item in data.get("signals") or ()),
        dir_flip=bool(data.get("dir_flip", False)),
        extensions=_ext(data),
    )


def _parse_interface_use(data: Mapping[str, Any]) -> InterfaceUse:
    return InterfaceUse(
        name=str(data["name"]),
        type=str(data["type"]),
        params=dict(data.get("params") or {}),
        signals=tuple(_parse_signal(item) for item in data.get("signals") or ()),
        dir_flip=bool(data.get("dir_flip", False)),
        extensions=_ext(data),
    )


def _parse_param(data: Mapping[str, Any]) -> Param:
    return Param(
        name=str(data["name"]),
        width=data.get("width"),
        expr=data.get("expr"),
        default=data.get("default"),
        doc=data.get("doc"),
    )


def _parse_port(data: Mapping[str, Any]) -> Port:
    return Port(
        name=str(data["name"]),
        dir=_port_dir(data["dir"]),
        width=data.get("width"),
        kind=_port_kind(data.get("kind", "data")),
        domain=data.get("domain"),
        default=data.get("default"),
        connect=data.get("connect"),
        doc=data.get("doc"),
        extensions=_ext(data),
    )


def _contract_keys(extensions: Mapping[str, Any], plugins: Sequence[Plugin], config: Mapping[str, Any]) -> frozenset[str]:
    plugin_ids = {plugin.id for plugin in plugins}
    keys: set[str] = set()
    for key in extensions:
        plugin_id = key[2:].split("-", 1)[0]
        if plugin_id not in plugin_ids:
            continue
        plugin_config = config.get(plugin_id)
        if plugin_config is None or not plugin_config.get("enabled", True):
            continue
        keys.add(key)
    return frozenset(keys)


def _parse_module(
    data: Mapping[str, Any],
    lines: Mapping[str, tuple[int, int]],
    plugins: Sequence[Plugin],
    plugins_config: Mapping[str, Any],
) -> ModuleDecl:
    name = str(data["name"])
    start, end = lines.get(name, (None, None))
    extensions = _ext(data)
    return ModuleDecl(
        name=name,
        kind=str(data["kind"]),
        clock=str(data["clock"]),
        status=data.get("status"),
        todo=data.get("todo"),
        params=tuple(_parse_param(item) for item in data.get("params") or ()),
        ports=tuple(_parse_port(item) for item in data.get("ports") or ()),
        interfaces=tuple(_parse_interface_use(item) for item in data.get("interfaces") or ()),
        extensions=extensions,
        contract_extension_keys=_contract_keys(extensions, plugins, plugins_config),
        line=start,
        end_line=end,
    )


def _parse_top_port(data: Mapping[str, Any], lines: Mapping[str, tuple[int, int]]) -> TopPort:
    name = str(data["name"])
    start, _ = lines.get(name, (None, None))
    return TopPort(
        name=name,
        dir=str(data["dir"]),
        from_ref=data.get("from"),
        to_refs=tuple(data.get("to") or ()),
        role=str(data.get("role", "data")),
        polarity=data.get("polarity"),
        default=data.get("default"),
        line=start,
    )


def _parse_top(data: Mapping[str, Any], lines: Mapping[str, tuple[int, int]]) -> Top:
    return Top(
        ports=tuple(_parse_top_port(item, lines) for item in data.get("ports") or ()),
        tieoffs=tuple(Tieoff(port=str(item["port"]), value=str(item["value"])) for item in data.get("tieoffs") or ()),
        extensions=_ext(data),
    )


def _build_model(
    document: Mapping[str, Any],
    *,
    original_version: str,
    lines: Mapping[str, Mapping[str, tuple[int, int]]],
    source_text: str,
    source_name: str,
    plugins: Sequence[Plugin],
) -> DesignModel:
    plugins_config = dict(document.get("plugins") or {})
    return DesignModel(
        schema_version=original_version,
        project=_parse_project(document["project"]),
        clocks=tuple(_parse_clock(item, lines.get("clocks", {})) for item in document["clocks"]),
        modules=tuple(_parse_module(item, lines.get("modules", {}), plugins, plugins_config) for item in document["modules"]),
        cdc=tuple(_parse_cdc(item, lines.get("cdc", {})) for item in document.get("cdc") or ()),
        interfaces=tuple(_parse_library(item) for item in document.get("interfaces") or ()),
        top=_parse_top(document["top"], lines.get("top", {})),
        plugins=plugins_config,
        extensions=_ext(document),
        source_text=source_text,
        source_name=source_name,
    )


def _validate_schema(document: Mapping[str, Any], source_name: str) -> list[Diagnostic]:
    validator = Draft202012Validator(_load_schema())
    error = best_match(validator.iter_errors(document))
    if error is None:
        return []
    return [_schema_diagnostic(error, document, source_name)]


def _from_document(
    document: Mapping[str, Any],
    *,
    source_text: str,
    lines: Mapping[str, Mapping[str, tuple[int, int]]],
    source_name: str,
    plugins: Sequence[Plugin],
) -> tuple[DesignModel | None, list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    version = str(document.get("schema_version", ""))
    match = _SEMVER_RE.fullmatch(version)
    if match is None:
        diagnostics.append(
            Diagnostic(
                code="E09",
                severity="E",
                message=f"schema_version 不是 semver：{version!r}",
                where=Location(file=source_name, json_path="schema_version"),
                hint="当前支持 1.1.0",
            )
        )
        return None, diagnostics
    major, _minor, _patch = (int(part) for part in match.groups())
    if major != SUPPORTED_MAJOR:
        diagnostics.append(
            Diagnostic(
                code="E09",
                severity="E",
                message=f"schema_version 主版本不兼容：{version}（当前 {SCHEMA_VERSION}）",
                where=Location(file=source_name, json_path="schema_version"),
                hint="先运行 rvgen migrate",
            )
        )
        return None, diagnostics
    if version != SCHEMA_VERSION:
        diagnostics.append(
            Diagnostic(
                code="I02",
                severity="I",
                message=f"schema_version {version} 与当前 {SCHEMA_VERSION} 不同，按当前 minor 契约加载",
                where=Location(file=source_name, json_path="schema_version"),
            )
        )

    working = dict(document)
    working["schema_version"] = SCHEMA_VERSION
    schema_diagnostics = _validate_schema(working, source_name)
    if schema_diagnostics:
        return None, [*diagnostics, *schema_diagnostics]

    model = _build_model(
        document,
        original_version=version,
        lines=lines,
        source_text=source_text,
        source_name=source_name,
        plugins=plugins,
    )
    diagnostics.extend(model.validate_semantic(plugins))
    return model, diagnostics


def load_data(
    document: Mapping[str, Any],
    plugins: Sequence[Plugin] = (),
    *,
    source_name: str = YAML_FILE,
    source_text: str = "",
    sink: DiagnosticSink | None = None,
) -> tuple[DesignModel | None, list[Diagnostic]]:
    """从已解析的 mapping 构建模型；供测试与 import 复用。"""

    return _from_document(
        document,
        source_text=source_text,
        lines={},
        source_name=source_name,
        plugins=plugins,
    )


def load_text(
    text: str,
    plugins: Sequence[Plugin] = (),
    *,
    source_name: str = YAML_FILE,
    sink: DiagnosticSink | None = None,
) -> tuple[DesignModel | None, list[Diagnostic]]:
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        return None, [
            Diagnostic(
                code="E09",
                severity="E",
                message=f"YAML 解析失败：{getattr(exc, 'problem', exc)}",
                where=Location(file=source_name, line=(mark.line + 1) if mark is not None else None),
            )
        ]
    if not isinstance(document, Mapping):
        return None, [
            Diagnostic(
                code="E09",
                severity="E",
                message="rvgen.yaml 顶层必须是 mapping",
                where=Location(file=source_name),
            )
        ]

    diagnostics: list[Diagnostic] = []
    depth = _anchor_depth(text)
    if depth > MAX_ANCHOR_DEPTH:
        diagnostics.append(
            Diagnostic(
                code="W10",
                severity="W",
                message=f"YAML 锚点嵌套 {depth} 层，超过 {MAX_ANCHOR_DEPTH} 层上限",
                where=Location(file=source_name),
                hint="展开锚点或改用显式字段",
            )
        )

    model, produced = _from_document(
        document,
        source_text=text,
        lines=_line_index(text),
        source_name=source_name,
        plugins=plugins,
    )
    diagnostics.extend(produced)
    return model, diagnostics


def load(
    path: str | Path,
    plugins: Sequence[Plugin] = (),
    *,
    sink: DiagnosticSink | None = None,
) -> tuple[DesignModel | None, list[Diagnostic]]:
    project_file = Path(path)
    try:
        text = project_file.read_text(encoding="utf-8")
    except OSError as exc:
        if sink is not None:
            sink.io_failure = True
        return None, [
            Diagnostic(
                code="E09",
                severity="E",
                message=f"读取 {project_file.name} 失败：{exc}",
                where=Location(file=project_file.name),
            )
        ]
    return load_text(text, plugins, source_name=project_file.name, sink=sink)
