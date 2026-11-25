"""P1 属性测试：§8.4 三条不变式（不含 emit/trace）。"""

from __future__ import annotations

import json

from hypothesis import HealthCheck, given, settings, strategies as st

from slc.diag import DiagnosticSink
from slc.digest import canonicalize_model, fingerprint_model, fingerprint_payload
from slc.graph import build, normalize, topsort
from slc.loader import load_data

_PORT_NAME = st.from_regex(r"[a-z][a-z0-9_]{1,7}", fullmatch=True)
_MODULE_NAME = st.from_regex(r"[a-z][a-z0-9_]{2,7}", fullmatch=True)


@st.composite
def design_documents(draw):
    count = draw(st.integers(min_value=1, max_value=3))
    names = draw(st.lists(_MODULE_NAME, min_size=count, max_size=count, unique=True))
    modules = []
    for name in names:
        ports = [{"name": "clk", "dir": "input", "kind": "clock"}]
        for index in range(draw(st.integers(min_value=1, max_value=3))):
            width = draw(st.one_of(st.integers(min_value=1, max_value=64), st.just("W")))
            ports.append({"name": f"o{index}", "dir": "output", "width": width})
        modules.append(
            {
                "name": name,
                "kind": "module",
                "clock": "clk",
                "params": [{"name": "W", "default": draw(st.integers(min_value=1, max_value=32))}],
                "ports": ports,
            }
        )
    return {
        "schema_version": "1.1.0",
        "project": {
            "name": "prop_proj",
            "top": "top",
            "default_clock": "clk",
            "reset": {"name": "rst_n", "polarity": "active_low", "sync": True, "levels": 2},
        },
        "clocks": [{"name": "clk", "freq_hz": 50000000, "domain_id": "sys", "source": "pad"}],
        "modules": modules,
        "top": {"ports": [{"name": "clk", "dir": "input", "role": "clock"}]},
    }


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(design_documents())
def test_canonical_fingerprint_is_stable_across_json_roundtrip(document) -> None:
    model, diagnostics = load_data(document)
    assert model is not None, [item.message for item in diagnostics]
    payload = canonicalize_model(model)
    roundtrip = json.loads(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    assert fingerprint_payload(roundtrip) == fingerprint_model(model)


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(design_documents())
def test_graph_normalize_is_idempotent(document) -> None:
    model, _ = load_data(document)
    sink = DiagnosticSink()
    graph = build(model, sink)
    assert not sink.has_errors(), [item.message for item in sink.items if item.severity == "E"]
    once = normalize(graph.document)
    twice = normalize(once)
    assert once == twice
    assert json.dumps(once, sort_keys=True) == json.dumps(twice, sort_keys=True)


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(design_documents())
def test_topsort_is_total_and_stable_for_acyclic_graphs(document) -> None:
    model, _ = load_data(document)
    graph = build(model, DiagnosticSink())
    order = topsort(graph)
    assert len(order) == len(document["modules"])
    assert order == topsort(graph)
    assert len(set(order)) == len(order)
