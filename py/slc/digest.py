"""契约规范化与指纹（附录 A）。

指纹只覆盖影响行为契约的字段：不含 doc/todo/status/loc，
不含 ``x-note`` 这类自由注释；只含已启用 plugin 的 ``x-<plugin>-*``
契约字段（由 loader 写入 ``contract_extension_keys``）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .model import (
    DesignModel,
    InterfaceSignal,
    InterfaceUse,
    ModuleDecl,
    Param,
    Port,
    PortDir,
    WidthError,
    param_values,
    resolve_width,
)


def _canonical_param(param: Param) -> dict[str, Any]:
    return {"name": param.name, "default": param.default, "width": param.width}


def _canonical_port(port: Port, params: Mapping[str, int]) -> dict[str, Any]:
    try:
        width_bits, _ = resolve_width(port, params)
    except WidthError:
        width_bits = None
    return {
        "name": port.name,
        "dir": port.dir.value,
        "width_bits": width_bits,
        "kind": port.kind.value,
        "domain": port.domain,
    }


def _flip(signal: InterfaceSignal, dir_flip: bool) -> str:
    if not dir_flip:
        return signal.dir.value
    if signal.dir is PortDir.input:
        return PortDir.output.value
    if signal.dir is PortDir.output:
        return PortDir.input.value
    return signal.dir.value


def _canonical_signal(signal: InterfaceSignal, dir_flip: bool) -> dict[str, Any]:
    return {
        "name": signal.name,
        "dir": _flip(signal, dir_flip),
        "width": signal.width,
        "kind": signal.kind.value,
        "domain": signal.domain,
    }


def _canonical_interface_use(use: InterfaceUse) -> dict[str, Any]:
    signals = sorted(use.expanded_signals, key=lambda item: item.name)
    return {
        "name": use.name,
        "type": use.type,
        "dir_flip": use.dir_flip,
        "params": dict(sorted(use.params.items())),
        "signals": [_canonical_signal(signal, use.dir_flip) for signal in signals],
    }


def canonicalize(module: ModuleDecl) -> dict[str, Any]:
    """§8.4 不变式 1 的规范对象：只保留契约字段。"""
    params = param_values(module)
    return {
        "name": module.name,
        "kind": module.kind,
        "clock": module.clock,
        "params": [_canonical_param(param) for param in module.params],
        "ports": [_canonical_port(port, params) for port in module.ports],
        "interfaces": [_canonical_interface_use(use) for use in module.interfaces],
        "x": {
            key: module.extensions[key]
            for key in sorted(module.contract_extension_keys)
            if key in module.extensions
        },
    }


def canonicalize_model(model: DesignModel) -> dict[str, Any]:
    return {
        "schema_version": model.schema_version,
        "project": {
            "name": model.project.name,
            "top": model.project.top,
            "default_clock": model.project.default_clock,
            "reset": {
                "name": model.project.reset.name,
                "polarity": model.project.reset.polarity,
                "sync": model.project.reset.sync,
                "levels": model.project.reset.levels,
            },
        },
        "clocks": [
            {
                "name": clock.name,
                "freq_hz": clock.freq_hz,
                "domain_id": clock.domain_id,
                "source": clock.source,
                "parent": clock.parent,
            }
            for clock in model.clocks
        ],
        "cdc": [
            {
                "id": cdc.id,
                "from": cdc.from_domain,
                "to": cdc.to_domain,
                "kind": cdc.kind,
                "width": cdc.width,
                "depth": cdc.depth,
                "almost_full": cdc.almost_full,
            }
            for cdc in model.cdc
        ],
        "interfaces": [
            {
                "name": interface.name,
                "type": interface.type,
                "dir_flip": interface.dir_flip,
                "params": dict(sorted(interface.params.items())),
                "signals": [
                    _canonical_signal(signal, interface.dir_flip)
                    for signal in sorted(interface.signals, key=lambda item: item.name)
                ],
            }
            for interface in model.interfaces
        ],
        "modules": [canonicalize(module) for module in model.modules],
        "top": {
            "ports": [
                {
                    "name": port.name,
                    "dir": port.dir,
                    "from": port.from_ref,
                    "to": list(port.to_refs),
                    "role": port.role,
                    "polarity": port.polarity,
                    "default": port.default,
                }
                for port in model.top.ports
            ],
            "tieoffs": [{"port": tieoff.port, "value": tieoff.value} for tieoff in model.top.tieoffs],
        },
    }


def _dumps(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def fingerprint_payload(payload: Any) -> str:
    return hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()


def fingerprint(module: ModuleDecl) -> str:
    return fingerprint_payload(canonicalize(module))


def fingerprint_model(model: DesignModel) -> str:
    return fingerprint_payload(canonicalize_model(model))


def source_digest(text: str | bytes) -> str:
    """§4.2 source_digest：sha256 前 16 位。"""
    data = text.encode("utf-8") if isinstance(text, str) else text
    return f"sha256:{hashlib.sha256(data).hexdigest()[:16]}"
