"""CPU plugin 规则：PCPU-01 未知流水级、PCPU-02 同队列重复槽位。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from rvgen.diag import Diagnostic, Location
from rvgen.model import DesignModel


def validate(model: DesignModel, config: Mapping[str, Any]) -> Sequence[Diagnostic]:
    lanes = tuple(str(item) for item in config.get("lanes") or ())
    diagnostics: list[Diagnostic] = []
    seen: dict[tuple[str, Any], str] = {}
    for module in model.modules:
        stage = module.extensions.get("x-cpu-stage")
        if stage is None:
            continue
        if lanes and stage not in lanes:
            diagnostics.append(
                Diagnostic(
                    code="PCPU-01",
                    severity="E",
                    message=f"module {module.name} 的 x-cpu-stage={stage!r} 不在 lanes {list(lanes)} 中",
                    where=Location(file=model.source_name, line=module.line, json_path=f"modules.{module.name}.x-cpu-stage"),
                    hint="在 plugins.cpu.lanes 中登记该流水级，或修正模块扩展字段",
                )
            )
        index = module.extensions.get("x-cpu-stage_index")
        if index is None:
            continue
        key = (str(stage), index)
        if key in seen:
            diagnostics.append(
                Diagnostic(
                    code="PCPU-02",
                    severity="E",
                    message=f"module {module.name} 与 {seen[key]} 占用同一流水槽位 ({stage}, {index})",
                    where=Location(file=model.source_name, line=module.line, json_path=f"modules.{module.name}.x-cpu-stage_index"),
                )
            )
        else:
            seen[key] = module.name
    return diagnostics
