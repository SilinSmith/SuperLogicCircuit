"""trace：TSV → JSONL 归一化、trace_summary 聚合、stats 概览。

只读 trace 文本与 node_graph.json；绝不改 RTL / 图文件。
诊断：E11（元数据/列数/Ext 非法）、W15（未声明 Ext 键，保留）、W05（利用率 >1）。
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, IO, Iterator

from .diag import DiagnosticSink, Location

META_PREFIX = "#rvgen-meta"
COLUMNS = ("Time", "Cycle", "Loc", "State", "Ids", "Ext")
CORE_EXT_KEYS = frozenset({"arc", "cdc"})
PLUGIN_EXT_KEYS: dict[str, frozenset[str]] = {
    "cpu": frozenset({"pipe", "ctrl", "regw", "icache", "dcache", "dec"}),
    "bus": frozenset({"txn", "stall"}),
}
UNIT_TO_NS = {"ps": 1e-3, "ns": 1.0, "us": 1e3, "ms": 1e6, "s": 1e9}
NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
VALUE_RE = re.compile(r"[A-Za-z0-9_.+-]+\Z")
TIME_RE = re.compile(r"[0-9]+(\.[0-9]+)?\Z")
UNIT_RE = re.compile(r"([0-9]*)(ps|ns|us|ms|s)\Z")
ARC_RE = re.compile(r"([A-Za-z0-9_.:>-]+):([01])\Z")
CDC_RE = re.compile(r"([A-Za-z0-9_.+-]+):([A-Za-z0-9_.+-]+):([A-Za-z0-9_.+-]+)\Z")


@dataclass
class NormalizeStats:
    rows: int = 0
    cycles: int = 0
    unknown_keys: set[str] | None = None


def _fail(sink: DiagnosticSink, message: str, path: Path, line: int, col: int | None = None) -> None:
    sink.error("E11", message, Location(file=str(path), line=line, col=col))


def parse_meta(line: str, path: Path, sink: DiagnosticSink) -> tuple[str, float]:
    """解析 `#rvgen-meta\tschema=core\ttimescale=ns`；缺失/非法 → E11。"""
    parts = line.split("\t")
    if not parts or parts[0].strip() != META_PREFIX:
        _fail(sink, "VCD/trace 缺少 #rvgen-meta 元数据行", path, 1)
        return "core", 1.0
    fields: dict[str, str] = {}
    for index, token in enumerate(parts[1:], start=2):
        if "=" not in token:
            _fail(sink, f"元数据字段非法：{token!r}", path, 1, index)
            continue
        key, value = token.split("=", 1)
        fields[key.strip()] = value.strip()
    flavor = fields.get("schema", "")
    if not flavor:
        _fail(sink, "元数据缺少 schema=<flavor>", path, 1)
        flavor = "core"
    unit = fields.get("timescale", "")
    match = UNIT_RE.fullmatch(unit)
    if match is None:
        _fail(sink, f"元数据 timescale 非法：{unit!r}（允许 ps/ns/us/ms/s）", path, 1)
        return flavor, 1.0
    multiplier = int(match.group(1) or "1")
    return flavor, UNIT_TO_NS[match.group(2)] * multiplier


def _parse_ids(value: str, path: Path, line: int, sink: DiagnosticSink) -> dict[str, str]:
    if value == "-":
        return {}
    result: dict[str, str] = {}
    for pair in value.split(","):
        if "=" not in pair:
            _fail(sink, f"Ids 片段非法：{pair!r}", path, line)
            continue
        key, raw = pair.split("=", 1)
        if not NAME_RE.fullmatch(key) or not VALUE_RE.fullmatch(raw):
            _fail(sink, f"Ids 键值非法：{pair!r}", path, line, 5)
            continue
        result[key] = raw
    return result


def _parse_ext(
    value: str,
    flavor: str,
    declared: frozenset[str],
    path: Path,
    line: int,
    sink: DiagnosticSink,
    unknown: set[str],
    plugin_ns: dict[str, str],
    unknown_ns: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    arcs: list[dict[str, Any]] = []
    cdcs: list[dict[str, str]] = []
    if value == "-":
        return arcs, cdcs
    for entry in value.split(";"):
        if "=" not in entry:
            _fail(sink, f"Ext 片段非法：{entry!r}", path, line, 6)
            continue
        key, raw = entry.split("=", 1)
        if not NAME_RE.fullmatch(key):
            _fail(sink, f"Ext 键非法：{key!r}", path, line, 6)
            continue
        if key not in declared:
            unknown.add(key)
            if not VALUE_RE.fullmatch(raw):
                _fail(sink, f"Ext 值非法：{raw!r}", path, line, 6)
                continue
            unknown_ns[key] = raw
            continue
        if key == "arc":
            match = ARC_RE.fullmatch(raw)
            if match is None:
                _fail(sink, f"arc 值非法：{raw!r}（期望 src.port>dst.port:t）", path, line, 6)
                continue
            edge = match.group(1)
            if "->" not in edge:
                edge = edge.replace(">", "->", 1)
            arcs.append({"edge": edge, "toggle": int(match.group(2))})
        elif key == "cdc":
            match = CDC_RE.fullmatch(raw)
            if match is None:
                _fail(sink, f"cdc 值非法：{raw!r}（期望 id:afull:cnt）", path, line, 6)
                continue
            cdcs.append({"id": match.group(1), "afull": match.group(2), "cnt": match.group(3)})
        else:
            if not VALUE_RE.fullmatch(raw):
                _fail(sink, f"{key} 值非法：{raw!r}", path, line, 6)
                continue
            plugin_ns[key] = raw
    return arcs, cdcs


def _open_temp(dst: Path) -> tuple[IO[str], Path]:
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    return tmp.open("w", encoding="utf-8", newline="\n"), tmp


def normalize(
    src: Path,
    dst: Path | None,
    flavor: str = "auto",
    *,
    sink: DiagnosticSink | None = None,
) -> NormalizeStats:
    """流式归一化；任何 E11 都不会留下半截目标文件。"""
    sink = sink or DiagnosticSink()
    src = Path(src)
    stats = NormalizeStats(unknown_keys=set())
    declared_flavor = "core"
    declared_keys = CORE_EXT_KEYS
    timescale = 1.0
    previous_cycle: int | None = None
    warned: set[str] = set()

    stdout_mode = dst is None or str(dst) == "-"
    base = Path(f".rvgen-stdout-{uuid.uuid4().hex}.jsonl") if stdout_mode else Path(dst)
    handle, tmp = _open_temp(base)
    try:
        with src.open("r", encoding="utf-8", newline="") as source, handle as target:
            for line_no, raw_line in enumerate(source, start=1):
                line = raw_line.rstrip("\r\n")
                if not line:
                    continue
                if line_no == 1:
                    meta_flavor, timescale = parse_meta(line, src, sink)
                    if sink.has_errors():
                        raise _Abort()
                    declared_flavor = flavor if flavor != "auto" else meta_flavor
                    declared_keys = CORE_EXT_KEYS | PLUGIN_EXT_KEYS.get(declared_flavor, frozenset())
                    continue
                columns = line.split("\t")
                if len(columns) != len(COLUMNS):
                    _fail(
                        sink,
                        f"列数 {len(columns)} ≠ 6（Time/Cycle/Loc/State/Ids/Ext）",
                        src,
                        line_no,
                    )
                    raise _Abort()
                time_raw, cycle_raw, loc, state, ids_raw, ext_raw = columns
                if not TIME_RE.fullmatch(time_raw):
                    _fail(sink, f"Time 非法：{time_raw!r}", src, line_no, 1)
                    raise _Abort()
                if not cycle_raw.isdigit():
                    _fail(sink, f"Cycle 非法：{cycle_raw!r}", src, line_no, 2)
                    raise _Abort()
                cycle = int(cycle_raw)
                if previous_cycle is None and cycle != 0:
                    _fail(sink, f"Cycle 必须从 0 起：实际 {cycle}", src, line_no, 2)
                    raise _Abort()
                if previous_cycle is not None and cycle < previous_cycle:
                    _fail(sink, f"Cycle 回退：{previous_cycle} → {cycle}", src, line_no, 2)
                    raise _Abort()
                previous_cycle = cycle
                for col_index, text in ((3, loc), (4, state)):
                    if any(ch in '"\'\t{}' for ch in text) or (text != "-" and not text.strip()):
                        _fail(sink, f"{COLUMNS[col_index - 1]} 含非法字符：{text!r}", src, line_no, col_index)
                        raise _Abort()
                ids = _parse_ids(ids_raw, src, line_no, sink)
                plugin_ns: dict[str, str] = {}
                unknown_ns: dict[str, str] = {}
                arcs, cdcs = _parse_ext(
                    ext_raw,
                    declared_flavor,
                    declared_keys,
                    src,
                    line_no,
                    sink,
                    stats.unknown_keys,
                    plugin_ns,
                    unknown_ns,
                )
                if sink.has_errors():
                    raise _Abort()
                record: dict[str, Any] = {
                    "cycle": cycle,
                    "time_ns": round(float(time_raw) * timescale, 6),
                    "loc": loc,
                    "state": state,
                    "ids": ids,
                    "arc": arcs,
                    "cdc": cdcs,
                }
                if declared_flavor != "core" and plugin_ns:
                    record[f"p_{declared_flavor}"] = plugin_ns
                if unknown_ns:
                    record["ext"] = unknown_ns
                target.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                stats.rows += 1
                stats.cycles = cycle + 1
        if sink.has_errors():
            raise _Abort()
        for key in sorted(stats.unknown_keys or ()):
            if key not in warned:
                warned.add(key)
                sink.warning("W15", f"trace Ext 出现未声明的键 {key!r}，已原样保留", Location(file=str(src)))
        if not stdout_mode:
            os.replace(tmp, Path(dst))
        else:
            import sys

            with tmp.open("r", encoding="utf-8") as produced:
                while True:
                    chunk = produced.read(1 << 20)
                    if not chunk:
                        break
                    sys.stdout.write(chunk)
            tmp.unlink(missing_ok=True)
        return stats
    except _Abort:
        tmp.unlink(missing_ok=True)
        return stats
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        sink.io_failure = True
        sink.error("E12", f"trace 读写失败：{exc}", Location(file=str(src)))
        return stats


class _Abort(Exception):
    pass


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def summary(
    run: Path,
    graph_path: Path,
    flavor: str = "auto",
    *,
    sink: DiagnosticSink | None = None,
) -> dict[str, Any]:
    """按 §4.6 聚合；静态图缺失只报 I08，不阻断。"""
    sink = sink or DiagnosticSink()
    run = Path(run)
    graph_path = Path(graph_path)
    graph: dict[str, Any] | None = None
    if graph_path.exists():
        try:
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            sink.io_failure = True
            sink.error("E12", f"读取静态图失败：{exc}", Location(file=str(graph_path)))
            return {}
    else:
        sink.warning("I08", f"未找到静态图 {graph_path}，utilization 留空", Location(file=str(graph_path)))

    edge_map: dict[str, dict[str, Any]] = {}
    node_ids: list[str] = []
    if graph:
        node_ids = [node["id"] for node in graph.get("nodes", [])]
        edge_map = {edge["id"]: edge for edge in graph.get("edges", [])}

    cycles = 0
    toggles: dict[str, int] = {}
    node_active: dict[str, set[int]] = {node_id: set() for node_id in node_ids}
    parse_failed = False
    try:
        for row in _iter_jsonl(run):
            cycle = int(row.get("cycle", 0))
            cycles = max(cycles, cycle + 1)
            for arc in row.get("arc", []):
                edge_id = str(arc.get("edge", ""))
                toggle = int(arc.get("toggle", 0))
                toggles[edge_id] = toggles.get(edge_id, 0) + toggle
                edge = edge_map.get(edge_id)
                if edge:
                    for endpoint in (edge.get("source"), edge.get("target")):
                        if endpoint in node_active:
                            node_active[endpoint].add(cycle)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        sink.io_failure = True
        sink.error("E12", f"读取 trace JSONL 失败：{exc}", Location(file=str(run)))
        parse_failed = True
    if parse_failed:
        return {}

    summary_flavor = flavor if flavor != "auto" else "core"
    nodes_out: list[dict[str, Any]] = []
    for node_id in node_ids:
        active = len(node_active.get(node_id, ()))
        nodes_out.append(
            {
                "id": node_id,
                "active_cycles": active,
                "util": round(active / cycles, 4) if cycles else 0.0,
            }
        )

    edges_out: list[dict[str, Any]] = []
    warnings: set[str] = set()
    for edge_id, edge in edge_map.items():
        width = edge.get("width_bits")
        toggle_count = toggles.get(edge_id, 0)
        if isinstance(width, int) and width > 0:
            bytes_moved = toggle_count * width / 8
            bits_per_cycle = bytes_moved * 8 / cycles if cycles else 0.0
            bandwidth = edge.get("bandwidth") or {}
            freq = bandwidth.get("freq_hz") if bandwidth.get("source") == "derived" else None
            gbps = bytes_moved * freq / cycles / 1e9 if freq and cycles else None
            utilization = bits_per_cycle / width if width else None
            if utilization is not None and utilization > 1.0:
                warnings.add("W05")
        else:
            bits_per_cycle = 0.0
            gbps = None
            utilization = None
        edges_out.append(
            {
                "id": edge_id,
                "bytes": bytes_moved if isinstance(width, int) and width > 0 else 0,
                "bits_per_cycle": round(bits_per_cycle, 3),
                "gbps": round(gbps, 4) if gbps is not None else None,
                "toggles": toggle_count,
                "toggle_rate": round(toggle_count / (width * cycles), 6)
                if isinstance(width, int) and width > 0 and cycles
                else None,
                "utilization": round(utilization, 4) if utilization is not None else None,
            }
        )

    if "W05" in warnings:
        sink.warning(
            "W05",
            "实测利用率 >1.0：声明位宽不足或统计口径有误",
            Location(file=str(run)),
            hint="核对 Ext arc 的 toggle 计数与 node_graph 的 width_bits",
        )

    return {
        "schema_version": "1.0.0",
        "trace": str(run).replace("\\", "/"),
        "flavor": summary_flavor,
        "cycles": cycles,
        "timescale_ns": 1.0,
        "nodes": nodes_out,
        "edges": edges_out,
        "warnings": sorted(warnings),
    }


def stats(path: Path, *, sink: DiagnosticSink | None = None) -> dict[str, Any]:
    """对 JSONL 或 TSV 做概览统计（不落盘）。"""
    sink = sink or DiagnosticSink()
    path = Path(path)
    if path.suffix == ".jsonl":
        rows = 0
        cycles = 0
        try:
            for row in _iter_jsonl(path):
                rows += 1
                cycles = max(cycles, int(row.get("cycle", 0)) + 1)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            sink.io_failure = True
            sink.error("E12", f"读取 JSONL 失败：{exc}", Location(file=str(path)))
            return {}
        return {"file": str(path).replace("\\", "/"), "rows": rows, "cycles": cycles}

    import tempfile

    fd, tmp_name = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    try:
        result = normalize(path, Path(tmp_name), "auto", sink=sink)
    finally:
        Path(tmp_name).unlink(missing_ok=True)
    return {
        "file": str(path).replace("\\", "/"),
        "rows": result.rows,
        "cycles": result.cycles,
        "unknown_ext": sorted(result.unknown_keys or ()),
    }
