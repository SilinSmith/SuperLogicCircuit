"""P1 model：位宽解析链、语义引用检查与 plugin 规则降级。"""

from __future__ import annotations

import pytest

from rvgen.diag import Diagnostic, Location
from rvgen.loader import load_data
from rvgen.model import Port, PortDir, PortKind, WidthError, resolve_width
from rvgen.plugins import Plugin


def _port(name: str = "a", width=None, kind: str = "data") -> Port:
    return Port(name=name, dir=PortDir.input, width=width, kind=PortKind(kind))


def module(name: str = "alpha", **overrides):
    data = {
        "name": name,
        "kind": "module",
        "clock": "clk",
        "params": [],
        "ports": [{"name": "clk", "dir": "input", "kind": "clock"}],
    }
    data.update(overrides)
    return data


def doc(**overrides):
    data = {
        "schema_version": "1.1.0",
        "project": {
            "name": "proj",
            "top": "top",
            "default_clock": "clk",
            "reset": {"name": "rst_n", "polarity": "active_low", "sync": True, "levels": 2},
        },
        "clocks": [{"name": "clk", "freq_hz": 50000000, "domain_id": "sys", "source": "pad"}],
        "modules": [module()],
        "top": {"ports": []},
    }
    data.update(overrides)
    return data


def codes(diagnostics) -> list[str]:
    return [item.code for item in diagnostics]


def test_resolve_width_literal_param_expr_and_implicit() -> None:
    assert resolve_width(_port(width=8), {}) == (8, "literal")
    assert resolve_width(_port(width="W"), {"W": 16}) == (16, "param")
    assert resolve_width(_port(width="W * 2"), {"W": 8}) == (16, "expr")
    assert resolve_width(_port(width="W - 1"), {"W": 9}) == (8, "expr")
    assert resolve_width(_port(width="(W + 1) >> 1"), {"W": 31}) == (16, "expr")
    assert resolve_width(_port(width=None, kind="ready"), {}) == (1, "implicit")


@pytest.mark.parametrize(
    "width, params",
    [
        (0, {}),
        (-3, {}),
        ("NOPE", {}),
        ("W // 0", {"W": 8}),
        ("W << -1", {"W": 8}),
        ("W ** 2", {"W": 8}),
        ("True", {}),
    ],
)
def test_resolve_width_rejects_bad_expressions(width, params) -> None:
    with pytest.raises(WidthError):
        resolve_width(_port(width=width), params)


def test_resolve_width_rejects_missing_and_param_zero() -> None:
    with pytest.raises(WidthError):
        resolve_width(_port(width=None), {})
    with pytest.raises(WidthError):
        resolve_width(_port(width="W"), {"W": 0})


def test_resolve_width_depth_limit() -> None:
    expr = "1" + " + 1" * 10
    with pytest.raises(WidthError, match="8 层"):
        resolve_width(_port(width=expr), {})


def test_unknown_default_clock_and_module_clock() -> None:
    document = doc()
    document["project"]["default_clock"] = "nope"
    document["modules"][0]["clock"] = "nope"
    _, diagnostics = load_data(document)
    found = codes(diagnostics)
    assert found.count("E05") >= 2


def test_duplicate_names_and_ports_are_E09() -> None:
    document = doc()
    document["modules"].append(module())
    document["modules"][0]["ports"].append({"name": "clk", "dir": "output"})
    _, diagnostics = load_data(document)
    assert codes(diagnostics).count("E09") >= 2


def test_kind_registration_accepts_plugin_kind_only_with_plugin() -> None:
    document = doc(modules=[module(kind="cache")])
    _, without_plugin = load_data(document)
    assert "E05" in codes(without_plugin)
    plugin = Plugin(id="cpu", kinds=("cache",))
    _, with_plugin = load_data(document, [plugin])
    assert "E05" not in codes(with_plugin)


def test_interface_type_registration_uses_plugin_interface_types() -> None:
    document = doc(
        interfaces=[{"name": "bus", "type": "custom_bus", "signals": []}],
        modules=[module(interfaces=[{"name": "b", "type": "custom_bus"}])],
    )
    _, diagnostics = load_data(document)
    assert codes(diagnostics).count("E05") == 2
    plugin = Plugin(id="custom", interface_types=("custom_bus",))
    _, accepted = load_data(document, [plugin])
    assert "E05" not in codes(accepted)


def test_generated_clock_parent_missing_and_cycle() -> None:
    document = doc()
    document["clocks"] = [
        {"name": "clk", "freq_hz": 50000000, "domain_id": "sys", "source": "pad"},
        {"name": "clk2", "freq_hz": 25000000, "domain_id": "fast", "source": "generated", "parent": "missing"},
    ]
    _, diagnostics = load_data(document)
    assert "E05" in codes(diagnostics)

    document["clocks"][1]["parent"] = "clk3"
    document["clocks"].append(
        {"name": "clk3", "freq_hz": 25000000, "domain_id": "fast2", "source": "generated", "parent": "clk2"}
    )
    _, cyclic = load_data(document)
    assert any("成环" in item.message for item in cyclic if item.code == "E05")


def test_cdc_reference_domain_and_constraints() -> None:
    document = doc(
        cdc=[
            {"id": "bad_ref", "from": "sys", "to": "nope", "kind": "2ff", "width": 1},
            {"id": "same", "from": "sys", "to": "sys", "kind": "2ff", "width": 1},
            {"id": "fifo", "from": "sys", "to": "sys", "kind": "async_fifo", "width": 8, "depth": 6, "almost_full": 7},
        ]
    )
    _, diagnostics = load_data(document)
    assert "E05" in codes(diagnostics)
    assert "W09" in codes(diagnostics)
    assert codes(diagnostics).count("E09") >= 2


def test_x_extension_without_enabled_plugin_is_kept_with_I07() -> None:
    document = doc(modules=[module(**{"x-cpu-stage": "EX"})])
    model, diagnostics = load_data(document)
    assert "I07" in codes(diagnostics)
    assert model is not None
    assert model.modules[0].extensions["x-cpu-stage"] == "EX"
    assert model.modules[0].contract_extension_keys == frozenset()

    document["plugins"] = {"cpu": {"enabled": True}}
    plugin = Plugin(id="cpu")
    model, diagnostics = load_data(document, [plugin])
    assert "I07" not in codes(diagnostics)
    assert model is not None
    assert model.modules[0].contract_extension_keys == frozenset({"x-cpu-stage"})


def test_configured_but_missing_plugin_is_W11() -> None:
    _, diagnostics = load_data(doc(plugins={"ghost": {"enabled": True}}))
    assert "W11" in codes(diagnostics)


def test_plugin_rule_failure_is_W11_and_rule_output_is_forwarded() -> None:
    def broken(model, config):
        raise RuntimeError("boom")

    def reports(model, config):
        return [Diagnostic(code="PCPU-01", severity="E", message="bad", where=Location())]

    document = doc(plugins={"cpu": {"enabled": True}})
    _, failed = load_data(document, [Plugin(id="cpu", rules=(broken,))])
    assert "W11" in codes(failed)

    _, produced = load_data(document, [Plugin(id="cpu", rules=(reports,))])
    assert "PCPU-01" in codes(produced)

    document["plugins"]["cpu"]["enabled"] = False
    _, disabled = load_data(document, [Plugin(id="cpu", rules=(reports,))])
    assert "PCPU-01" not in codes(disabled)


def test_checker_plugin_rule_finds_unknown_stage_and_duplicate_slot() -> None:
    from plugins.cpu.plugin import cpu_plugin

    document = doc(
        plugins={"cpu": {"enabled": True, "lanes": ["IF", "ID"]}},
        modules=[
            module("alpha", **{"x-cpu-stage": "EX", "x-cpu-stage_index": 0}),
            module("beta", **{"x-cpu-stage": "IF", "x-cpu-stage_index": 1}),
            module("gamma", **{"x-cpu-stage": "IF", "x-cpu-stage_index": 1}),
        ],
    )
    _, diagnostics = load_data(document, [cpu_plugin()])
    found = codes(diagnostics)
    assert "PCPU-01" in found
    assert "PCPU-02" in found


def test_uppercase_identifiers_rejected_at_load_stage() -> None:
    document = doc(
        modules=[
            module(
                "UART",
                ports=[
                    {"name": "clk", "dir": "input", "kind": "clock"},
                    {"name": "Tx_Data", "dir": "output"},
                ],
            )
        ],
        top={"ports": [{"name": "clk", "dir": "input", "role": "clock"}]},
    )
    model, diagnostics = load_data(document)
    assert model is not None
    errors = [item for item in diagnostics if item.code == "E09"]
    assert len(errors) == 2
    assert all("小写" in item.message for item in errors)


def test_lowercase_identifiers_and_uppercase_params_are_allowed() -> None:
    document = doc(
        modules=[
            module(
                "alpha",
                params=[{"name": "WIDTH", "default": 8}],
                ports=[
                    {"name": "clk", "dir": "input", "kind": "clock"},
                    {"name": "data_in", "dir": "input", "width": "WIDTH"},
                ],
            )
        ],
        top={"ports": [{"name": "clk", "dir": "input", "role": "clock"}]},
    )
    model, diagnostics = load_data(document)
    assert model is not None
    assert "E09" not in codes(diagnostics)
