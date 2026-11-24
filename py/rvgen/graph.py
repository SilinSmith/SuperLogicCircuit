"""静态 node_graph 构建：位宽解析、连线、规则码与确定性输出。"""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import __version__
from .atomic import atomic_write
from .diag import Diagnostic, DiagnosticSink, Location
from .digest import source_digest
from .model import (
    Clock,
    DesignModel,
    ModuleDecl,
    Port,
    PortKind,
    WidthError,
    YAML_FILE,
    param_values,
    resolve_width,
)

NODE_GRAPH_VERSION = "1.0.0"
NODE_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_REF_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_$]*)\.([A-Za-z_][A-Za-z0-9_$]*)$")
_DATA_EDGE_KINDS = ("data", "handshake", "bundle")


@dataclass(frozen=True)
class NodeGraph:
    document: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.document, ensure_ascii=False))

    @property
    def nodes(self) -> list[dict[str, Any]]:
        return list(self.document.get("nodes", ()))

    @property
    def edges(self) -> list[dict[str, Any]]:
        return list(self.document.get("edges", ()))


class _Build:
    def __init__(self, model: DesignModel, sink: DiagnosticSink) -> None:
        self.model = model
        self.sink = sink
        self.nodes: list[dict[str, Any]] = []
        self.edges: dict[str, dict[str, Any]] = {}
        self.widths: dict[tuple[str, str], tuple[int | None, str]] = {}
        self.width_exprs: dict[tuple[str, str], Any] = {}
        self.clock_edges_done: set[tuple[str, str]] = set()

    # ---------- 诊断 ----------

    def _where(self, line: int | None, json_path: str | None = None) -> Location:
        return Location(file=self.model.source_name, line=line, json_path=json_path)

    def error(self, code: str, message: str, line: int | None, json_path: str | None = None, hint: str | None = None) -> None:
        self.sink.add(Diagnostic(code=code, severity="E", message=message, where=self._where(line, json_path), hint=hint))

    def warning(self, code: str, message: str, line: int | None, json_path: str | None = None, hint: str | None = None) -> None:
        self.sink.add(Diagnostic(code=code, severity="W", message=message, where=self._where(line, json_path), hint=hint))

    # ---------- 入口 ----------

    def run(self) -> NodeGraph:
        self._check_naming()
        self._resolve_widths()
        self._build_module_nodes()
        self._build_clock_nodes()
        self._build_cdc_nodes()
        self._build_clock_edges()
        self._build_cdc_edges()
        self._build_connect_edges()
        self._check_wiring()
        self._check_topology()
        document = {
            "schema_version": NODE_GRAPH_VERSION,
            "generated_by": f"rvgen {__version__}",
            "source_digest": source_digest(self.model.source_text),
            "nodes": self.nodes,
            "edges": list(self.edges.values()),
        }
        return NodeGraph(normalize(document))

    # ---------- 节点 ----------

    def _check_naming(self) -> None:
        for module in self.model.modules:
            if not NODE_ID_RE.fullmatch(module.name):
                self.error(
                    "E09",
                    f"module 名 {module.name!r} 不能生成 node id（要求 {NODE_ID_RE.pattern}）",
                    module.line,
                    f"modules.{module.name}.name",
                    hint="命名口径已收紧：rvgen 标识符必须小写；node_graph 的 mod:<name> 只接受小写",
                )
            for port in module.ports:
                if not NODE_ID_RE.fullmatch(port.name):
                    self.error(
                        "E09",
                        f"module {module.name} 的端口名 {port.name!r} 不能生成 node_port（要求 {NODE_ID_RE.pattern}）",
                        module.line,
                        f"modules.{module.name}.ports.{port.name}",
                    )
        for clock in self.model.clocks:
            if not NODE_ID_RE.fullmatch(clock.name):
                self.error("E09", f"clock 名 {clock.name!r} 不能生成 clk:<name>", clock.line, f"clocks.{clock.name}.name")
        for cdc in self.model.cdc:
            if not NODE_ID_RE.fullmatch(cdc.id):
                self.error("E09", f"cdc id {cdc.id!r} 不能生成 cdc:<id>", cdc.line, f"cdc.{cdc.id}.id")

    def _resolve_widths(self) -> None:
        for module in self.model.modules:
            params = param_values(module)
            for port in module.ports:
                key = (module.name, port.name)
                self.width_exprs[key] = port.width
                try:
                    bits, _source = resolve_width(port, params)
                except WidthError as exc:
                    self.widths[key] = (None, str(exc))
                    self.error(
                        "E01",
                        f"module {module.name} 端口 {port.name} 位宽无法解析：{exc}",
                        module.line,
                        f"modules.{module.name}.ports.{port.name}",
                        hint=exc.hint,
                    )
                else:
                    self.widths[key] = (bits, "")

    def _domain_of(self, module: ModuleDecl) -> str | None:
        clock = self.model.clock(module.clock)
        return clock.domain_id if clock is not None else None

    def _build_module_nodes(self) -> None:
        for module in self.model.modules:
            ports: list[dict[str, Any]] = []
            for port in module.ports:
                bits, reason = self.widths[(module.name, port.name)]
                item: dict[str, Any] = {
                    "name": port.name,
                    "dir": port.dir.value,
                    "width_expr": self.width_exprs[(module.name, port.name)],
                    "width_bits": bits,
                    "kind": port.kind.value,
                    "domain": port.domain,
                    "unresolved": "E01" if bits is None else None,
                }
                if bits is None and reason:
                    item["x-unresolved-reason"] = reason
                ports.append(item)
            node: dict[str, Any] = {
                "id": f"mod:{module.name}",
                "type": "module_node",
                "label": module.name,
                "module": module.name,
                "clock": module.clock,
                "domain": self._domain_of(module),
                "ports": ports,
            }
            if module.line is not None:
                node["loc"] = {"file": YAML_FILE, "line": module.line, "end_line": module.end_line}
            else:
                node["loc"] = None
            if module.status is not None:
                node["status"] = module.status
            if module.todo is not None:
                node["todo"] = module.todo
            self.nodes.append(node)

    def _clock_node(self, clock: Clock) -> dict[str, Any]:
        node: dict[str, Any] = {
            "id": f"clk:{clock.name}",
            "type": "clock_node",
            "label": clock.name,
            "clock": clock.name,
            "domain": clock.domain_id,
        }
        if clock.line is not None:
            node["loc"] = {"file": YAML_FILE, "line": clock.line, "end_line": clock.end_line or clock.line}
        return node

    def _build_clock_nodes(self) -> None:
        self.nodes.extend(self._clock_node(clock) for clock in self.model.clocks)

    def _build_cdc_nodes(self) -> None:
        for cdc in self.model.cdc:
            node: dict[str, Any] = {
                "id": f"cdc:{cdc.id}",
                "type": "cdc_node",
                "label": cdc.id,
                "domain": cdc.from_domain,
            }
            if cdc.line is not None:
                node["loc"] = {"file": YAML_FILE, "line": cdc.line}
            self.nodes.append(node)

    # ---------- 边 ----------

    def _add_edge(self, edge: dict[str, Any]) -> None:
        self.edges.setdefault(edge["id"], edge)

    def _build_clock_edges(self) -> None:
        for module in self.model.modules:
            edge_id = f"clk:{module.clock}->mod:{module.name}"
            if (module.clock, module.name) in self.clock_edges_done:
                continue
            self.clock_edges_done.add((module.clock, module.name))
            self._add_edge(
                {
                    "id": edge_id,
                    "source": f"clk:{module.clock}",
                    "target": f"mod:{module.name}",
                    "source_port": None,
                    "target_port": None,
                    "kind": "clock",
                    "width_bits": None,
                    "bandwidth": None,
                }
            )

    def _build_cdc_edges(self) -> None:
        for cdc in self.model.cdc:
            from_clock = self.model.domain_clock(cdc.from_domain)
            to_clock = self.model.domain_clock(cdc.to_domain)
            if from_clock is None or to_clock is None:
                continue
            self._add_edge(
                {
                    "id": f"clk:{from_clock.name}->cdc:{cdc.id}",
                    "source": f"clk:{from_clock.name}",
                    "target": f"cdc:{cdc.id}",
                    "source_port": None,
                    "target_port": None,
                    "kind": "cdc",
                    "width_bits": cdc.width,
                    "bandwidth": None,
                }
            )
            self._add_edge(
                {
                    "id": f"cdc:{cdc.id}->clk:{to_clock.name}",
                    "source": f"cdc:{cdc.id}",
                    "target": f"clk:{to_clock.name}",
                    "source_port": None,
                    "target_port": None,
                    "kind": "cdc",
                    "width_bits": cdc.width,
                    "bandwidth": None,
                }
            )

    def _parse_ref(self, value: str | None) -> tuple[ModuleDecl, Port] | None:
        if value is None:
            return None
        match = _REF_RE.fullmatch(value.strip())
        if match is None:
            return None
        module = self.model.module(match.group(1))
        if module is None:
            return None
        port = module.port(match.group(2))
        if port is None:
            return None
        return module, port

    def _effective_domain(self, module: ModuleDecl, port: Port) -> str | None:
        return port.domain if port.domain is not None else self._domain_of(module)

    def _cdc_pairs(self) -> set[tuple[str, str]]:
        pairs: set[tuple[str, str]] = set()
        for cdc in self.model.cdc:
            pairs.add((cdc.from_domain, cdc.to_domain))
            pairs.add((cdc.to_domain, cdc.from_domain))
        return pairs

    def _build_connect_edges(self) -> None:
        pairs = self._cdc_pairs()
        for module in self.model.modules:
            for port in module.ports:
                if port.connect is None:
                    continue
                if _REF_RE.fullmatch(port.connect.strip()) is None:
                    continue  # 常量连接，由 P2 top 生成负责落字面量
                parsed = self._parse_ref(port.connect)
                if parsed is None:
                    self.error(
                        "E05",
                        f"module {module.name} 端口 {port.name} 的 connect={port.connect!r} 找不到目标 module/port",
                        module.line,
                        f"modules.{module.name}.ports.{port.name}.connect",
                    )
                    continue
                other_module, other_port = parsed
                if module is other_module and other_port is port:
                    self.error(
                        "E03",
                        f"module {module.name} 端口 {port.name} connect 到自身",
                        module.line,
                        f"modules.{module.name}.ports.{port.name}.connect",
                    )
                    continue
                driver_module, driver_port, load_module, load_port = self._orient(module, port, other_module, other_port)
                if driver_module is None or driver_port is None or load_module is None or load_port is None:
                    self.error(
                        "E05",
                        f"module {module.name} 端口 {port.name} 与 {other_module.name}.{other_port.name} 方向不构成驱动关系",
                        module.line,
                        f"modules.{module.name}.ports.{port.name}.connect",
                    )
                    continue
                self._check_domains(driver_module, driver_port, load_module, load_port, pairs)
                driver_bits, _ = self.widths[(driver_module.name, driver_port.name)]
                load_bits, _ = self.widths[(load_module.name, load_port.name)]
                if driver_bits is not None and load_bits is not None and driver_bits != load_bits:
                    self.warning(
                        "W03",
                        f"{driver_module.name}.{driver_port.name} 宽 {driver_bits} 与 {load_module.name}.{load_port.name} 宽 {load_bits} 不一致",
                        load_module.line,
                        f"modules.{load_module.name}.ports.{load_port.name}",
                    )
                width_bits = driver_bits if driver_bits is not None else load_bits
                kind = "handshake" if {driver_port.kind, load_port.kind} & {PortKind.valid, PortKind.ready, PortKind.handshake} else "data"
                clock = self.model.clock(driver_module.clock)
                edge: dict[str, Any] = {
                    "id": f"mod:{driver_module.name}.{driver_port.name}->mod:{load_module.name}.{load_port.name}",
                    "source": f"mod:{driver_module.name}",
                    "target": f"mod:{load_module.name}",
                    "source_port": driver_port.name,
                    "target_port": load_port.name,
                    "kind": kind,
                    "width_bits": width_bits,
                    "bandwidth": derive_bandwidth(
                        width_bits,
                        float(clock.freq_hz) if clock is not None else None,
                        clock.name if clock is not None else None,
                    ),
                }
                self._add_edge(edge)

    @staticmethod
    def _orient(
        module: ModuleDecl,
        port: Port,
        other_module: ModuleDecl,
        other_port: Port,
    ) -> tuple[ModuleDecl | None, Port | None, ModuleDecl | None, Port | None]:
        if port.dir.value == "input" and other_port.dir.value in ("output", "inout"):
            return other_module, other_port, module, port
        if port.dir.value in ("output", "inout") and other_port.dir.value == "input":
            return module, port, other_module, other_port
        if port.dir.value == "inout" and other_port.dir.value in ("output", "inout"):
            return other_module, other_port, module, port
        return None, None, None, None

    def _check_domains(
        self,
        driver_module: ModuleDecl,
        driver_port: Port,
        load_module: ModuleDecl,
        load_port: Port,
        pairs: set[tuple[str, str]],
    ) -> None:
        source_domain = self._effective_domain(driver_module, driver_port)
        target_domain = self._effective_domain(load_module, load_port)
        if source_domain is None or target_domain is None or source_domain == target_domain:
            return
        if (source_domain, target_domain) in pairs:
            return
        self.error(
            "E08",
            f"{driver_module.name}.{driver_port.name}（{source_domain}）跨域连到 {load_module.name}.{load_port.name}（{target_domain}）但 cdc[] 未声明该桥",
            load_module.line,
            f"modules.{load_module.name}.ports.{load_port.name}",
            hint="在 cdc[] 里声明 from/to，或把端口归到同一 domain",
        )

    # ---------- top 显式连线 ----------

    def _check_wiring(self) -> None:
        top = self.model.top
        seen_names: set[str] = set()
        for port in top.ports:
            if port.name in seen_names:
                self.error("E13", f"top.ports 名重复：{port.name}", port.line, f"top.ports.{port.name}.name")
            seen_names.add(port.name)

        drivers: dict[str, list[str]] = {}
        used_targets: set[str] = set()
        for port in top.ports:
            if port.dir == "output":
                if port.from_ref is None:
                    continue
                drivers.setdefault(port.from_ref, []).append(port.name)
                self._check_ref(port.from_ref, "output", port, "from")
            else:
                for ref in port.to_refs:
                    used_targets.add(ref)
                    self._check_ref(ref, "input", port, "to")
        for ref, names in drivers.items():
            if len(names) > 1:
                self.error(
                    "E13",
                    f"top.ports 中 {ref!r} 被多个输出端口驱动：{', '.join(sorted(names))}",
                    top.ports[0].line if top.ports else None,
                    "top.ports",
                    hint="一个模块端口只能对应一个顶层输出",
                )
        self._check_required_inputs(used_targets)
        self._check_clock_reset_inputs()

    def _check_ref(self, ref: str, expected: str, top_port: TopPort, field_name: str) -> None:
        parsed = self._parse_ref(ref)
        if parsed is None:
            hint = None
            if _REF_RE.fullmatch(ref.strip()) is not None:
                module_name = ref.split(".", 1)[0]
                module = self.model.module(module_name)
                if module is not None:
                    candidates = get_close_matches(ref.split(".", 1)[1], [port.name for port in module.ports], n=1)
                    hint = f"did you mean {module_name}.{candidates[0]}?" if candidates else None
            self.error(
                "E02",
                f"top.ports.{top_port.name}.{field_name}={ref!r} 找不到对应模块端口",
                top_port.line,
                f"top.ports.{top_port.name}.{field_name}",
                hint=hint,
            )
            return
        module, port = parsed
        if expected == "output" and port.dir.value not in ("output", "inout"):
            self.error(
                "E02",
                f"top.ports.{top_port.name}.from={ref!r} 指向 {port.dir.value} 端口，不能作驱动源",
                top_port.line,
                f"top.ports.{top_port.name}.from",
            )
        if expected == "input" and port.dir.value not in ("input", "inout"):
            self.error(
                "E02",
                f"top.ports.{top_port.name}.to={ref!r} 指向 {port.dir.value} 端口，不能作负载",
                top_port.line,
                f"top.ports.{top_port.name}.to",
            )

    def _check_required_inputs(self, used_targets: set[str]) -> None:
        # 模块间 connect 的负载端同样是"已驱动"，不能误报 E14。
        connect_targets = {
            port.connect.strip()
            for module in self.model.modules
            for port in module.ports
            if port.connect is not None
        }
        missing: list[str] = []
        for module in self.model.modules:
            for port in module.ports:
                if port.dir.value not in ("input", "inout"):
                    continue
                if port.kind in (PortKind.clock, PortKind.reset):
                    continue
                if port.default is not None or port.connect is not None:
                    continue
                ref = f"{module.name}.{port.name}"
                if ref in used_targets or ref in connect_targets:
                    continue
                missing.append(ref)
        if missing:
            self.error(
                "E14",
                f"以下输入端口既未被 top.ports 驱动，也没有 default/connect：{', '.join(sorted(missing))}",
                None,
                "top.ports",
                hint="为每个模块输入补 top.ports[].to、port.default 或 port.connect",
            )

    def _check_clock_reset_inputs(self) -> None:
        reset_name = self.model.project.reset.name
        for module in self.model.modules:
            for port in module.ports:
                if port.dir.value not in ("input", "inout"):
                    continue
                if port.connect is not None or port.default is not None:
                    continue
                if port.kind is PortKind.clock and port.name != module.clock:
                    self.error(
                        "E07",
                        f"module {module.name} 的时钟输入 {port.name} 浮空（module.clock={module.clock}）",
                        module.line,
                        f"modules.{module.name}.ports.{port.name}",
                    )
                elif port.kind is PortKind.reset and port.name != reset_name:
                    self.error(
                        "E07",
                        f"module {module.name} 的复位输入 {port.name} 浮空（project.reset.name={reset_name}）",
                        module.line,
                        f"modules.{module.name}.ports.{port.name}",
                    )

    # ---------- 组合环 ----------

    def _check_topology(self) -> None:
        edges = list(self.edges.values())
        module_count = len([node for node in self.nodes if node["type"] == "module_node"])
        order = _kahn(self.nodes, edges)
        if len(order) == module_count:
            return
        cycle = _find_cycle(self.nodes, edges) or []
        self.error(
            "E03",
            f"组合环：{' -> '.join(cycle)}",
            None,
            "edges",
            hint="在环上插入寄存器，或让 plugin 声明打断点",
        )


def derive_bandwidth(
    width_bits: int | None,
    freq_hz: float | None,
    clock_name: str | None,
) -> dict[str, Any] | None:
    if width_bits is None or freq_hz is None or clock_name is None:
        return None
    return {"source": "derived", "width_bits": width_bits, "clock": clock_name, "freq_hz": freq_hz}


def bandwidth(width_bits: int | None, freq_hz: float | None, explicit_bpc: float | None = None, *, clock_name: str | None = None) -> dict[str, Any] | None:
    """附录 C：explicit 优先，其次 derived。"""
    if explicit_bpc is not None:
        return {"source": "explicit", "value": explicit_bpc, "reason": "manual override"}
    return derive_bandwidth(width_bits, freq_hz, clock_name)


def _module_order(nodes: Sequence[Mapping[str, Any]]) -> list[str]:
    return [str(node["id"]) for node in nodes if node.get("type") == "module_node"]


def _adjacency(
    nodes: Sequence[Mapping[str, Any]],
    edges: Iterable[Mapping[str, Any]],
) -> dict[str, list[str]]:
    order = _module_order(nodes)
    index = {node_id: position for position, node_id in enumerate(order)}
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in order}
    for edge in edges:
        if edge.get("kind") not in _DATA_EDGE_KINDS:
            continue
        source = edge.get("source")
        target = edge.get("target")
        if source in adjacency and target in adjacency:
            adjacency[source].append(target)
    for successors in adjacency.values():
        successors.sort(key=lambda item: index.get(item, 1 << 30))
    return adjacency


def _kahn(nodes: Sequence[Mapping[str, Any]], edges: Iterable[Mapping[str, Any]]) -> list[str]:
    order = _module_order(nodes)
    adjacency = _adjacency(nodes, edges)
    indegree = {node_id: 0 for node_id in order}
    for successors in adjacency.values():
        for target in successors:
            indegree[target] += 1
    queue = deque(node_id for node_id in order if indegree[node_id] == 0)
    result: list[str] = []
    while queue:
        node_id = queue.popleft()
        result.append(node_id)
        for target in adjacency[node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    return result


def _find_cycle(nodes: Sequence[Mapping[str, Any]], edges: Iterable[Mapping[str, Any]]) -> list[str] | None:
    adjacency = _adjacency(nodes, edges)
    color: dict[str, int] = {node_id: 0 for node_id in adjacency}
    stack: list[str] = []

    def visit(node_id: str) -> list[str] | None:
        color[node_id] = 1
        stack.append(node_id)
        for target in adjacency[node_id]:
            if color.get(target) == 1:
                position = stack.index(target)
                return [*stack[position:], target]
            if color.get(target, 0) == 0:
                found = visit(target)
                if found is not None:
                    return found
        stack.pop()
        color[node_id] = 2
        return None

    for node_id in adjacency:
        if color[node_id] == 0:
            found = visit(node_id)
            if found is not None:
                return found
    return None


def topsort(graph: NodeGraph, sink: DiagnosticSink | None = None) -> list[str]:
    """append-only 的确定性拓扑序；有环返回空列表并记 E03。"""
    nodes = graph.nodes
    edges = graph.edges
    order = _kahn(nodes, edges)
    module_count = len(_module_order(nodes))
    if len(order) == module_count:
        return order
    cycle = _find_cycle(nodes, edges) or []
    if sink is not None:
        sink.error("E03", f"组合环：{' -> '.join(cycle)}", Location(json_path="edges"))
    return []


def normalize(document: Mapping[str, Any]) -> dict[str, Any]:
    """图对象规范化：节点/边按 id 排序，保证逐字节可复现。"""

    return {
        "schema_version": document["schema_version"],
        "generated_by": document["generated_by"],
        "source_digest": document["source_digest"],
        "nodes": sorted((dict(node) for node in document.get("nodes", ())), key=lambda node: node["id"]),
        "edges": sorted((dict(edge) for edge in document.get("edges", ())), key=lambda edge: edge["id"]),
    }


def build(model: DesignModel, sink: DiagnosticSink | None = None) -> NodeGraph:
    builder = _Build(model, sink if sink is not None else DiagnosticSink())
    return builder.run()


def write(graph: NodeGraph, path: str | Path, *, sink: DiagnosticSink | None = None) -> Path:
    text = json.dumps(graph.document, ensure_ascii=False, indent=2) + "\n"
    return atomic_write(Path(path), text, sink=sink)
