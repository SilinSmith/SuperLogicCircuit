"""P2 emitter：渲染、USER 块合并、生成物保护与 CDC 基础文件。"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from rvgen.diag import DiagnosticSink
from rvgen.emitter import (
    _top_port_width,
    check_outputs,
    emit,
    merge_blocks,
    plan_files,
    render_cdc,
    render_module,
    render_top,
    split_markers,
)
from rvgen.graph import build
from rvgen.loader import load, load_data

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "schema" / "valid" / "rvgen.yaml"


def _load(sink: DiagnosticSink | None = None):
    sink = sink or DiagnosticSink()
    model, diagnostics = load(FIXTURE, [], sink=sink)
    sink.extend(diagnostics)
    assert model is not None
    return model, sink


def _codes(sink: DiagnosticSink) -> list[str]:
    return [item.code for item in sink.items]


def test_render_module_has_fingerprint_and_ports() -> None:
    model, _ = _load()
    module = model.module("uart")
    assert module is not None
    text = render_module(module)
    assert "rvgen:fingerprint" in text
    assert "// rvgen:user-begin logic" in text
    assert "input wire [7:0] cfg" in text


def test_merge_preserves_user_block_and_updates_generated_region() -> None:
    sink = DiagnosticSink()
    generated = "// new\n// rvgen:user-begin logic\n// TODO\n// rvgen:user-end logic\n// tail\n"
    existing = "// old\n// rvgen:user-begin logic\n    assign x = y;\n// rvgen:user-end logic\n// old tail\n"
    merged, orphans = merge_blocks(existing, generated, "uart", sink)
    assert "assign x = y;" in merged
    assert "// new" in merged
    assert "// old tail" not in merged
    assert orphans == ()
    assert "E06" not in _codes(sink)


def test_split_markers_reports_broken_markers() -> None:
    sink = DiagnosticSink()
    split_markers("// rvgen:user-end logic\n", sink)
    split_markers("// rvgen:user-begin a\n// rvgen:user-begin b\n", sink)
    split_markers("// rvgen:user-begin a\n", sink)
    assert _codes(sink).count("E06") == 4


def test_merge_reports_duplicate_and_orphan_block() -> None:
    sink = DiagnosticSink()
    generated = "// rvgen:user-begin logic\n// d\n// rvgen:user-end logic\n"
    existing = (
        "// rvgen:user-begin logic\n// a\n// rvgen:user-end logic\n"
        "// rvgen:user-begin logic\n// b\n// rvgen:user-end logic\n"
        "// rvgen:user-begin extra\n// c\n// rvgen:user-end extra\n"
    )
    merged, orphans = merge_blocks(existing, generated, "uart", sink)
    assert "E06" in _codes(sink)
    assert "I04" in _codes(sink)
    assert orphans == (("extra", "// c\n"),)
    assert "// a" in merged


def test_emit_preserves_user_logic_across_runs(tmp_path: Path) -> None:
    model, sink = _load()
    graph = build(model, sink)
    emit(model, graph, tmp_path, sink)
    uart = tmp_path / "uart.v"
    text = uart.read_text(encoding="utf-8")
    uart.write_text(text.replace("// TODO(rvgen): 手写逻辑写在这里", "    assign tx = rxd;"), encoding="utf-8")

    emit(model, graph, tmp_path, sink)
    assert "assign tx = rxd;" in uart.read_text(encoding="utf-8")
    assert "error" not in {item.severity for item in sink.items}


def test_emit_is_idempotent(tmp_path: Path) -> None:
    model, sink = _load()
    graph = build(model, sink)
    emit(model, graph, tmp_path, sink)
    first = {path.name: path.read_bytes() for path in tmp_path.glob("*.v")}
    emit(model, graph, tmp_path, sink)
    second = {path.name: path.read_bytes() for path in tmp_path.glob("*.v")}
    assert first == second
    assert check_outputs(model, graph, tmp_path, DiagnosticSink()) == []


def test_top_omits_empty_parameter_list(tmp_path: Path) -> None:
    model, sink = _load()
    graph = build(model, sink)
    emit(model, graph, tmp_path, sink)
    top = (tmp_path / "top_core.v").read_text(encoding="utf-8")
    assert "fifo u_fifo (" in top
    assert "#(\n    ) u_fifo" not in top
    assert ".clk(clk)" in top
    assert ".push(fifo_push)" in top


def test_frozen_module_is_skipped_and_reports_e10() -> None:
    model, sink = _load()
    frozen = dataclasses.replace(
        model,
        modules=tuple(
            dataclasses.replace(module, status="frozen") if module.name == "uart" else module
            for module in model.modules
        ),
    )
    graph = build(frozen, sink)

    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        out = Path(raw)
        emit(frozen, graph, out, sink)
        assert "I03" not in _codes(sink)  # 首次不存在，允许生成
        uart = out / "uart.v"
        uart.write_text(uart.read_text(encoding="utf-8").replace("output wire tx", "output wire txx"), encoding="utf-8")
        check_sink = DiagnosticSink()
        stale = check_outputs(frozen, graph, out, check_sink)
        assert [path.name for path in stale] == ["uart.v"]
        assert "E10" in _codes(check_sink)

        emit(frozen, graph, out, sink)
        assert "I03" in _codes(sink)
        assert "txx" in uart.read_text(encoding="utf-8")


def test_non_frozen_stale_reports_e15(tmp_path: Path) -> None:
    model, sink = _load()
    graph = build(model, sink)
    emit(model, graph, tmp_path, sink)
    uart = tmp_path / "uart.v"
    uart.write_text(uart.read_text(encoding="utf-8") + "// drift\n", encoding="utf-8")
    check_sink = DiagnosticSink()
    check_outputs(model, graph, tmp_path, check_sink)
    assert "E15" in _codes(check_sink)


def test_orphan_block_is_backed_up(tmp_path: Path) -> None:
    model, sink = _load()
    graph = build(model, sink)
    emit(model, graph, tmp_path, sink)
    uart = tmp_path / "uart.v"
    text = uart.read_text(encoding="utf-8").replace(
        "endmodule",
        "// rvgen:user-begin extra\n    // keep\n// rvgen:user-end extra\nendmodule",
    )
    uart.write_text(text, encoding="utf-8")
    emit(model, graph, tmp_path, sink)
    assert "I04" in _codes(sink)
    backups = list((tmp_path.parent / ".rvgen" / "orphaned").rglob("uart.extra.v.bak"))
    assert backups
    assert "keep" in backups[0].read_text(encoding="utf-8")


def test_contract_fingerprint_change_warns_w01(tmp_path: Path) -> None:
    model, sink = _load()
    graph = build(model, sink)
    emit(model, graph, tmp_path, sink)
    uart = tmp_path / "uart.v"
    text = uart.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    lines[1] = "// rvgen:fingerprint stale\n"
    uart.write_text("".join(lines), encoding="utf-8")
    plan_files(model, graph, tmp_path, sink)
    assert "W01" in _codes(sink)


def test_sync_converges_after_contract_notice(tmp_path: Path) -> None:
    """W01 提示是一次性的：emit 后立刻 sync --check 不应把提示当成落后。"""
    model, sink = _load()
    graph = build(model, sink)
    emit(model, graph, tmp_path, sink)
    uart = tmp_path / "uart.v"
    lines = uart.read_text(encoding="utf-8").splitlines(keepends=True)
    lines[1] = "// rvgen:fingerprint stale\n"
    uart.write_text("".join(lines), encoding="utf-8")

    emit(model, graph, tmp_path, sink)
    check_sink = DiagnosticSink()
    stale = check_outputs(model, graph, tmp_path, check_sink)
    assert stale == []
    assert "E15" not in _codes(check_sink)


def test_render_cdc_creates_bridge() -> None:
    text = render_cdc("2ff", "two_ff", 8)
    assert "module two_ff #(" in text
    assert "parameter WIDTH = 8" in text
    assert "rvgen:fingerprint cdc/2ff/8" in text


def test_render_top_reports_unbound_output() -> None:
    model, sink = _load()
    graph = build(model, sink)
    render_top(model, graph, sink=sink)
    assert "W04" in _codes(sink)
    assert "W02" not in _codes(sink)


@pytest.mark.parametrize("kind", ["2ff", "async_fifo", "handshake", "pulse_sync", "gray_bus"])
def test_render_cdc_all_kinds(kind: str) -> None:
    assert f"// CDC 基础模块：{kind}" in render_cdc(kind, "bridge", 1)


def _rich_document() -> dict:
    return {
        "schema_version": "1.1.0",
        "project": {
            "name": "demo_top",
            "top": "top",
            "default_clock": "clk",
            "reset": {"name": "rst_n", "polarity": "active_low", "sync": True, "levels": 2},
        },
        "clocks": [
            {"name": "clk", "freq_hz": 100000000, "domain_id": "sys", "source": "pad"},
            {"name": "fast", "freq_hz": 200000000, "domain_id": "fast", "source": "pll"},
        ],
        "cdc": [{"id": "sys_fast", "from": "sys", "to": "fast", "kind": "2ff", "width": 8}],
        "modules": [
            {
                "name": "alpha",
                "kind": "module",
                "clock": "clk",
                "ports": [
                    {"name": "clk", "dir": "input", "kind": "clock"},
                    {"name": "dout", "dir": "output", "width": 8},
                ],
            },
            {
                "name": "beta",
                "kind": "module",
                "clock": "clk",
                "ports": [
                    {"name": "clk", "dir": "input", "kind": "clock"},
                    {"name": "rst_n", "dir": "input", "kind": "reset"},
                    {"name": "din", "dir": "input", "width": 8, "default": "8'h00"},
                    {"name": "c_ok", "dir": "input", "width": 8, "connect": "alpha.dout"},
                    {"name": "c_zero", "dir": "input", "width": 1, "connect": "1'b0"},
                    {"name": "v", "dir": "input", "kind": "valid"},
                    {"name": "r", "dir": "input", "kind": "ready"},
                    {"name": "raw", "dir": "input", "width": 8},
                    {"name": "unused", "dir": "output", "width": 4},
                ],
            },
        ],
        "top": {
            "ports": [
                {"name": "clk", "dir": "input", "role": "clock"},
                {"name": "rst_n", "dir": "input", "role": "reset", "polarity": "active_low"},
                {"name": "out", "dir": "output", "from": "alpha.dout"},
            ]
        },
    }


def test_top_context_covers_connect_default_valid_ready_and_cdc() -> None:
    model, diagnostics = load_data(_rich_document())
    assert model is not None and not any(item.severity == "E" for item in diagnostics)
    sink = DiagnosticSink()
    graph = build(model, sink)
    text = render_top(model, graph, sink=sink)
    assert ".c_ok(out)" in text
    assert ".c_zero(1'b0)" in text
    assert ".din(8'h00)" in text
    assert ".v(1'b0)" in text
    assert ".r(1'b0)" in text
    assert ".raw({8{1'b0}})" in text
    assert "two_ff #(" in text
    assert "u_cdc_sys_fast" in text
    codes = _codes(sink)
    assert "W02" in codes
    assert "W04" in codes


def test_top_port_width_falls_back_for_bad_or_missing_refs() -> None:
    model, _ = load_data(_rich_document())
    assert model is not None
    assert _top_port_width(model, "not.a.ref!", ()) is None
    assert _top_port_width(model, "ghost.port", ()) is None
    assert _top_port_width(model, None, ("alpha.dout",)) == 8


def test_plan_and_emit_generate_cdc_files(tmp_path: Path) -> None:
    model, diagnostics = load_data(_rich_document())
    assert model is not None and not any(item.severity == "E" for item in diagnostics)
    sink = DiagnosticSink()
    graph = build(model, sink)
    files = plan_files(model, graph, tmp_path, sink)
    cdc = [file for file in files if file.path.name == "two_ff.v"]
    assert cdc and cdc[0].path.parent.name == "cdc"
    emit(model, graph, tmp_path, sink)
    assert (tmp_path / "gen" / "cdc" / "two_ff.v").exists()


def test_unresolved_width_renders_without_range() -> None:
    document = _rich_document()
    document["modules"][0]["ports"][1]["width"] = "NOPE"
    model, _ = load_data(document)
    assert model is not None
    text = render_module(model.module("alpha"))
    assert "output wire dout" in text


def test_plan_file_existed_flag(tmp_path: Path) -> None:
    model, sink = _load()
    graph = build(model, sink)
    first = plan_files(model, graph, tmp_path, sink)
    assert all(not file.existed for file in first)
    emit(model, graph, tmp_path, sink)
    second = plan_files(model, graph, tmp_path, sink)
    assert all(file.existed for file in second)


def test_top_contract_change_warns_w01(tmp_path: Path) -> None:
    model, sink = _load()
    graph = build(model, sink)
    emit(model, graph, tmp_path, sink)
    top = tmp_path / "top_core.v"
    lines = top.read_text(encoding="utf-8").splitlines(keepends=True)
    lines[1] = "// rvgen:fingerprint stale\n"
    top.write_text("".join(lines), encoding="utf-8")
    plan_files(model, graph, tmp_path, sink)
    assert "W01" in _codes(sink)
