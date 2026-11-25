from __future__ import annotations

from dataclasses import dataclass

import pytest

from slc.diag import DiagnosticSink
from slc.plugins import Plugin, discover


@dataclass
class FakeEntryPoint:
    name: str
    loader: object

    def load(self) -> object:
        return self.loader()  # type: ignore[operator]


def _cpu_plugin() -> Plugin:
    return Plugin(
        id="cpu",
        kinds=("cache", "pipeline_slot"),
        node_types=("p_cpu:cache_node", "p_cpu:pipeline_slot_node"),
        trace_flavors=("cpu",),
        views=("pipeline_slot",),
    )


def test_discover_good_plugin() -> None:
    plugin = _cpu_plugin()
    sink = DiagnosticSink()
    found = discover(sink, entry_points=[FakeEntryPoint("cpu", lambda: plugin)])
    assert found == [plugin]
    assert sink.items == []


def test_discover_skips_failed_plugin_with_w11() -> None:
    def boom() -> object:
        raise RuntimeError("missing dependency")

    sink = DiagnosticSink()
    found = discover(
        sink,
        entry_points=[
            FakeEntryPoint("broken", boom),
            FakeEntryPoint("cpu", _cpu_plugin),
        ],
    )
    assert [plugin.id for plugin in found] == ["cpu"]
    assert any(item.code == "W11" and item.severity == "W" for item in sink.items)


def test_discover_deduplicates_plugin_id() -> None:
    sink = DiagnosticSink()
    found = discover(
        sink,
        entry_points=[
            FakeEntryPoint("cpu-a", _cpu_plugin),
            FakeEntryPoint("cpu-b", _cpu_plugin),
        ],
    )
    assert len(found) == 1
    assert any(item.code == "W11" and "重复" in item.message for item in sink.items)


def test_discover_empty_group() -> None:
    sink = DiagnosticSink()
    assert discover(sink, entry_points=[]) == []
    assert sink.items == []


@pytest.mark.parametrize(
    "plugin",
    [
        Plugin(id="CPU"),
        Plugin(id="cpu", node_types=("cache_node",)),
        Plugin(id="cpu", node_types=("p_bus:cache_node",)),
        Plugin(id="cpu", trace_flavors=("CPU",)),
        Plugin(id="cpu", kinds=("Cache",)),
    ],
)
def test_plugin_validate_rejects_bad_contract(plugin: Plugin) -> None:
    with pytest.raises(ValueError):
        plugin.validate()
