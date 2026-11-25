"""SuperLogicCircuit（slc）CLI 骨架。

P0 只实现 doctor / plugin list 与 check 的通路；其余命令注册完整但返回 E00，
明确提示"尚未实现"，避免把用户带进 P1/P2 的语义核心。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .diag import DiagnosticSink
from .plugins import discover


class CliUsageError(Exception):
    pass


class _CliParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # argparse 默认 exit(2)，与 0/1/2/3 口径冲突
        raise CliUsageError(message)


def _add_subparsers(parser: argparse.ArgumentParser, dest: str) -> argparse._SubParsersAction:
    return parser.add_subparsers(dest=dest, required=True, parser_class=_CliParser)


def build_parser() -> argparse.ArgumentParser:
    parser = _CliParser(prog="slc", description="SuperLogicCircuit：声明式 Verilog/IP 工程脚手架")
    parser.add_argument("--version", action="version", version=f"slc {__version__}")
    sub = _add_subparsers(parser, "command")

    init = sub.add_parser("init", help="建目录 + slc.yaml 样例")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--preset", choices=["minimal", "uart", "rv32i"], default="minimal")

    imp = sub.add_parser("import", help="从已有 Verilog 反生成声明骨架")
    imp.add_argument("file")
    imp.add_argument("-o", "--output", default="slc.yaml")

    sync = sub.add_parser("sync", help="生成骨架/top/CDC/.core，合并 USER 块")
    sync.add_argument("--dry-run", action="store_true")
    sync.add_argument("--check", action="store_true")
    sync.add_argument("--strict", action="store_true")
    sync.add_argument("--update-graph", action="store_true")
    sync.add_argument("--force-unfreeze", action="store_true")

    graph = sub.add_parser("graph", help="计算静态图；只有 --write 才落盘")
    graph.add_argument("--write", action="store_true")
    graph.add_argument("--check", action="store_true")
    graph.add_argument("--accept-wiring", action="store_true")
    graph.add_argument("--list-cdc", action="store_true")

    yaml_parser = sub.add_parser("yaml", help="YAML 只读工具")
    yaml_sub = _add_subparsers(yaml_parser, "yaml_command")
    yaml_expand = yaml_sub.add_parser("expand", help="展开锚点/别名并打印")
    yaml_expand.add_argument("-o", "--output", default="-")

    check = sub.add_parser("check", help="语义 diff；P0 先提供 schema lint 通路")
    check.add_argument("--format", choices=["text", "github", "json"], default="text")
    check.add_argument("--fix", action="store_true")
    check.add_argument("--strict", action="store_true")
    check.add_argument("--quiet", action="store_true")

    trace = sub.add_parser("trace", help="trace 归一/指标/统计")
    trace_sub = _add_subparsers(trace, "trace_command")
    trace_norm = trace_sub.add_parser("normalize")
    trace_norm.add_argument("src")
    trace_norm.add_argument("-o", "--output", default="-")
    trace_norm.add_argument("--flavor", choices=["core", "cpu", "bus", "auto"], default="auto")
    trace_summary = trace_sub.add_parser("summary")
    trace_summary.add_argument("run")
    trace_summary.add_argument("-o", "--output", default="trace_summary.json")
    trace_summary.add_argument("--graph", default="node_graph.json")
    trace_summary.add_argument("--flavor", choices=["core", "cpu", "bus", "auto"], default="auto")
    trace_stats = trace_sub.add_parser("stats")
    trace_stats.add_argument("file")

    gen = sub.add_parser("gen", help="生成 CDC 基础模块 / FuseSoC .core")
    gen_sub = _add_subparsers(gen, "gen_command")
    gen_cdc = gen_sub.add_parser("cdc")
    gen_cdc.add_argument("--out", default="rtl/gen/cdc")
    gen_core = gen_sub.add_parser("fuse-soc")
    gen_core.add_argument("--out", default=".")

    serve = sub.add_parser("serve", help="HTTP + SSE 看板服务")
    serve.add_argument("--project", default=None)
    serve.add_argument("--port", type=int, default=8123)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--no-open", action="store_true")

    plugin = sub.add_parser("plugin", help="plugin 管理")
    plugin_sub = _add_subparsers(plugin, "plugin_command")
    plugin_sub.add_parser("list", help="列出已发现 plugin")

    doctor = sub.add_parser("doctor", help="探测外部工具链")
    doctor.add_argument("--json", dest="json_output", action="store_true")

    migrate = sub.add_parser("migrate", help="schema 版本迁移")
    migrate.add_argument("--from", dest="from_version", default=None)
    migrate.add_argument("--dry-run", action="store_true")

    return parser


def _render(sink: DiagnosticSink, output_format: str, *, quiet: bool = False) -> None:
    stream = sys.stdout if output_format == "json" else sys.stderr
    if quiet and output_format == "text":
        filtered = DiagnosticSink()
        filtered.items = [item for item in sink.items if item.severity != "I"]
        filtered.io_failure = sink.io_failure
        filtered.render("text", stream=stream)
        return
    sink.render(output_format, stream=stream)


def _probe(name: str, command: list[str], required: bool) -> dict[str, object]:
    if name == "python":
        executable = sys.executable
    else:
        executable = shutil.which(command[0])
    if not executable:
        return {
            "name": name,
            "required": required,
            "status": "missing",
            "version": None,
            "detail": f"找不到 {command[0]}",
        }

    actual = [executable, *command[1:]]
    try:
        completed = subprocess.run(
            actual,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "name": name,
            "required": required,
            "status": "present",
            "version": None,
            "detail": str(exc),
        }

    output = (completed.stdout or "") + (completed.stderr or "")
    version = next((line.strip() for line in output.splitlines() if line.strip()), None)
    return {
        "name": name,
        "required": required,
        "status": "ok",
        "version": version,
        "detail": None,
    }


def _cmd_doctor(args: argparse.Namespace) -> int:
    tools = [
        _probe("python", ["python", "--version"], True),
        _probe("iverilog", ["iverilog", "-V"], True),
        _probe("node", ["node", "--version"], True),
        _probe("npm", ["npm", "--version"], True),
        _probe("git", ["git", "--version"], True),
        _probe("verilator", ["verilator", "--version"], False),
        _probe("yosys", ["yosys", "-V"], False),
        _probe("fusesoc", ["fusesoc", "--version"], False),
        _probe("verible", ["verible-verilog-lint", "--version"], False),
    ]
    tools.append(
        {
            "name": "slc_protocol",
            "required": False,
            "status": "manual",
            "version": None,
            "detail": "运行 scripts/register-rvopen.{ps1,sh} 注册 slc://",
        }
    )
    ok = all(tool["status"] != "missing" for tool in tools if tool["required"])

    if args.json_output:
        sys.stdout.write(json.dumps({"ok": ok, "tools": tools}, ensure_ascii=False, indent=2) + "\n")
    else:
        for tool in tools:
            mark = "required" if tool["required"] else "optional"
            version = tool["version"] or tool["detail"] or "-"
            sys.stdout.write(f"{str(tool['status']):8} {tool['name']:14} {mark:8} {version}\n")
        sys.stdout.write("doctor: OK\n" if ok else "doctor: 缺少必需工具\n")
    return 0 if ok else 3


def _cmd_plugin_list(_args: argparse.Namespace) -> int:
    sink = DiagnosticSink()
    plugins = discover(sink)
    if not plugins:
        sys.stdout.write("没有发现 plugin（entry_points group=slc.plugins）\n")
    for plugin in plugins:
        sys.stdout.write(f"plugin: {plugin.id}\n")
        sys.stdout.write(f"  kinds: {', '.join(plugin.kinds) or '-'}\n")
        sys.stdout.write(f"  node_types: {', '.join(plugin.node_types) or '-'}\n")
        sys.stdout.write(f"  views: {', '.join(str(v) for v in plugin.views) or '-'}\n")
        sys.stdout.write(f"  trace_flavors: {', '.join(plugin.trace_flavors) or '-'}\n")
    _render(sink, "text")
    return sink.exit_code(strict=False)


def _command_label(args: argparse.Namespace) -> str:
    label = str(args.command)
    for attr in ("yaml_command", "trace_command", "gen_command", "plugin_command"):
        value = getattr(args, attr, None)
        if value:
            label += f" {value}"
    return label


def _cmd_init(args: argparse.Namespace) -> int:
    from .atomic import AtomicWriteError, atomic_write
    from .emitter import emit
    from .graph import build, write
    from .init_presets import PRESETS
    from .loader import load

    sink = DiagnosticSink()
    root = Path(args.path).expanduser()
    slc_path = root / "slc.yaml"
    if slc_path.exists():
        sink.error("E00", f"{slc_path} 已存在", hint="换一个空目录，或先备份现有声明")
        _render(sink, "text")
        return sink.exit_code()
    try:
        root.mkdir(parents=True, exist_ok=True)
        atomic_write(slc_path, PRESETS[args.preset])
    except (OSError, AtomicWriteError) as exc:
        sink.io_failure = True
        sink.error("E12", f"初始化失败：{exc}", hint="检查目录权限后重试")
        _render(sink, "text")
        return sink.exit_code()

    plugins = discover(sink)
    model, diagnostics = load(slc_path, plugins, sink=sink)
    sink.extend(diagnostics)
    if model is not None and not sink.has_errors():
        graph = build(model, sink)
        if not sink.has_errors():
            emit(model, graph, root / "rtl", sink)
        if not sink.has_errors():
            try:
                write(graph, root / "node_graph.json", sink=sink)
            except AtomicWriteError as exc:
                sink.io_failure = True
                sink.error("E12", str(exc), hint="检查目录权限后重试")
    if not sink.has_errors():
        sys.stdout.write(f"initialized {root} (preset={args.preset})\n")
    _render(sink, "text")
    return sink.exit_code()


def _cmd_import(args: argparse.Namespace) -> int:
    import yaml

    from .atomic import AtomicWriteError, atomic_write
    from .importer import import_verilog

    sink = DiagnosticSink()
    source = Path(args.file)
    if not source.exists():
        sink.io_failure = True
        sink.error("E00", f"未找到 {source}", hint="传入一个 .v/.sv 文件")
        _render(sink, "text")
        return sink.exit_code()
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        sink.io_failure = True
        sink.error("E12", f"读取失败：{exc}", hint="检查文件权限")
        _render(sink, "text")
        return sink.exit_code()

    document, diagnostics = import_verilog(text, source_name=str(source))
    sink.extend(diagnostics)
    if document is not None and not sink.has_errors():
        payload = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
        if args.output == "-":
            sys.stdout.write(payload)
        else:
            try:
                atomic_write(Path(args.output), payload)
            except AtomicWriteError as exc:
                sink.io_failure = True
                sink.error("E12", str(exc), hint="检查输出路径权限")
            else:
                sys.stdout.write(f"wrote {args.output}\n")
    _render(sink, "text")
    return sink.exit_code()


def _cmd_gen(args: argparse.Namespace) -> int:
    from .atomic import AtomicWriteError, atomic_write
    from .emitter import CDC_MODULES, render_cdc

    sink = DiagnosticSink()
    if args.gen_command == "cdc":
        out = Path(args.out)
        for kind, module_name in CDC_MODULES.items():
            try:
                atomic_write(out / f"{module_name}.v", render_cdc(kind, module_name, 1))
            except AtomicWriteError as exc:
                sink.io_failure = True
                sink.error("E12", str(exc), hint="检查输出目录权限")
                break
            sys.stdout.write(f"wrote {out / (module_name + '.v')}\n")
        _render(sink, "text")
        return sink.exit_code()

    if args.gen_command == "fuse-soc":
        from .fusesoc import render_core
        from .loader import load

        slc_path = Path.cwd() / "slc.yaml"
        if not slc_path.exists():
            sink.error("E00", f"未找到 {slc_path}", hint="在项目根运行 slc gen fuse-soc")
            _render(sink, "text")
            return sink.exit_code()
        model, diagnostics = load(slc_path, discover(sink), sink=sink)
        sink.extend(diagnostics)
        if model is not None and not sink.has_errors():
            target = Path(args.out) / f"{model.project.name}.core"
            try:
                atomic_write(target, render_core(model))
            except AtomicWriteError as exc:
                sink.io_failure = True
                sink.error("E12", str(exc), hint="检查输出目录权限")
            else:
                sys.stdout.write(f"wrote {target}\n")
        _render(sink, "text")
        return sink.exit_code()

    return _cmd_unimplemented(args)


def _cmd_unimplemented(args: argparse.Namespace) -> int:
    sink = DiagnosticSink()
    sink.error(
        "E00",
        f"slc {_command_label(args)} 尚未实现：P1 只提供 loader/model/graph/digest/importer 与 graph --write",
        hint="按 slc完整方案.md 第 9 章，生成与前端分别属于 P2/P3",
    )
    _render(sink, "text")
    return sink.exit_code()


def _cmd_graph(args: argparse.Namespace) -> int:
    sink = DiagnosticSink()
    if not args.write or args.check or args.accept_wiring or args.list_cdc:
        sink.error(
            "E00",
            "graph --check/--accept-wiring/--list-cdc 尚未实现：P1 只实现 --write",
            hint="需要落盘时运行 slc graph --write",
        )
        _render(sink, "text")
        return sink.exit_code()

    from .graph import build, write
    from .loader import load

    root = Path.cwd()
    slc_path = root / "slc.yaml"
    if not slc_path.exists():
        sink.error("E00", f"未找到 {slc_path}", hint="在项目根运行 slc graph --write")
        _render(sink, "text")
        return sink.exit_code()

    plugins = discover(sink)
    model, diagnostics = load(slc_path, plugins, sink=sink)
    sink.extend(diagnostics)
    if model is None or sink.has_errors():
        _render(sink, "text")
        return sink.exit_code()

    node_graph = build(model, sink)
    if sink.has_errors():
        _render(sink, "text")
        return sink.exit_code()

    from .atomic import AtomicWriteError

    try:
        write(node_graph, root / "node_graph.json", sink=sink)
    except AtomicWriteError as exc:
        sink.error("E12", str(exc), hint="检查文件权限/占用后重试")
        _render(sink, "text")
        return sink.exit_code()
    sys.stdout.write("wrote node_graph.json\n")
    _render(sink, "text")
    return sink.exit_code()


def _cmd_check(args: argparse.Namespace) -> int:
    # P1：schema lint + loader/graph 语义校验；生成物 diff 仍属 P2。
    from .checker import run_check

    sink = DiagnosticSink()
    code = run_check(
        Path.cwd(),
        sink,
        strict=args.strict,
        output_format=args.format,
        quiet=args.quiet,
        fix=args.fix,
    )
    return code


def _cmd_sync(args: argparse.Namespace) -> int:
    from .emitter import check_outputs, emit, plan_files
    from .graph import build, write
    from .loader import load

    sink = DiagnosticSink()
    root = Path.cwd()
    slc_path = root / "slc.yaml"
    if not slc_path.exists():
        sink.error("E00", f"未找到 {slc_path}", hint="在项目根运行 slc sync")
        _render(sink, "text")
        return sink.exit_code(strict=args.strict)

    plugins = discover(sink)
    model, diagnostics = load(slc_path, plugins, sink=sink)
    sink.extend(diagnostics)
    if model is None or sink.has_errors():
        _render(sink, "text")
        return sink.exit_code(strict=args.strict)

    graph = build(model, sink)
    if sink.has_errors():
        _render(sink, "text")
        return sink.exit_code(strict=args.strict)

    out_dir = root / "rtl"
    if args.check:
        check_outputs(model, graph, out_dir, sink, force_unfreeze=args.force_unfreeze)
        _render(sink, "text")
        return sink.exit_code(strict=args.strict)

    if args.dry_run:
        for file in plan_files(model, graph, out_dir, sink, force_unfreeze=args.force_unfreeze):
            state = "stale" if file.stale else "up-to-date"
            if file.frozen and file.stale:
                state = "frozen-skip"
            sys.stdout.write(f"{state:11} {file.path}\n")
        _render(sink, "text")
        return sink.exit_code(strict=args.strict)

    written = emit(model, graph, out_dir, sink, force_unfreeze=args.force_unfreeze)
    for path in written:
        sys.stdout.write(f"wrote {path}\n")

    if args.update_graph and not sink.has_errors():
        from .atomic import AtomicWriteError

        try:
            write(graph, root / "node_graph.json", sink=sink)
        except AtomicWriteError as exc:
            sink.error("E12", str(exc), hint="检查文件权限/占用后重试")
        else:
            sys.stdout.write("wrote node_graph.json\n")

    _render(sink, "text")
    return sink.exit_code(strict=args.strict)


def _cmd_serve(args: argparse.Namespace) -> int:
    from .server import serve

    sink = DiagnosticSink()
    root = Path(args.project).expanduser().resolve() if args.project else Path.cwd()
    if not root.is_dir():
        sink.io_failure = True
        sink.error("E00", f"项目根不存在：{root}", hint="用 --project 指定包含 slc.yaml 的目录")
        _render(sink, "text")
        return sink.exit_code()
    try:
        return serve(root, host=args.host, port=args.port, open_browser=not args.no_open)
    except OSError as exc:
        sink.io_failure = True
        sink.error("E00", f"serve 启动失败：{exc}", hint="端口被占用时用 --port 换一个")
        _render(sink, "text")
        return sink.exit_code()


def _cmd_trace(args: argparse.Namespace) -> int:
    from .trace import normalize, stats, summary

    sink = DiagnosticSink()
    if args.trace_command == "normalize":
        src = Path(args.src)
        if not src.exists():
            sink.io_failure = True
            sink.error("E00", f"未找到 trace 文件 {src}", hint="确认 --trace 路径后重试")
            _render(sink, "text")
            return sink.exit_code()
        result = normalize(src, Path(args.output), args.flavor, sink=sink)
        if not sink.has_errors():
            sys.stderr.write(f"normalized {result.rows} rows → {args.output}\n")
        _render(sink, "text")
        return sink.exit_code()

    if args.trace_command == "summary":
        payload = summary(Path(args.run), Path(args.graph), args.flavor, sink=sink)
        if payload and not sink.has_errors():
            from .atomic import AtomicWriteError, atomic_write

            try:
                atomic_write(Path(args.output), json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            except AtomicWriteError as exc:
                sink.error("E12", str(exc), hint="检查输出路径权限后重试")
            else:
                sys.stdout.write(f"wrote {args.output}\n")
        _render(sink, "text")
        return sink.exit_code()

    if args.trace_command == "stats":
        payload = stats(Path(args.file), sink=sink)
        if payload and not sink.has_errors():
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        _render(sink, "text")
        return sink.exit_code()

    return _cmd_unimplemented(args)


def _cmd_migrate(args: argparse.Namespace) -> int:
    from .migrate import MigrationError, migrate_file

    sink = DiagnosticSink()
    path = Path.cwd() / "slc.yaml"
    try:
        result = migrate_file(path, dry_run=args.dry_run, from_version=args.from_version)
    except MigrationError as exc:
        if not path.exists():
            sink.io_failure = True
        sink.error("E00", str(exc), hint="迁移前请先备份；slc 会自动写 .slc/snapshots/")
        _render(sink, "text")
        return sink.exit_code()

    if not result.steps:
        sys.stdout.write(f"slc.yaml 已是 {result.to_version}，无需迁移\n")
        _render(sink, "text")
        return sink.exit_code()

    if args.dry_run:
        sys.stdout.write(json.dumps(result.patch, ensure_ascii=False, indent=2) + "\n")
    else:
        chain = " → ".join([result.from_version, *(step.target for step in result.steps)])
        sys.stdout.write(f"migrated slc.yaml: {chain}\n")
        if result.snapshot:
            sys.stdout.write(f"snapshot: {result.snapshot}\n")
    _render(sink, "text")
    return sink.exit_code()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except CliUsageError as exc:
        sink = DiagnosticSink()
        sink.error("E00", f"CLI 用法错误：{exc}", hint="运行 slc --help")
        _render(sink, "text")
        return 1
    except SystemExit as exc:
        return int(exc.code or 0)

    if args.command == "doctor":
        return _cmd_doctor(args)
    if args.command == "plugin":
        return _cmd_plugin_list(args)
    if args.command == "check":
        return _cmd_check(args)
    if args.command == "sync":
        return _cmd_sync(args)
    if args.command == "graph":
        return _cmd_graph(args)
    if args.command == "trace":
        return _cmd_trace(args)
    if args.command == "serve":
        return _cmd_serve(args)
    if args.command == "migrate":
        return _cmd_migrate(args)
    if args.command == "init":
        return _cmd_init(args)
    if args.command == "import":
        return _cmd_import(args)
    if args.command == "gen":
        return _cmd_gen(args)
    return _cmd_unimplemented(args)
