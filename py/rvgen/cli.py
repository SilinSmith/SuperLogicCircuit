"""rvgen CLI 骨架。

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
    parser = _CliParser(prog="rvgen", description="声明式 Verilog/IP 工程脚手架")
    parser.add_argument("--version", action="version", version=f"rvgen {__version__}")
    sub = _add_subparsers(parser, "command")

    init = sub.add_parser("init", help="建目录 + rvgen.yaml 样例")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--preset", choices=["minimal", "uart", "rv32i"], default="minimal")

    imp = sub.add_parser("import", help="从已有 Verilog 反生成声明骨架")
    imp.add_argument("file")
    imp.add_argument("-o", "--output", default="rvgen.yaml")

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
            "name": "rvgen_protocol",
            "required": False,
            "status": "deferred",
            "version": None,
            "detail": "rvgen:// 协议注册在 P5 实现",
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
        sys.stdout.write("没有发现 plugin（entry_points group=rvgen.plugins）\n")
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


def _cmd_unimplemented(args: argparse.Namespace) -> int:
    sink = DiagnosticSink()
    sink.error(
        "E00",
        f"rvgen {_command_label(args)} 尚未实现：P0 只提供 CLI 骨架与 check 的 lint 通路",
        hint="按 rvgen完整方案.md 第 9 章，语义核心从 P1 开始实现",
    )
    _render(sink, "text")
    return sink.exit_code()


def _cmd_check(args: argparse.Namespace) -> int:
    # P0：check 只做 schema lint，不写文件；P1 接入语义 diff。
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
    # P0：--check 复用 lint；生成物比对属于 P2。
    if not args.check:
        return _cmd_unimplemented(args)
    from .checker import run_check

    sink = DiagnosticSink()
    code = run_check(
        Path.cwd(),
        sink,
        strict=args.strict,
        output_format="text",
        quiet=False,
        fix=False,
    )
    if code == 0 and (Path.cwd() / "rtl").exists():
        sink.error(
            "E00",
            "rvgen sync --check 的生成物比对在 P2 实现；当前目录已有 rtl/，P0 不能判定是否落后",
            hint="P0 CI 在仓库根目录运行，不会命中此分支",
        )
        _render(sink, "text")
        return sink.exit_code(strict=args.strict)
    return code


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except CliUsageError as exc:
        sink = DiagnosticSink()
        sink.error("E00", f"CLI 用法错误：{exc}", hint="运行 rvgen --help")
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
    return _cmd_unimplemented(args)
