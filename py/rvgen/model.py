"""领域模型与语义校验（纯内存，禁止 IO）。

核心只认识 module/bridge/memory/clock_gen 四类结构件；
任何 ``x-`` 扩展字段原样透传，核心不解释其取值。
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from .diag import Diagnostic, Location
from .plugins import Plugin

YAML_FILE = "rvgen.yaml"
CORE_KINDS: tuple[str, ...] = ("module", "bridge", "memory", "clock_gen")
BUILTIN_INTERFACE_TYPES: tuple[str, ...] = ("ready_valid", "axi4lite", "axi4stream", "apb", "uart")
_IMPLICIT_WIDTH_KINDS = ("valid", "ready", "clock", "reset")

# 与附录 C 一致：只放行整数常量、参数名、+ - * // % << >> 与一元正负
_OK_BIN_OPS = (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Mod, ast.LShift, ast.RShift)
_MAX_EXPR_DEPTH = 8


class PortDir(str, Enum):
    input = "input"
    output = "output"
    inout = "inout"


class PortKind(str, Enum):
    data = "data"
    valid = "valid"
    ready = "ready"
    handshake = "handshake"
    clock = "clock"
    reset = "reset"
    param = "param"


class ModuleStatus(str, Enum):
    draft = "draft"
    wip = "wip"
    stable = "stable"
    frozen = "frozen"


class ClockSource(str, Enum):
    pll = "pll"
    pad = "pad"
    generated = "generated"


class TopPortRole(str, Enum):
    clock = "clock"
    reset = "reset"
    data = "data"


class WidthError(ValueError):
    """位宽解析失败；由调用方转成 E01。"""

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint


def _enum(enum_type: type[Enum], value: Any, label: str) -> Any:
    try:
        return enum_type(value)
    except ValueError as exc:  # schema 已保证取值合法；这里只防手写数据
        raise WidthError(f"{label} 取值非法：{value!r}") from exc


def _extensions(data: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if isinstance(key, str) and key.startswith("x-")}


def _safe_eval(node: ast.AST, params: Mapping[str, int], depth: int) -> int:
    if depth > _MAX_EXPR_DEPTH:
        raise ValueError("表达式嵌套超过 8 层")
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in params:
            raise KeyError(node.id)
        return params[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _safe_eval(node.operand, params, depth + 1)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and isinstance(node.op, _OK_BIN_OPS):
        left = _safe_eval(node.left, params, depth + 1)
        right = _safe_eval(node.right, params, depth + 1)
        if isinstance(node.op, ast.FloorDiv) and right == 0:
            raise ValueError("除零")
        if isinstance(node.op, ast.Mod) and right == 0:
            raise ValueError("除零")
        if isinstance(node.op, (ast.LShift, ast.RShift)) and right < 0:
            raise ValueError("移位量为负")
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        if isinstance(node.op, ast.Mod):
            return left % right
        return left << right if isinstance(node.op, ast.LShift) else left >> right
    raise ValueError(f"不允许的语法：{type(node).__name__}")


def _coerce_int(value: Any, params: Mapping[str, int]) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"-?\d+", text):
            return int(text)
        try:
            return _safe_eval(ast.parse(text, mode="eval").body, params, 0)
        except (SyntaxError, KeyError, ValueError):
            return None
    return None


def param_values(module: "ModuleDecl") -> dict[str, int]:
    """按声明顺序求参数值；引用未声明/不可解析的参数直接跳过。"""
    values: dict[str, int] = {}
    for param in module.params:
        resolved = _coerce_int(param.default, values)
        if resolved is not None:
            values[param.name] = resolved
    return values


def resolve_width(port: "Port", params: Mapping[str, int]) -> tuple[int, str]:
    """§5.1 解析链 1–4；失败抛 WidthError（由调用方转 E01）。"""
    width = port.width
    if isinstance(width, int) and not isinstance(width, bool):
        if width > 0:
            return width, "literal"
        raise WidthError(f"端口 {port.name} 位宽必须 > 0：{width}")
    if isinstance(width, str):
        if width in params:
            value = params[width]
            if value > 0:
                return value, "param"
            raise WidthError(f"参数 {width} 的值为 {value}，不可作位宽")
        try:
            value = _safe_eval(ast.parse(width, mode="eval").body, params, 0)
        except (SyntaxError, KeyError, ValueError) as exc:
            raise WidthError(
                f"端口 {port.name} 位宽无法解析：{width!r}（{exc}）",
                hint=f"可用参数：{sorted(params)}；或把 width 写成正整数",
            ) from exc
        if value > 0:
            return value, "expr"
        raise WidthError(f"端口 {port.name} 的位宽表达式结果非正：{value}")
    if port.kind.value in _IMPLICIT_WIDTH_KINDS:
        return 1, "implicit"
    raise WidthError(
        f"端口 {port.name} 缺少位宽",
        hint="给参数加 default，或把 width 写成正整数/已解析表达式",
    )


@dataclass(frozen=True)
class ResetCfg:
    name: str
    polarity: str
    sync: bool
    levels: int
    extensions: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Project:
    name: str
    top: str
    default_clock: str
    reset: ResetCfg
    extensions: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Clock:
    name: str
    freq_hz: float
    domain_id: str
    source: str
    parent: str | None = None
    extensions: Mapping[str, Any] = field(default_factory=dict)
    line: int | None = None
    end_line: int | None = None


@dataclass(frozen=True)
class Cdc:
    id: str
    from_domain: str
    to_domain: str
    kind: str
    width: int | None = None
    depth: int | None = None
    almost_full: int | None = None
    extensions: Mapping[str, Any] = field(default_factory=dict)
    line: int | None = None


@dataclass(frozen=True)
class InterfaceSignal:
    name: str
    dir: PortDir
    width: Any = None
    kind: PortKind = PortKind.data
    domain: str | None = None
    default: str | None = None
    connect: str | None = None
    doc: str | None = None
    extensions: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InterfaceLib:
    name: str
    type: str
    params: Mapping[str, Any] = field(default_factory=dict)
    signals: tuple[InterfaceSignal, ...] = ()
    dir_flip: bool = False
    extensions: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InterfaceUse:
    name: str
    type: str
    params: Mapping[str, Any] = field(default_factory=dict)
    signals: tuple[InterfaceSignal, ...] = ()
    dir_flip: bool = False
    extensions: Mapping[str, Any] = field(default_factory=dict)

    @property
    def expanded_signals(self) -> tuple[InterfaceSignal, ...]:
        return self.signals


@dataclass(frozen=True)
class Param:
    name: str
    width: Any = None
    expr: str | None = None
    default: Any = None
    doc: str | None = None
    line: int | None = None


@dataclass(frozen=True)
class Port:
    name: str
    dir: PortDir
    width: Any = None
    kind: PortKind = PortKind.data
    domain: str | None = None
    default: str | None = None
    connect: str | None = None
    doc: str | None = None
    extensions: Mapping[str, Any] = field(default_factory=dict)
    line: int | None = None


@dataclass(frozen=True)
class ModuleDecl:
    name: str
    kind: str
    clock: str
    status: str | None = None
    todo: str | None = None
    params: tuple[Param, ...] = ()
    ports: tuple[Port, ...] = ()
    interfaces: tuple[InterfaceUse, ...] = ()
    extensions: Mapping[str, Any] = field(default_factory=dict)
    contract_extension_keys: frozenset[str] = frozenset()
    line: int | None = None
    end_line: int | None = None

    def port(self, name: str) -> Port | None:
        for port in self.ports:
            if port.name == name:
                return port
        return None


@dataclass(frozen=True)
class TopPort:
    name: str
    dir: str
    from_ref: str | None = None
    to_refs: tuple[str, ...] = ()
    role: str = "data"
    polarity: str | None = None
    default: str | None = None
    line: int | None = None


@dataclass(frozen=True)
class Tieoff:
    port: str
    value: str


@dataclass(frozen=True)
class Top:
    ports: tuple[TopPort, ...] = ()
    tieoffs: tuple[Tieoff, ...] = ()
    extensions: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DesignModel:
    schema_version: str
    project: Project
    clocks: tuple[Clock, ...]
    modules: tuple[ModuleDecl, ...]
    cdc: tuple[Cdc, ...] = ()
    interfaces: tuple[InterfaceLib, ...] = ()
    top: Top = field(default_factory=Top)
    plugins: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    extensions: Mapping[str, Any] = field(default_factory=dict)
    source_text: str = ""
    source_name: str = YAML_FILE

    def clock(self, name: str) -> Clock | None:
        for clock in self.clocks:
            if clock.name == name:
                return clock
        return None

    def module(self, name: str) -> ModuleDecl | None:
        for module in self.modules:
            if module.name == name:
                return module
        return None

    def domain_ids(self) -> set[str]:
        return {clock.domain_id for clock in self.clocks}

    def domain_clock(self, domain_id: str) -> Clock | None:
        for clock in self.clocks:
            if clock.domain_id == domain_id:
                return clock
        return None

    def plugin_enabled(self, plugin_id: str) -> bool:
        config = self.plugins.get(plugin_id)
        if config is None:
            return False
        return bool(config.get("enabled", True))

    def validate_semantic(self, plugins: Sequence[Plugin] = ()) -> list[Diagnostic]:
        """§4.1 的引用存在性与插件规则；不解析任何 x- 取值。"""

        out: list[Diagnostic] = []
        plugin_map = {plugin.id: plugin for plugin in plugins}
        plugin_kinds = {kind for plugin in plugins for kind in plugin.kinds}
        plugin_interface_types = {name for plugin in plugins for name in plugin.interface_types}
        clock_names = {clock.name for clock in self.clocks}
        domain_ids = self.domain_ids()

        seen_clocks: set[str] = set()
        for clock in self.clocks:
            if clock.name in seen_clocks:
                out.append(self._error("E09", f"clock 名重复：{clock.name}", clock.line, f"clocks.{clock.name}.name"))
            seen_clocks.add(clock.name)
            if clock.source == ClockSource.generated.value and clock.parent not in clock_names:
                out.append(
                    self._error(
                        "E05",
                        f"clock {clock.name} 的 parent {clock.parent!r} 未声明",
                        clock.line,
                        f"clocks.{clock.name}.parent",
                        hint=f"已声明 clock：{sorted(clock_names)}",
                    )
                )

        for clock in self.clocks:
            self._check_parent_cycle(clock, clock_names, out)

        if self.project.default_clock not in clock_names:
            out.append(
                self._error(
                    "E05",
                    f"project.default_clock {self.project.default_clock!r} 未在 clocks 中声明",
                    None,
                    "project.default_clock",
                    hint=f"已声明 clock：{sorted(clock_names)}",
                )
            )

        seen_cdc: set[str] = set()
        for cdc in self.cdc:
            if cdc.id in seen_cdc:
                out.append(self._error("E09", f"cdc id 重复：{cdc.id}", cdc.line, f"cdc.{cdc.id}.id"))
            seen_cdc.add(cdc.id)
            for field_name, value in (("from", cdc.from_domain), ("to", cdc.to_domain)):
                if value not in domain_ids:
                    out.append(
                        self._error(
                            "E05",
                            f"cdc {cdc.id} 的 {field_name}={value!r} 不是已声明 domain_id",
                            cdc.line,
                            f"cdc.{cdc.id}.{field_name}",
                            hint=f"已声明 domain：{sorted(domain_ids)}",
                        )
                    )
            if cdc.from_domain == cdc.to_domain:
                out.append(
                    self._warning(
                        "W09",
                        f"cdc {cdc.id} 的 from 与 to 同为 {cdc.from_domain!r}，该桥没有跨域意义",
                        cdc.line,
                        f"cdc.{cdc.id}.from",
                    )
                )
            if cdc.kind == "async_fifo" and cdc.depth is not None and cdc.depth & (cdc.depth - 1):
                out.append(
                    self._error("E09", f"cdc {cdc.id} 的 depth={cdc.depth} 不是 2 的幂", cdc.line, f"cdc.{cdc.id}.depth")
                )
            if cdc.kind == "async_fifo" and cdc.almost_full is not None and cdc.depth is not None:
                if cdc.almost_full >= cdc.depth:
                    out.append(
                        self._error(
                            "E09",
                            f"cdc {cdc.id} 的 almost_full={cdc.almost_full} 必须小于 depth={cdc.depth}",
                            cdc.line,
                            f"cdc.{cdc.id}.almost_full",
                        )
                    )

        lib_names: set[str] = set()
        for interface in self.interfaces:
            if interface.name in lib_names:
                out.append(self._error("E09", f"interfaces 名重复：{interface.name}", None, f"interfaces.{interface.name}.name"))
            lib_names.add(interface.name)
            if not self._interface_type_known(interface.type, plugin_interface_types):
                out.append(
                    self._error(
                        "E05",
                        f"interfaces.{interface.name}.type={interface.type!r} 未注册",
                        None,
                        f"interfaces.{interface.name}.type",
                        hint=f"内置类型：{sorted(BUILTIN_INTERFACE_TYPES)}；插件类型：{sorted(plugin_interface_types)}",
                    )
                )

        seen_modules: set[str] = set()
        for module in self.modules:
            if module.name in seen_modules:
                out.append(self._error("E09", f"module 名重复：{module.name}", module.line, f"modules.{module.name}.name"))
            seen_modules.add(module.name)
            if module.clock not in clock_names:
                out.append(
                    self._error(
                        "E05",
                        f"module {module.name} 的 clock={module.clock!r} 未声明",
                        module.line,
                        f"modules.{module.name}.clock",
                        hint=f"已声明 clock：{sorted(clock_names)}",
                    )
                )
            if module.kind not in CORE_KINDS and module.kind not in plugin_kinds:
                out.append(
                    self._error(
                        "E05",
                        f"module {module.name} 的 kind={module.kind!r} 未注册",
                        module.line,
                        f"modules.{module.name}.kind",
                        hint=f"核心 kind：{sorted(CORE_KINDS)}；插件 kind：{sorted(plugin_kinds)}",
                    )
                )
            port_names: set[str] = set()
            for port in module.ports:
                if port.name in port_names:
                    out.append(
                        self._error(
                            "E09",
                            f"module {module.name} 端口名重复：{port.name}",
                            port.line or module.line,
                            f"modules.{module.name}.ports.{port.name}",
                        )
                    )
                port_names.add(port.name)
            use_names: set[str] = set()
            for interface in module.interfaces:
                if interface.name in use_names:
                    out.append(
                        self._error(
                            "E09",
                            f"module {module.name} 接口实例名重复：{interface.name}",
                            module.line,
                            f"modules.{module.name}.interfaces.{interface.name}",
                        )
                    )
                use_names.add(interface.name)
                if not self._interface_type_known(interface.type, plugin_interface_types):
                    out.append(
                        self._error(
                            "E05",
                            f"module {module.name} 的接口类型 {interface.type!r} 未注册",
                            module.line,
                            f"modules.{module.name}.interfaces.{interface.name}.type",
                            hint=f"内置类型：{sorted(BUILTIN_INTERFACE_TYPES)}；插件类型：{sorted(plugin_interface_types)}",
                        )
                    )
            for key in module.extensions:
                plugin_id = key[2:].split("-", 1)[0]
                if plugin_id not in plugin_map or not self.plugin_enabled(plugin_id):
                    out.append(
                        self._info(
                            "I07",
                            f"module {module.name} 的扩展字段 {key} 对应的 plugin {plugin_id!r} 未启用，已原样保留",
                            module.line,
                            f"modules.{module.name}.{key}",
                        )
                    )

        for plugin_id in self.plugins:
            if plugin_id not in plugin_map:
                out.append(
                    self._warning(
                        "W11",
                        f"rvgen.yaml 配置了 plugin {plugin_id!r}，但未发现对应实现，已忽略",
                        None,
                        f"plugins.{plugin_id}",
                    )
                )
        for plugin in plugins:
            config = self.plugins.get(plugin.id)
            if config is None or not self.plugin_enabled(plugin.id):
                continue
            for rule in plugin.rules:
                try:
                    produced = rule(self, config)
                except Exception as exc:  # plugin 规则失败只降级，不拖垮核心
                    out.append(
                        self._warning("W11", f"plugin {plugin.id} 规则执行失败，已跳过：{exc}", None, f"plugins.{plugin.id}")
                    )
                    continue
                out.extend(produced)
        return out

    def _check_parent_cycle(self, clock: Clock, clock_names: set[str], out: list[Diagnostic]) -> None:
        parent = clock.parent
        seen: list[str] = [clock.name]
        while parent is not None and parent in clock_names:
            if parent in seen:
                out.append(
                    self._error(
                        "E05",
                        f"clock parent 链成环：{' -> '.join([*seen, parent])}",
                        clock.line,
                        f"clocks.{clock.name}.parent",
                    )
                )
                return
            seen.append(parent)
            parent_clock = self.clock(parent)
            parent = parent_clock.parent if parent_clock is not None else None

    @staticmethod
    def _interface_type_known(type_name: str, plugin_types: set[str]) -> bool:
        return type_name in BUILTIN_INTERFACE_TYPES or type_name in plugin_types

    def _error(
        self,
        code: str,
        message: str,
        line: int | None,
        json_path: str,
        hint: str | None = None,
    ) -> Diagnostic:
        return Diagnostic(code=code, severity="E", message=message, where=self._loc(line, json_path), hint=hint)

    def _warning(
        self,
        code: str,
        message: str,
        line: int | None,
        json_path: str,
        hint: str | None = None,
    ) -> Diagnostic:
        return Diagnostic(code=code, severity="W", message=message, where=self._loc(line, json_path), hint=hint)

    def _info(
        self,
        code: str,
        message: str,
        line: int | None,
        json_path: str,
    ) -> Diagnostic:
        return Diagnostic(code=code, severity="I", message=message, where=self._loc(line, json_path))

    def _loc(self, line: int | None, json_path: str) -> Location:
        return Location(file=self.source_name, line=line, json_path=json_path)


def iter_extension_keys(module: ModuleDecl) -> Iterable[str]:
    return (key for key in module.extensions if key.startswith("x-"))
