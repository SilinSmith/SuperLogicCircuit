"""P1 graph：建图、规则码 E01/E02/E03/E05/E07/E08/E13/E14、带宽与确定性。"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from rvgen.diag import DiagnosticSink
from rvgen.graph import bandwidth, build, normalize, topsort, write
from rvgen.loader import load_data


def mod(name: str, *, clock: str = "clk", ports=None, **extra):
    data = {"name": name, "kind": "module", "clock": clock, "ports": ports or []}
    data.update(extra)
    return data


def doc(modules, *, clocks=None, cdc=None, top_ports=None, project=None):
    return {
        "schema_version": "1.1.0",
        "project": project
        or {
            "name": "proj",
            "top": "top",
            "default_clock": "clk",
            "reset": {"name": "rst_n", "polarity": "active_low", "sync": True, "levels": 2},
        },
        "clocks": clocks
        or [{"name": "clk", "freq_hz": 50000000, "domain_id": "sys", "source": "pad"}],
        "modules": modules,
        "cdc": cdc or [],
        "top": {"ports": top_ports if top_ports is not None else []},
    }


def run(document):
    model, load_diagnostics = load_data(document)
    assert model is not None, [item.message for item in load_diagnostics]
    sink = DiagnosticSink()
    sink.extend(item for item in load_diagnostics if item.severity == "E")
    graph = build(model, sink)
    return graph, sink


def codes(sink: DiagnosticSink) -> list[str]:
    return [item.code for item in sink.items]


def test_builds_nodes_edges_and_derived_bandwidth() -> None:
    document = doc(
        [
            mod(
                "alpha",
                ports=[
                    {"name": "clk", "dir": "input", "kind": "clock"},
                    {"name": "out", "dir": "output", "width": 8, "connect": "beta.inp"},
                ],
            ),
            mod("beta", ports=[{"name": "clk", "dir": "input", "kind": "clock"}, {"name": "inp", "dir": "input", "width": 8}]),
        ],
        top_ports=[
            {"name": "clk", "dir": "input", "role": "clock"},
            {"name": "a_out", "dir": "output", "from": "alpha.out"},
        ],
    )
    graph, sink = run(document)
    node_ids = {node["id"] for node in graph.nodes}
    assert node_ids == {"mod:alpha", "mod:beta", "clk:clk"}
    data_edges = [edge for edge in graph.edges if edge["kind"] == "data"]
    assert len(data_edges) == 1
    edge = data_edges[0]
    assert edge["id"] == "mod:alpha.out->mod:beta.inp"
    assert edge["width_bits"] == 8
    assert edge["bandwidth"] == {"source": "derived", "width_bits": 8, "clock": "clk", "freq_hz": 50000000.0}
    assert codes(sink) == []
    schema = json.loads(Path("schema/node_graph.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(graph.document)


def test_E01_unresolved_width_marks_node_port() -> None:
    document = doc(
        [
            mod(
                "alpha",
                ports=[
                    {"name": "clk", "dir": "input", "kind": "clock"},
                    {"name": "out", "dir": "output", "width": "UNKNOWN"},
                ],
            )
        ],
        top_ports=[
            {"name": "clk", "dir": "input", "role": "clock"},
            {"name": "a_out", "dir": "output", "from": "alpha.out"},
        ],
    )
    graph, sink = run(document)
    assert "E01" in codes(sink)
    port = next(item for item in graph.nodes if item["id"] == "mod:alpha")["ports"][1]
    assert port["width_bits"] is None
    assert port["unresolved"] == "E01"


def test_E03_self_loop_and_two_module_cycle() -> None:
    self_doc = doc(
        [
            mod(
                "alpha",
                ports=[
                    {"name": "clk", "dir": "input", "kind": "clock"},
                    {"name": "out", "dir": "output", "width": 8, "connect": "alpha.out"},
                ],
            )
        ],
        top_ports=[{"name": "clk", "dir": "input", "role": "clock"}],
    )
    _, sink = run(self_doc)
    assert "E03" in codes(sink)

    cycle_doc = doc(
        [
            mod(
                "alpha",
                ports=[
                    {"name": "clk", "dir": "input", "kind": "clock"},
                    {"name": "inp", "dir": "input", "width": 8, "connect": "beta.out"},
                    {"name": "out", "dir": "output", "width": 8, "connect": "beta.inp"},
                ],
            ),
            mod(
                "beta",
                ports=[
                    {"name": "clk", "dir": "input", "kind": "clock"},
                    {"name": "inp", "dir": "input", "width": 8},
                    {"name": "out", "dir": "output", "width": 8, "connect": "alpha.inp"},
                ],
            ),
        ],
        top_ports=[{"name": "clk", "dir": "input", "role": "clock"}],
    )
    graph, sink = run(cycle_doc)
    message = next(item.message for item in sink.items if item.code == "E03")
    assert "alpha" in message and "beta" in message
    assert topsort(graph) == []


def test_E05_dangling_and_direction_conflict() -> None:
    document = doc(
        [
            mod(
                "alpha",
                ports=[
                    {"name": "clk", "dir": "input", "kind": "clock"},
                    {"name": "out", "dir": "output", "width": 8, "connect": "ghost.p"},
                    {"name": "x", "dir": "input", "width": 8, "connect": "beta.y", "default": "8'h0"},
                ],
            ),
            mod(
                "beta",
                ports=[
                    {"name": "clk", "dir": "input", "kind": "clock"},
                    {"name": "y", "dir": "input", "width": 8, "connect": "alpha.x", "default": "8'h0"},
                ],
            ),
        ],
        top_ports=[{"name": "clk", "dir": "input", "role": "clock"}],
    )
    _, sink = run(document)
    assert codes(sink).count("E05") >= 2


def test_E08_cross_domain_without_cdc_then_suppressed() -> None:
    clocks = [
        {"name": "clk", "freq_hz": 50000000, "domain_id": "sys", "source": "pad"},
        {"name": "clk2", "freq_hz": 100000000, "domain_id": "fast", "source": "pad"},
    ]
    modules = [
        mod(
            "alpha",
            ports=[
                {"name": "clk", "dir": "input", "kind": "clock"},
                {"name": "out", "dir": "output", "width": 8, "connect": "beta.inp"},
            ],
        ),
        mod(
            "beta",
            clock="clk2",
            ports=[{"name": "clk2", "dir": "input", "kind": "clock"}, {"name": "inp", "dir": "input", "width": 8}],
        ),
    ]
    top_ports = [
        {"name": "clk", "dir": "input", "role": "clock"},
        {"name": "a_out", "dir": "output", "from": "alpha.out"},
    ]
    _, sink = run(doc(modules, clocks=clocks, top_ports=top_ports))
    assert "E08" in codes(sink)

    cdc = [{"id": "sys_fast", "from": "sys", "to": "fast", "kind": "2ff", "width": 8}]
    graph, suppressed = run(doc(modules, clocks=clocks, cdc=cdc, top_ports=top_ports))
    assert "E08" not in codes(suppressed)
    cdc_nodes = [node for node in graph.nodes if node["type"] == "cdc_node"]
    assert [node["id"] for node in cdc_nodes] == ["cdc:sys_fast"]
    assert "clk:clk->cdc:sys_fast" in {edge["id"] for edge in graph.edges}


def test_W03_width_mismatch() -> None:
    document = doc(
        [
            mod(
                "alpha",
                ports=[
                    {"name": "clk", "dir": "input", "kind": "clock"},
                    {"name": "out", "dir": "output", "width": 8, "connect": "beta.inp"},
                ],
            ),
            mod("beta", ports=[{"name": "clk", "dir": "input", "kind": "clock"}, {"name": "inp", "dir": "input", "width": 16}]),
        ],
        top_ports=[
            {"name": "clk", "dir": "input", "role": "clock"},
            {"name": "a_out", "dir": "output", "from": "alpha.out"},
        ],
    )
    _, sink = run(document)
    assert "W03" in codes(sink)


def test_E02_unknown_top_reference_and_direction() -> None:
    document = doc(
        [mod("alpha", ports=[{"name": "clk", "dir": "input", "kind": "clock"}, {"name": "out", "dir": "output", "width": 8}])],
        top_ports=[
            {"name": "clk", "dir": "input", "role": "clock"},
            {"name": "ghost_out", "dir": "output", "from": "ghost.p"},
            {"name": "bad_in", "dir": "input", "to": ["alpha.out"]},
        ],
    )
    _, sink = run(document)
    assert codes(sink).count("E02") >= 2


def test_E13_duplicate_top_name_and_multi_driver() -> None:
    document = doc(
        [
            mod(
                "alpha",
                ports=[
                    {"name": "clk", "dir": "input", "kind": "clock"},
                    {"name": "out", "dir": "output", "width": 8},
                    {"name": "out2", "dir": "output", "width": 8},
                ],
            )
        ],
        top_ports=[
            {"name": "clk", "dir": "input", "role": "clock"},
            {"name": "dup", "dir": "output", "from": "alpha.out"},
            {"name": "dup", "dir": "output", "from": "alpha.out"},
            {"name": "third", "dir": "output", "from": "alpha.out"},
        ],
    )
    _, sink = run(document)
    assert "E13" in codes(sink)
    assert any("多个输出端口驱动" in item.message for item in sink.items if item.code == "E13")


def test_AC10_clock_role_top_port_never_infers_data_connection() -> None:
    """role: clock 的顶层端口即使与数据口同名，也不连线、不产生候选。"""
    document = doc(
        [
            mod(
                "uart",
                ports=[
                    {"name": "clk", "dir": "input", "kind": "clock"},
                    {"name": "rx", "dir": "input", "width": 8},
                    {"name": "tx", "dir": "output", "width": 8},
                ],
            )
        ],
        top_ports=[
            {"name": "clk", "dir": "input", "role": "clock"},
            {"name": "rx", "dir": "input", "role": "clock"},
            {"name": "tx", "dir": "output", "from": "uart.tx"},
        ],
    )
    graph, sink = run(document)
    assert [edge["id"] for edge in graph.edges] == ["clk:clk->mod:uart"]
    assert [edge for edge in graph.edges if edge["kind"] == "data"] == []
    assert "E14" in codes(sink)
    assert any("uart.rx" in item.message for item in sink.items if item.code == "E14")


def test_E14_lists_all_missing_inputs_once() -> None:
    document = doc(
        [
            mod(
                "alpha",
                ports=[
                    {"name": "clk", "dir": "input", "kind": "clock"},
                    {"name": "a", "dir": "input", "width": 1},
                    {"name": "b", "dir": "input", "width": 1},
                ],
            )
        ],
        top_ports=[{"name": "clk", "dir": "input", "role": "clock"}],
    )
    _, sink = run(document)
    errors = [item for item in sink.items if item.code == "E14"]
    assert len(errors) == 1
    assert "alpha.a" in errors[0].message
    assert "alpha.b" in errors[0].message


def test_E07_clock_and_reset_port_name_mismatch() -> None:
    document = doc(
        [
            mod(
                "alpha",
                ports=[
                    {"name": "clk_i", "dir": "input", "kind": "clock"},
                    {"name": "reset", "dir": "input", "kind": "reset"},
                ],
            )
        ],
        top_ports=[{"name": "clk", "dir": "input", "role": "clock"}],
    )
    _, sink = run(document)
    assert codes(sink).count("E07") == 2


def test_uppercase_names_cannot_form_node_ids() -> None:
    document = doc(
        [mod("UART", ports=[{"name": "clk", "dir": "input", "kind": "clock"}])],
        top_ports=[{"name": "clk", "dir": "input", "role": "clock"}],
    )
    _, sink = run(document)
    assert "E09" in codes(sink)


def test_bandwidth_explicit_wins() -> None:
    assert bandwidth(8, 50000000) is None
    assert bandwidth(8, 50000000, clock_name="clk")["source"] == "derived"
    assert bandwidth(8, 50000000, 2.5)["source"] == "explicit"


def test_normalize_and_topsort_are_deterministic() -> None:
    document = doc(
        [
            mod("alpha", ports=[{"name": "clk", "dir": "input", "kind": "clock"}, {"name": "out", "dir": "output", "width": 8, "connect": "beta.inp"}]),
            mod("beta", ports=[{"name": "clk", "dir": "input", "kind": "clock"}, {"name": "inp", "dir": "input", "width": 8}]),
        ],
        top_ports=[{"name": "clk", "dir": "input", "role": "clock"}, {"name": "a_out", "dir": "output", "from": "alpha.out"}],
    )
    graph, _ = run(document)
    first = json.dumps(normalize(graph.document), sort_keys=True)
    second = json.dumps(normalize(normalize(graph.document)), sort_keys=True)
    assert first == second
    assert topsort(graph) == topsort(graph) == ["mod:alpha", "mod:beta"]


def test_plugin_extension_fields_reach_node() -> None:
    document = doc(
        [
            mod(
                "if_stage",
                ports=[{"name": "clk", "dir": "input", "kind": "clock"}],
                **{"x-cpu-stage": "IF", "x-cpu-stage_index": 0},
            )
        ],
        top_ports=[{"name": "clk", "dir": "input", "role": "clock"}],
    )
    graph, sink = run(document)
    assert not sink.has_errors()
    node = next(item for item in graph.document["nodes"] if item["id"] == "mod:if_stage")
    assert node["x-cpu-stage"] == "IF"
    assert node["x-cpu-stage_index"] == 0


def test_write_is_atomic_deterministic_and_keeps_lf(tmp_path: Path) -> None:
    document = doc(
        [mod("alpha", ports=[{"name": "clk", "dir": "input", "kind": "clock"}])],
        top_ports=[{"name": "clk", "dir": "input", "role": "clock"}],
    )
    graph, _ = run(document)
    target = tmp_path / "node_graph.json"
    write(graph, target)
    first = target.read_bytes()
    write(graph, target)
    second = target.read_bytes()
    assert first == second
    assert first.endswith(b"\n")
    assert b"\r\n" not in first
