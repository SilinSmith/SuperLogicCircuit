"""P2 emitter：Jinja2 渲染 + USER 块六步合并 + 顶层例化 + 原子写。

约束（§6.1）：只被 cli.sync 调用；禁止改 YAML、禁止改图。
marker 破损 → E06；原子写失败 → E12；frozen 覆写 → E10（由 sync --check 判定）。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from jinja2 import Environment, FileSystemLoader

from . import __version__
from .atomic import AtomicWriteError, atomic_write
from .diag import DiagnosticSink, Location
from .digest import fingerprint, fingerprint_model
from .graph import NodeGraph
from .model import DesignModel, ModuleDecl, Port, PortKind, WidthError, param_values, resolve_width

BEGIN_RE = re.compile(r"^\s*//\s*rvgen:user-begin\s+(\S+)\s*$")
END_RE = re.compile(r"^\s*//\s*rvgen:user-end\s+(\S+)\s*$")
FINGERPRINT_RE = re.compile(r"^//\s*rvgen:fingerprint\s+(\S+)\s*$", re.MULTILINE)
REF_RE = re.compile(r"^([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)$")
CDC_MODULES = {
    "2ff": "two_ff",
    "async_fifo": "async_fifo",
    "handshake": "handshake",
    "pulse_sync": "pulse_sync",
    "gray_bus": "gray_bus",
}
_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

Token = tuple[str, Any]


@dataclass
class EmittedFile:
    path: Path
    content: str
    existing: str
    owner: str
    frozen: bool
    orphans: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def stale(self) -> bool:
        return self.content != self.existing

    @property
    def existed(self) -> bool:
        return self.existing != ""


def environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        autoescape=False,
        newline_sequence="\n",
    )


# ---------- USER 块 ----------


def split_markers(text: str, sink: DiagnosticSink, where: Location | None = None) -> list[Token]:
    tokens: list[Token] = []
    buffer: list[str] = []
    current: str | None = None
    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        begin = BEGIN_RE.match(bare)
        end = END_RE.match(bare)
        if begin is not None:
            if current is not None:
                sink.error("E06", f"USER 块 {current!r} 内又出现 user-begin {begin.group(1)!r}", where)
            tokens.append(("text", "".join(buffer)))
            buffer = []
            current = begin.group(1)
        elif end is not None:
            if current is None:
                sink.error("E06", f"出现孤立的 user-end {end.group(1)!r}", where)
                continue
            if end.group(1) != current:
                sink.error("E06", f"user-begin {current!r} 与 user-end {end.group(1)!r} 不匹配", where)
            tokens.append(("block", (current, "".join(buffer))))
            buffer = []
            current = None
        else:
            buffer.append(line)
    if current is not None:
        sink.error("E06", f"USER 块 {current!r} 缺少 user-end", where)
    tokens.append(("text", "".join(buffer)))
    return tokens


def _existing_blocks(tokens: Iterable[Token], sink: DiagnosticSink, where: Location | None) -> dict[str, str]:
    blocks: dict[str, str] = {}
    for kind, payload in tokens:
        if kind != "block":
            continue
        bid, body = payload
        if bid in blocks:
            sink.error("E06", f"USER 块 {bid!r} 在旧文件中重复，保留第一份", where)
            continue
        blocks[bid] = body
    return blocks


def merge_blocks(
    existing: str,
    generated: str,
    owner: str,
    sink: DiagnosticSink,
    where: Location | None = None,
) -> tuple[str, tuple[tuple[str, str], ...]]:
    """六步合并：只保留旧 USER 块内容，其余整体采用新生成文本。"""

    old_blocks = _existing_blocks(split_markers(existing, sink, where), sink, where)
    new_tokens = split_markers(generated, sink, where)
    kept: set[str] = set()
    pieces: list[str] = []
    for kind, payload in new_tokens:
        if kind == "text":
            pieces.append(payload)
            continue
        bid, default_body = payload
        kept.add(bid)
        body = old_blocks.get(bid, default_body)
        if not body.endswith("\n"):
            body += "\n"
        pieces.append(f"// rvgen:user-begin {bid}\n{body}// rvgen:user-end {bid}\n")
    orphans = tuple((bid, body) for bid, body in old_blocks.items() if bid not in kept)
    if orphans:
        names = ", ".join(f"{owner}.{bid}" for bid, _ in orphans)
        sink.info("I04", f"USER 块已删除并备份到 orphaned/：{names}")
    return "".join(pieces), orphans


def old_fingerprint(text: str) -> str | None:
    match = FINGERPRINT_RE.search(text)
    return match.group(1) if match else None


# ---------- 渲染 ----------


def _range(bits: int | None) -> str:
    return "" if bits is None or bits <= 1 else f"[{bits - 1}:0] "


def _width_of(module: ModuleDecl, port: Port) -> int | None:
    try:
        bits, _ = resolve_width(port, param_values(module))
    except WidthError:
        return None
    return bits


def _sanitize(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name)
    return cleaned


def _wire_name(module: str, port: str, sink: DiagnosticSink) -> str:
    raw = f"w_{_sanitize(module)}_{_sanitize(port)}"
    if len(raw) <= 64:
        return raw
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    shortened = f"w_{_sanitize(module)[:24]}_{_sanitize(port)[:24]}_{digest}"
    sink.warning("W08", f"wire 名 {raw!r} 超过 64 字符，已哈希为 {shortened!r}")
    return shortened


def render_module(
    module: ModuleDecl,
    *,
    fp: str | None = None,
    contract_notice: str | None = None,
    sink: DiagnosticSink | None = None,
) -> str:
    ports = []
    for port in module.ports:
        ports.append(
            {
                "dir": port.dir.value,
                "range": _range(_width_of(module, port)),
                "name": port.name,
            }
        )
    params = [
        {"name": param.name, "expr": param.default if param.default is not None else param.name}
        for param in module.params
    ]
    return environment().get_template("module.v.j2").render(
        version=__version__,
        module_name=module.name,
        fingerprint=fp or fingerprint(module),
        contract_notice=contract_notice,
        params=params,
        ports=ports,
    )


def _top_port_width(model: DesignModel, ref: str | None, to_refs: Sequence[str]) -> int | None:
    candidates = [ref] if ref else list(to_refs)
    for candidate in candidates:
        match = REF_RE.fullmatch(candidate or "")
        if match is None:
            continue
        module = model.module(match.group(1))
        if module is None:
            continue
        port = module.port(match.group(2))
        if port is not None:
            return _width_of(module, port)
    return None


def _top_context(model: DesignModel, graph: NodeGraph, sink: DiagnosticSink) -> dict[str, Any]:
    top_ports = []
    for port in model.top.ports:
        bits = 1 if port.role in ("clock", "reset") else _top_port_width(model, port.from_ref, port.to_refs)
        top_ports.append({"dir": port.dir, "range": _range(bits), "name": port.name})

    out_alias = {port.from_ref: port.name for port in model.top.ports if port.from_ref}
    in_alias: dict[str, str] = {}
    for port in model.top.ports:
        for ref in port.to_refs:
            in_alias[ref] = port.name

    tieoffs = {tieoff.port: tieoff.value for tieoff in model.top.tieoffs}

    wire_names: dict[tuple[str, str], str] = {}
    for module in model.modules:
        for port in module.ports:
            if port.dir.value == "output":
                ref = f"{module.name}.{port.name}"
                wire_names[(module.name, port.name)] = out_alias.get(ref) or _wire_name(module.name, port.name, sink)

    edges_in: dict[tuple[str, str], dict[str, Any]] = {}
    consumers: set[tuple[str, str]] = set()
    for edge in graph.edges:
        if not str(edge.get("source", "")).startswith("mod:"):
            continue
        source = str(edge["source"])[4:]
        target = str(edge["target"])[4:]
        source_port = edge.get("source_port")
        target_port = edge.get("target_port")
        if source_port and target_port:
            consumers.add((source, source_port))
            edges_in[(target, str(target_port))] = {"module": source, "port": str(source_port)}

    wires: list[dict[str, str]] = []
    declared: set[str] = set()
    for module in model.modules:
        for port in module.ports:
            if port.dir.value != "output":
                continue
            net = wire_names[(module.name, port.name)]
            if net in in_alias.values() or net in out_alias.values():
                continue
            if net in declared:
                continue
            declared.add(net)
            wires.append({"range": _range(_width_of(module, port)), "name": net})
            ref = f"{module.name}.{port.name}"
            if (module.name, port.name) not in consumers and ref not in out_alias:
                sink.warning(
                    "W04",
                    f"输出 {ref} 未连接（已声明 wire {net}）",
                    Location(file=model.source_name, line=module.line),
                    f"modules.{module.name}.ports.{port.name}",
                )

    def input_net(module: ModuleDecl, port: Port) -> str:
        ref = f"{module.name}.{port.name}"
        if ref in in_alias:
            return in_alias[ref]
        if ref in tieoffs:
            return tieoffs[ref]
        if (module.name, port.name) in edges_in:
            driver = edges_in[(module.name, port.name)]
            return wire_names.get((driver["module"], driver["port"])) or _wire_name(
                driver["module"], driver["port"], sink
            )
        if port.connect is not None:
            if REF_RE.fullmatch(port.connect.strip()):
                other = port.connect.strip().split(".")
                return wire_names.get((other[0], other[1])) or _sanitize(port.connect.strip().replace(".", "_"))
            return port.connect
        if port.default is not None:
            return port.default
        if port.kind is PortKind.clock:
            return module.clock
        if port.kind is PortKind.reset:
            return model.project.reset.name
        if port.kind in (PortKind.valid, PortKind.ready):
            return "1'b0"
        bits = _width_of(module, port)
        sink.warning(
            "W02",
            f"数据输入 {ref} 未连接，已接 0",
            Location(file=model.source_name, line=module.line),
            f"modules.{module.name}.ports.{port.name}",
        )
        return f"{{{bits}{{1'b0}}}}" if bits and bits > 1 else "1'b0"

    insts = []
    for module in model.modules:
        bindings = []
        for port in module.ports:
            net = wire_names[(module.name, port.name)] if port.dir.value == "output" else input_net(module, port)
            bindings.append({"port": port.name, "net": net})
        params = [
            {"name": param.name, "expr": param.default if param.default is not None else param.name}
            for param in module.params
        ]
        insts.append({"module": module.name, "inst": module.name, "param_bindings": params, "port_bindings": bindings})

    cdc_insts = []
    for cdc in model.cdc:
        module_name = CDC_MODULES.get(cdc.kind, cdc.kind)
        from_net = next((clock.name for clock in model.clocks if clock.domain_id == cdc.from_domain), cdc.from_domain)
        to_net = next((clock.name for clock in model.clocks if clock.domain_id == cdc.to_domain), cdc.to_domain)
        width = cdc.width or 1
        cdc_insts.append(
            {
                "id": cdc.id,
                "module": module_name,
                "from_domain": cdc.from_domain,
                "to_domain": cdc.to_domain,
                "kind": cdc.kind,
                "param_bindings": [{"name": "WIDTH", "value": width}],
                "port_bindings": [
                    {"port": "clk_src", "net": from_net},
                    {"port": "clk_dst", "net": to_net},
                    {"port": "rst_n", "net": model.project.reset.name},
                ],
            }
        )

    return {
        "project": {"top": model.project.top},
        "ports": top_ports,
        "wires": wires,
        "cdc_insts": cdc_insts,
        "insts": insts,
    }


def render_top(
    model: DesignModel,
    graph: NodeGraph,
    *,
    fp: str | None = None,
    contract_notice: str | None = None,
    sink: DiagnosticSink | None = None,
) -> str:
    sink = sink or DiagnosticSink()
    context = _top_context(model, graph, sink)
    return environment().get_template("top.v.j2").render(
        version=__version__,
        top_fingerprint=fp or fingerprint_model(model),
        contract_notice=contract_notice,
        **context,
    )


def render_cdc(kind: str, module_name: str, width: int) -> str:
    return environment().get_template("cdc_bridge.v.j2").render(
        version=__version__,
        fingerprint=f"cdc/{kind}/{width}",
        kind=kind,
        module_name=module_name,
        width=width,
    )


# ---------- 计划 / 落盘 ----------


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _notice(existing: str, new_fp: str) -> str | None:
    old = old_fingerprint(existing)
    if old is None or old == new_fp:
        return None
    return f"USER 块契约已变更（fp {old} -> {new_fp}），请核对端口表"


def plan_files(
    model: DesignModel,
    graph: NodeGraph,
    out_dir: Path,
    sink: DiagnosticSink,
    *,
    force_unfreeze: bool = False,
) -> list[EmittedFile]:
    out_dir = Path(out_dir)
    where = Location(file=model.source_name)
    files: list[EmittedFile] = []

    for module in model.modules:
        path = out_dir / f"{module.name}.v"
        existing = _read(path)
        fp = fingerprint(module)
        notice = _notice(existing, fp)
        if notice is not None:
            sink.warning("W01", notice, Location(file=model.source_name, line=module.line), f"modules.{module.name}")
        generated = render_module(module, fp=fp, contract_notice=notice, sink=sink)
        content, orphans = merge_blocks(existing, generated, module.name, sink, where)
        files.append(
            EmittedFile(
                path=path,
                content=content,
                existing=existing,
                owner=module.name,
                frozen=module.status == "frozen" and bool(existing) and not force_unfreeze,
                orphans=orphans,
            )
        )

    top_path = out_dir / f"{model.project.top}.v"
    existing = _read(top_path)
    fp = fingerprint_model(model)
    notice = _notice(existing, fp)
    if notice is not None:
        sink.warning("W01", notice, Location(file=model.source_name), "project.top")
    generated = render_top(model, graph, fp=fp, contract_notice=notice, sink=sink)
    content, orphans = merge_blocks(existing, generated, model.project.top, sink, where)
    files.append(
        EmittedFile(
            path=top_path,
            content=content,
            existing=existing,
            owner=model.project.top,
            frozen=False,
            orphans=orphans,
        )
    )

    kinds = {(cdc.kind, cdc.width or 1) for cdc in model.cdc}
    for kind, width in sorted(kinds):
        module_name = CDC_MODULES.get(kind, kind)
        path = out_dir / "gen" / "cdc" / f"{module_name}.v"
        existing = _read(path)
        generated = render_cdc(kind, module_name, width)
        files.append(
            EmittedFile(
                path=path,
                content=generated,
                existing=existing,
                owner=module_name,
                frozen=False,
                orphans=(),
            )
        )

    return files


def _write_orphans(root: Path, file: EmittedFile, sink: DiagnosticSink) -> None:
    if not file.orphans:
        return
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    target = root / ".rvgen" / "orphaned" / stamp
    try:
        target.mkdir(parents=True, exist_ok=True)
        for bid, body in file.orphans:
            (target / f"{file.owner}.{bid}.v.bak").write_text(body, encoding="utf-8")
    except OSError as exc:
        sink.error("E12", f"备份 orphaned USER 块失败：{exc}", hint="检查 .rvgen 目录权限")


def emit(
    model: DesignModel,
    graph: NodeGraph,
    out_dir: Path,
    sink: DiagnosticSink,
    *,
    force_unfreeze: bool = False,
) -> list[Path]:
    out_dir = Path(out_dir)
    written: list[Path] = []
    for file in plan_files(model, graph, out_dir, sink, force_unfreeze=force_unfreeze):
        if file.frozen:
            sink.info("I03", f"frozen 模块已跳过：{file.path}")
            continue
        try:
            atomic_write(file.path, file.content, sink=sink)
        except AtomicWriteError as exc:
            sink.error("E12", str(exc), hint="检查文件权限/占用后重试")
            continue
        _write_orphans(out_dir.parent, file, sink)
        written.append(file.path)
    return written


def check_outputs(
    model: DesignModel,
    graph: NodeGraph,
    out_dir: Path,
    sink: DiagnosticSink,
    *,
    force_unfreeze: bool = False,
) -> list[Path]:
    """只读比对：frozen 落后 → E10；普通生成物落后 → E15。"""

    stale: list[Path] = []
    for file in plan_files(model, graph, out_dir, sink, force_unfreeze=force_unfreeze):
        if not file.stale:
            continue
        stale.append(file.path)
        if file.frozen and not force_unfreeze:
            sink.error(
                "E10",
                f"frozen 生成物与声明不一致，拒绝覆写：{file.path}",
                hint="改 module.status 或显式 --force-unfreeze",
            )
        else:
            sink.error(
                "E15",
                f"生成物落后于 rvgen.yaml：{file.path}",
                hint="运行 rvgen sync（或先看 --dry-run）",
            )
    return stale
