from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "schema"
VALID_DIR = REPO_ROOT / "tests" / "fixtures" / "schema" / "valid"


def load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def load_yaml(name: str) -> dict:
    return yaml.safe_load((VALID_DIR / name).read_text(encoding="utf-8"))


SCHEMAS = {
    "slc": load_schema("slc"),
    "node_graph": load_schema("node_graph"),
    "layout": load_schema("layout"),
    "trace": load_schema("trace"),
}


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_schema_is_valid_draft_2020_12(name: str) -> None:
    Draft202012Validator.check_schema(SCHEMAS[name])


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_schema_declares_draft_2020_12(name: str) -> None:
    assert SCHEMAS[name]["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_valid_slc_sample() -> None:
    Draft202012Validator(SCHEMAS["slc"]).validate(load_yaml("slc.yaml"))


def test_valid_node_graph_sample() -> None:
    data = json.loads((VALID_DIR / "node_graph.json").read_text(encoding="utf-8"))
    Draft202012Validator(SCHEMAS["node_graph"]).validate(data)


def test_valid_layout_sample() -> None:
    data = json.loads((VALID_DIR / "layout.json").read_text(encoding="utf-8"))
    Draft202012Validator(SCHEMAS["layout"]).validate(data)


def test_valid_trace_sample() -> None:
    validator = Draft202012Validator(SCHEMAS["trace"])
    lines = (VALID_DIR / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines
    for line in lines:
        validator.validate(json.loads(line))


def _slc_validator() -> Draft202012Validator:
    return Draft202012Validator(SCHEMAS["slc"])


def test_slc_rejects_core_stage_field() -> None:
    data = copy.deepcopy(load_yaml("slc.yaml"))
    data["modules"][0]["stage"] = "IF"
    assert not _slc_validator().is_valid(data)


def test_slc_accepts_plugin_stage_extension_field() -> None:
    data = copy.deepcopy(load_yaml("slc.yaml"))
    data["modules"][0]["x-cpu-stage"] = "IF"
    _slc_validator().validate(data)


def test_slc_accepts_plugin_kind_at_schema_layer() -> None:
    data = copy.deepcopy(load_yaml("slc.yaml"))
    data["modules"][0]["kind"] = "cache"
    _slc_validator().validate(data)


def test_slc_rejects_inout_on_non_memory_module() -> None:
    data = copy.deepcopy(load_yaml("slc.yaml"))
    data["modules"][0]["ports"].append({"name": "io", "dir": "inout", "width": 1})
    assert not _slc_validator().is_valid(data)


def test_slc_rejects_async_fifo_without_depth() -> None:
    data = copy.deepcopy(load_yaml("slc.yaml"))
    data["cdc"] = [{"id": "cf", "from": "sys", "to": "sys2", "kind": "async_fifo", "width": 8}]
    assert not _slc_validator().is_valid(data)


def test_slc_rejects_generated_clock_without_parent() -> None:
    data = copy.deepcopy(load_yaml("slc.yaml"))
    data["clocks"][0]["source"] = "generated"
    assert not _slc_validator().is_valid(data)


def test_slc_rejects_output_top_port_without_from() -> None:
    data = copy.deepcopy(load_yaml("slc.yaml"))
    del data["top"]["ports"][2]["from"]
    assert not _slc_validator().is_valid(data)


def test_slc_rejects_output_top_port_with_to() -> None:
    data = copy.deepcopy(load_yaml("slc.yaml"))
    data["top"]["ports"][2]["to"] = ["fifo.pop"]
    assert not _slc_validator().is_valid(data)


def test_slc_rejects_data_input_top_port_without_to() -> None:
    data = copy.deepcopy(load_yaml("slc.yaml"))
    data["top"]["ports"].append({"name": "din", "dir": "input"})
    assert not _slc_validator().is_valid(data)


def test_slc_accepts_clock_input_top_port_without_to() -> None:
    data = copy.deepcopy(load_yaml("slc.yaml"))
    data["top"]["ports"].append({"name": "clk_aux", "dir": "input", "role": "clock"})
    _slc_validator().validate(data)


def test_slc_rejects_param_with_width_and_expr() -> None:
    data = copy.deepcopy(load_yaml("slc.yaml"))
    data["modules"][0]["params"][0]["expr"] = "WIDTH"
    assert not _slc_validator().is_valid(data)


def test_node_graph_rejects_metrics_top_level() -> None:
    data = json.loads((VALID_DIR / "node_graph.json").read_text(encoding="utf-8"))
    data["metrics"] = {}
    assert not Draft202012Validator(SCHEMAS["node_graph"]).is_valid(data)


def test_node_graph_rejects_generated_at() -> None:
    data = json.loads((VALID_DIR / "node_graph.json").read_text(encoding="utf-8"))
    data["generated_at"] = "2026-11-24T00:00:00Z"
    assert not Draft202012Validator(SCHEMAS["node_graph"]).is_valid(data)


def test_node_graph_rejects_bare_plugin_node_type() -> None:
    data = json.loads((VALID_DIR / "node_graph.json").read_text(encoding="utf-8"))
    data["nodes"][0]["type"] = "cache_node"
    assert not Draft202012Validator(SCHEMAS["node_graph"]).is_valid(data)


def test_node_graph_accepts_prefixed_plugin_node_type() -> None:
    data = json.loads((VALID_DIR / "node_graph.json").read_text(encoding="utf-8"))
    data["nodes"][0]["type"] = "p_cpu:cache_node"
    Draft202012Validator(SCHEMAS["node_graph"]).validate(data)


def test_node_graph_rejects_explicit_bandwidth_without_reason() -> None:
    data = json.loads((VALID_DIR / "node_graph.json").read_text(encoding="utf-8"))
    data["edges"][0]["bandwidth"] = {"source": "explicit", "value": "8 bits/cycle"}
    assert not Draft202012Validator(SCHEMAS["node_graph"]).is_valid(data)


def test_layout_rejects_non_positive_zoom() -> None:
    data = json.loads((VALID_DIR / "layout.json").read_text(encoding="utf-8"))
    data["views"]["dataflow"]["viewport"]["zoom"] = 0
    assert not Draft202012Validator(SCHEMAS["layout"]).is_valid(data)


def test_trace_rejects_missing_core_column() -> None:
    data = json.loads((VALID_DIR / "trace.jsonl").read_text(encoding="utf-8").splitlines()[0])
    del data["cdc"]
    assert not Draft202012Validator(SCHEMAS["trace"]).is_valid(data)


def test_trace_accepts_plugin_namespace() -> None:
    data = json.loads((VALID_DIR / "trace.jsonl").read_text(encoding="utf-8").splitlines()[0])
    data["p_cpu"] = {"pipe": "IF"}
    Draft202012Validator(SCHEMAS["trace"]).validate(data)
