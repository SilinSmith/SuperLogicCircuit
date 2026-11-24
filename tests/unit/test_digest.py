"""P1 digest：契约字段白名单、指纹稳定性与 source_digest。"""

from __future__ import annotations

import json

from rvgen.digest import (
    canonicalize,
    canonicalize_model,
    fingerprint,
    fingerprint_model,
    fingerprint_payload,
    source_digest,
)
from rvgen.loader import load_data


def _doc(ports=None, **module_extra):
    module = {
        "name": "alpha",
        "kind": "module",
        "clock": "clk",
        "todo": "later",
        "status": "wip",
        "params": [{"name": "W", "default": 8}],
        "ports": ports
        or [
            {"name": "clk", "dir": "input", "kind": "clock"},
            {"name": "d", "dir": "input", "width": "W", "doc": "doc"},
        ],
        "interfaces": [],
    }
    module.update(module_extra)
    return {
        "schema_version": "1.1.0",
        "project": {
            "name": "proj",
            "top": "top",
            "default_clock": "clk",
            "reset": {"name": "rst_n", "polarity": "active_low", "sync": True, "levels": 2},
        },
        "clocks": [{"name": "clk", "freq_hz": 50000000, "domain_id": "sys", "source": "pad"}],
        "modules": [module],
        "top": {"ports": []},
    }


def test_canonicalize_keeps_contract_fields_only() -> None:
    model, _ = load_data(_doc(**{"x-note": "ignore me"}))
    assert model is not None
    canonical = canonicalize(model.modules[0])
    assert set(canonical) == {"name", "kind", "clock", "params", "ports", "interfaces", "x"}
    assert canonical["x"] == {}
    assert canonical["params"] == [{"name": "W", "default": 8, "width": None}]
    assert canonical["ports"][1]["width_bits"] == 8
    assert "doc" not in canonical["ports"][1]


def test_doc_and_todo_changes_do_not_change_fingerprint() -> None:
    first, _ = load_data(_doc())
    changed = _doc()
    changed["modules"][0]["todo"] = "other"
    changed["modules"][0]["status"] = "stable"
    changed["modules"][0]["ports"][1]["doc"] = "other"
    second, _ = load_data(changed)
    assert fingerprint(first.modules[0]) == fingerprint(second.modules[0])


def test_width_change_changes_fingerprint() -> None:
    first, _ = load_data(_doc())
    changed = _doc(ports=[{"name": "clk", "dir": "input", "kind": "clock"}, {"name": "d", "dir": "input", "width": 16}])
    second, _ = load_data(changed)
    assert fingerprint(first.modules[0]) != fingerprint(second.modules[0])


def test_plugin_contract_extension_participates_in_fingerprint() -> None:
    from rvgen.plugins import Plugin

    document = _doc(**{"x-cpu-stage": "EX"})
    document["plugins"] = {"cpu": {"enabled": True}}
    first, _ = load_data(document, [Plugin(id="cpu")])
    changed = _doc(**{"x-cpu-stage": "ID"})
    changed["plugins"] = {"cpu": {"enabled": True}}
    second, _ = load_data(changed, [Plugin(id="cpu")])
    assert fingerprint(first.modules[0]) != fingerprint(second.modules[0])
    assert canonicalize(first.modules[0])["x"] == {"x-cpu-stage": "EX"}


def test_canonicalize_model_roundtrips_through_json() -> None:
    model, _ = load_data(_doc())
    payload = canonicalize_model(model)
    roundtrip = json.loads(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    assert fingerprint_payload(roundtrip) == fingerprint_model(model)


def test_source_digest_is_sha256_prefix() -> None:
    digest = source_digest("hello")
    assert digest.startswith("sha256:")
    assert len(digest) == len("sha256:") + 16
    assert digest == source_digest(b"hello")
    assert digest != source_digest("hello\n")


def test_unresolved_width_canonicalizes_to_none() -> None:
    document = _doc(ports=[{"name": "clk", "dir": "input", "kind": "clock"}, {"name": "d", "dir": "input", "width": "MISSING"}])
    model, _ = load_data(document)
    assert model is not None
    port = canonicalize(model.modules[0])["ports"][1]
    assert port["width_bits"] is None


def test_interface_dir_flip_is_applied_in_canonical_form() -> None:
    document = _doc(
        ports=[{"name": "clk", "dir": "input", "kind": "clock"}],
        interfaces=[
            {
                "name": "bus",
                "type": "ready_valid",
                "dir_flip": True,
                "signals": [
                    {"name": "v", "dir": "input", "kind": "valid"},
                    {"name": "r", "dir": "output", "kind": "ready"},
                    {"name": "d", "dir": "inout", "width": 8},
                ],
            },
            {
                "name": "plain",
                "type": "uart",
                "signals": [{"name": "tx", "dir": "output"}],
            },
        ],
    )
    model, _ = load_data(document)
    assert model is not None
    interfaces = canonicalize(model.modules[0])["interfaces"]
    interface = interfaces[0]
    assert [signal["name"] for signal in interface["signals"]] == ["d", "r", "v"]
    directions = {signal["name"]: signal["dir"] for signal in interface["signals"]}
    assert directions == {"v": "output", "r": "input", "d": "inout"}
    assert interface["dir_flip"] is True


def test_library_signal_dir_flip_in_canonical_model() -> None:
    document = _doc(ports=[{"name": "clk", "dir": "input", "kind": "clock"}])
    document["interfaces"] = [
        {
            "name": "bus",
            "type": "ready_valid",
            "dir_flip": True,
            "signals": [
                {"name": "v", "dir": "input"},
                {"name": "r", "dir": "output"},
            ],
        }
    ]
    model, _ = load_data(document)
    assert model is not None
    payload = canonicalize_model(model)
    signals = payload["interfaces"][0]["signals"]
    assert {signal["name"]: signal["dir"] for signal in signals} == {"v": "output", "r": "input"}
