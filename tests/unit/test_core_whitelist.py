from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "schema"


def load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


SLC = load_schema("slc")
NODE_GRAPH = load_schema("node_graph")
LAYOUT = load_schema("layout")
TRACE = load_schema("trace")


def _has_x_escape(obj: dict) -> bool:
    patterns = obj.get("patternProperties", {})
    return patterns.get("^x-") is True


def test_core_kind_enum_exactly_four() -> None:
    assert SLC["$defs"]["core_kind"]["enum"] == [
        "module",
        "bridge",
        "memory",
        "clock_gen",
    ]


def test_module_kind_is_open_string_not_domain_enum() -> None:
    kind = SLC["$defs"]["module"]["properties"]["kind"]
    assert kind["type"] == "string"


def test_module_schema_has_no_domain_field_names() -> None:
    props = SLC["$defs"]["module"]["properties"]
    assert not ({"stage", "stage_index", "cache"} & set(props))


def test_module_schema_allows_x_cpu_extension() -> None:
    assert _has_x_escape(SLC["$defs"]["module"])


def test_node_graph_core_types_exactly_four() -> None:
    assert NODE_GRAPH["$defs"]["core_node_types"]["enum"] == [
        "module_node",
        "clock_node",
        "cdc_node",
        "stats_node",
    ]


def test_node_graph_plugin_types_require_namespace() -> None:
    assert NODE_GRAPH["$defs"]["plugin_type_pattern"]["pattern"].startswith("^p_")


def test_node_graph_has_no_bare_plugin_types_in_core_enum() -> None:
    core = set(NODE_GRAPH["$defs"]["core_node_types"]["enum"])
    assert "cache_node" not in core
    assert "pipeline_slot_node" not in core


def test_structural_objects_allow_x_extensions() -> None:
    objects = [
        SLC,
        SLC["$defs"]["project"],
        SLC["$defs"]["reset"],
        SLC["$defs"]["clock"],
        SLC["$defs"]["cdc"],
        SLC["$defs"]["interface_signal"],
        SLC["$defs"]["interface_lib"],
        SLC["$defs"]["top"],
        SLC["$defs"]["top_port"],
        SLC["$defs"]["tieoff"],
        SLC["$defs"]["module"],
        SLC["$defs"]["param"],
        SLC["$defs"]["port"],
        SLC["$defs"]["module_interface"],
        NODE_GRAPH["$defs"]["loc"],
        NODE_GRAPH["$defs"]["node_port"],
        NODE_GRAPH["$defs"]["node"],
        NODE_GRAPH["$defs"]["bandwidth_explicit"],
        NODE_GRAPH["$defs"]["bandwidth_derived"],
        NODE_GRAPH["$defs"]["edge"],
        LAYOUT["$defs"]["node_layout"],
        LAYOUT["$defs"]["edge_layout"],
        LAYOUT["$defs"]["viewport"],
        LAYOUT["$defs"]["prefs"],
        LAYOUT["$defs"]["view"],
        TRACE,
        TRACE["$defs"]["arc"],
        TRACE["$defs"]["cdc"],
    ]
    missing = [i for i, obj in enumerate(objects) if not _has_x_escape(obj)]
    assert missing == []
