"""plugin 契约与发现。

核心不认识任何领域概念；plugin 只通过 entry_points(group="slc.plugins")
或 slc.yaml 的 plugins: 局部注册进入。P0 只实现发现与 W11 跳过。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib import metadata
from typing import Any

from .diag import DiagnosticSink

PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
FLAVOR_RE = re.compile(r"^[a-z][a-z0-9_]*$")
KIND_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ENTRY_POINT_GROUP = "slc.plugins"


@dataclass(frozen=True)
class Plugin:
    id: str
    schema: Mapping[str, Any] | None = None
    rules: Sequence[Any] = ()
    views: Sequence[Any] = ()
    trace_flavors: Sequence[str] = ()
    node_types: Sequence[str] = ()
    kinds: Sequence[str] = ()
    interface_types: Sequence[str] = ()

    def validate(self) -> None:
        if not PLUGIN_ID_RE.fullmatch(self.id):
            raise ValueError(f"plugin id 非法：{self.id!r}（要求 {PLUGIN_ID_RE.pattern}）")
        if self.schema is not None and not isinstance(self.schema, Mapping):
            raise ValueError(f"plugin {self.id}: schema 必须是 mapping")
        for node_type in self.node_types:
            prefix = f"p_{self.id}:"
            if not isinstance(node_type, str) or not node_type.startswith(prefix):
                raise ValueError(f"plugin {self.id}: node_type {node_type!r} 必须以 {prefix!r} 开头")
            suffix = node_type[len(prefix) :]
            if not KIND_RE.fullmatch(suffix):
                raise ValueError(f"plugin {self.id}: node_type 后缀非法 {suffix!r}")
        for flavor in self.trace_flavors:
            if not isinstance(flavor, str) or not FLAVOR_RE.fullmatch(flavor):
                raise ValueError(f"plugin {self.id}: trace flavor 非法 {flavor!r}")
        for kind in self.kinds:
            if not isinstance(kind, str) or not KIND_RE.fullmatch(kind):
                raise ValueError(f"plugin {self.id}: kind 非法 {kind!r}")
        for interface_type in self.interface_types:
            if not isinstance(interface_type, str) or not FLAVOR_RE.fullmatch(interface_type):
                raise ValueError(f"plugin {self.id}: interface_type 非法 {interface_type!r}")
        for rule in self.rules:
            if not callable(rule):
                raise ValueError(f"plugin {self.id}: rules 元素必须可调用，实际为 {type(rule).__name__}")


def _coerce_plugin(candidate: Any) -> Plugin:
    if isinstance(candidate, Plugin):
        return candidate
    if callable(candidate):
        produced = candidate()
        if isinstance(produced, Plugin):
            return produced
    raise TypeError(f"entry point 必须返回 slc.plugins.Plugin，实际为 {type(candidate).__name__}")


def discover(
    sink: DiagnosticSink | None = None,
    *,
    entry_points: Iterable[Any] | None = None,
) -> list[Plugin]:
    """发现 plugin；单个失败只记 W11，绝不拖垮核心。"""

    if entry_points is None:
        eps: Iterable[Any] = metadata.entry_points(group=ENTRY_POINT_GROUP)
    else:
        eps = entry_points

    plugins: list[Plugin] = []
    seen: set[str] = set()
    for entry_point in eps:
        name = getattr(entry_point, "name", "<unknown>")
        try:
            plugin = _coerce_plugin(entry_point.load())
            plugin.validate()
        except Exception as exc:  # plugin 是外部代码，任何异常都只能降级为 W11
            if sink is not None:
                sink.warning("W11", f"plugin {name} 发现失败，已跳过：{exc}")
            continue
        if plugin.id in seen:
            if sink is not None:
                sink.warning("W11", f"plugin {name} 的 id {plugin.id!r} 重复，已跳过")
            continue
        seen.add(plugin.id)
        plugins.append(plugin)
    return plugins
