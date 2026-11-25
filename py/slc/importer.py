"""从 Verilog 模块头反向生成 slc.yaml 骨架（§1.2 假设：只解析模块头/端口/参数）。"""

from __future__ import annotations

import re
from typing import Any, Iterable

from .diag import Diagnostic, Location

_MODULE_RE = re.compile(
    r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)\s*(?:#\s*\((.*?)\)\s*)?\((.*?)\)\s*;",
    re.S | re.I,
)
_MODULE_NO_PORTS_RE = re.compile(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)\s*;", re.S | re.I)
_RANGE_RE = re.compile(r"\[\s*([^:\]]+)\s*:\s*([^\]]+)\s*\]")
_DIR_RE = re.compile(r"\b(input|output|inout)\b", re.I)
_IFDEF_RE = re.compile(r"^\s*`(ifdef|ifndef)\b", re.I)
_ELSE_RE = re.compile(r"^\s*`(else|elsif)\b", re.I)
_ENDIF_RE = re.compile(r"^\s*`endif\b", re.I)
_KEYWORDS = {
    "input",
    "output",
    "inout",
    "wire",
    "reg",
    "logic",
    "signed",
    "unsigned",
    "integer",
    "int",
    "bit",
    "parameter",
    "localparam",
}


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", lambda match: "\n" * match.group(0).count("\n"), text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def _mask_ifdef(text: str) -> tuple[str, int]:
    """把 `ifdef 包裹的内容替换成空行，并统计被跳过的端口声明数。"""

    lines = text.splitlines(keepends=True)
    depth = 0
    skipped = 0
    output: list[str] = []
    for line in lines:
        if _IFDEF_RE.match(line):
            depth += 1
            output.append("\n")
            continue
        if _ELSE_RE.match(line) and depth:
            output.append("\n")
            continue
        if _ENDIF_RE.match(line) and depth:
            depth -= 1
            output.append("\n")
            continue
        if depth:
            if re.search(r"\b(input|output|inout)\b", line, re.I):
                skipped += 1
            output.append("\n")
            continue
        output.append(line)
    return "".join(output), skipped


def _split_top(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    if "".join(current).strip():
        parts.append("".join(current))
    return parts


def _width_of(segment: str) -> int | str | None:
    match = _RANGE_RE.search(segment)
    if match is None:
        return None
    msb_raw = match.group(1).strip()
    lsb_raw = match.group(2).strip()
    try:
        msb = int(msb_raw, 0)
        lsb = int(lsb_raw, 0)
    except ValueError:
        param = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_$]*)\s*-\s*1", msb_raw)
        if param is not None and lsb_raw == "0":
            return param.group(1)
        return f"{msb_raw}:{lsb_raw}"
    return abs(msb - lsb) + 1


def _names_of(segment: str) -> list[str]:
    text = _DIR_RE.sub(" ", segment)
    text = _RANGE_RE.sub(" ", text)
    text = re.sub(r"=.*", " ", text)
    names: list[str] = []
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_$]*", text):
        if token.lower() in _KEYWORDS:
            continue
        names.append(token)
    return names


def _parse_params(text: str | None) -> list[dict[str, Any]]:
    if not text:
        return []
    params: list[dict[str, Any]] = []
    for segment in _split_top(text):
        cleaned = re.sub(r"^\s*(parameter|localparam)\b", " ", segment, flags=re.I).strip()
        match = re.match(
            r"(?:(?:integer|int|logic|bit|signed|unsigned|string)\s+|\[[^\]]*\]\s*)*"
            r"([A-Za-z_][A-Za-z0-9_$]*)\s*=\s*(.+)$",
            cleaned,
            re.S,
        )
        if match is None:
            continue
        name = match.group(1)
        raw = match.group(2).strip()
        if re.fullmatch(r"-?\d+", raw):
            value: Any = int(raw)
        else:
            value = raw
        params.append({"name": name, "default": value})
    return params


def _parse_ansi_ports(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    ports: list[dict[str, Any]] = []
    unresolved: list[str] = []
    current_dir: str | None = None
    for segment in _split_top(text):
        stripped = segment.strip()
        if not stripped:
            continue
        match = _DIR_RE.search(stripped)
        if match is not None:
            current_dir = match.group(1).lower()
        names = _names_of(stripped)
        if current_dir is None:
            unresolved.extend(names)
            continue
        if not names:
            unresolved.append(stripped)
            continue
        width = _width_of(stripped)
        for name in names:
            port: dict[str, Any] = {"name": name, "dir": current_dir}
            if width is not None:
                port["width"] = width
            ports.append(port)
    return ports, unresolved


def _parse_body_ports(body: str, names: Iterable[str]) -> tuple[list[dict[str, Any]], list[str]]:
    ports: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for name in names:
        pattern = re.compile(
            r"\b(input|output|inout)\b\s*([^;]*?)\b" + re.escape(name) + r"\b\s*(?:=[^;]*)?;",
            re.I | re.S,
        )
        match = pattern.search(body)
        if match is None:
            unresolved.append(name)
            continue
        statement = match.group(0)
        port: dict[str, Any] = {"name": name, "dir": match.group(1).lower()}
        width = _width_of(statement)
        if width is not None:
            port["width"] = width
        ports.append(port)
    return ports, unresolved


def _project_name(module_name: str, override: str | None) -> str:
    if override is not None:
        return override
    base = re.sub(r"[^a-z0-9_]", "_", module_name.lower())
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,31}", base):
        base = ("p_" + base)[:32]
        base = re.sub(r"_+$", "", base)
        if len(base) < 3:
            base = "imported_project"
    return base


def import_verilog(
    source: str,
    *,
    source_name: str = "<verilog>",
    project_name: str | None = None,
) -> tuple[dict[str, Any] | None, list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    text = _strip_comments(source)
    masked, skipped = _mask_ifdef(text)
    if skipped:
        diagnostics.append(
            Diagnostic(
                code="I05",
                severity="I",
                message=f"`ifdef 包裹的 {skipped} 条端口声明已跳过，需人工补",
                where=Location(file=source_name),
            )
        )

    match = _MODULE_RE.search(masked)
    if match is not None:
        module_name = match.group(1)
        params = _parse_params(match.group(2))
        body_start = match.end()
        ansi_ports, unresolved = _parse_ansi_ports(match.group(3))
        body = masked[body_start:]
        body_ports, body_unresolved = _parse_body_ports(body, [port["name"] for port in ansi_ports] + unresolved)
        by_name = {port["name"]: port for port in body_ports}
        ports = [by_name.get(port["name"], port) for port in ansi_ports]
        if not ports:
            # 非 ANSI 写法：头部只列名字
            header_names = _names_of(match.group(3))
            body_ports, body_unresolved = _parse_body_ports(body, header_names)
            ports = body_ports
        unresolved_names = [name for name in body_unresolved if name not in {port["name"] for port in ports}]
    else:
        no_ports = _MODULE_NO_PORTS_RE.search(masked)
        if no_ports is None:
            diagnostics.append(
                Diagnostic(
                    code="E09",
                    severity="E",
                    message="无法解析 module 头",
                    where=Location(file=source_name),
                    hint="只支持 module <name> [#(...)] (...); 与 module <name>;",
                )
            )
            return None, diagnostics
        module_name = no_ports.group(1)
        params = []
        ports = []
        unresolved_names = []

    skeleton: dict[str, Any] = {
        "schema_version": "1.1.0",
        "project": {
            "name": _project_name(module_name, project_name),
            "top": "top",
            "default_clock": "clk",
            "reset": {"name": "rst_n", "polarity": "active_low", "sync": True, "levels": 2},
        },
        "clocks": [{"name": "clk", "freq_hz": 50000000, "domain_id": "sys", "source": "pad"}],
        "modules": [
            {
                "name": module_name,
                "kind": "module",
                "clock": "clk",
                "params": params,
                "ports": ports,
            }
        ],
        "top": {"ports": [], "tieoffs": []},
    }

    todos = [
        "modules[0].kind 使用默认 module",
        "modules[0].clock 使用默认 clk",
        "端口 kind 默认 data，domain 默认 null",
        "top.ports 为空，需按实际顶层映射补齐",
    ]
    if unresolved_names:
        todos.append(f"未解析端口：{', '.join(unresolved_names)}")
    diagnostics.append(
        Diagnostic(
            code="W14",
            severity="W",
            message="import 生成的骨架有默认值待确认：" + "；".join(todos),
            where=Location(file=source_name),
        )
    )
    return skeleton, diagnostics
