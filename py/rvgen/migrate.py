"""schema 迁移链（P6 首例：1.0.0 → 1.1.0）。

纪律：先快照原文件，再按步骤纯函数变换；`--dry-run` 只输出 JSON Patch，不落盘。
迁移会丢失 YAML 注释与锚点（PyYAML 限制），因此快照保留原始字节以便人工比对。
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from .atomic import atomic_write
from .loader import SCHEMA_VERSION

_SNAPSHOT_ROOT = Path(".rvgen") / "snapshots"
_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "rvgen.schema.json"

Transformer = Callable[[dict[str, Any]], dict[str, Any]]


class MigrationError(Exception):
    pass


@dataclass(frozen=True)
class Step:
    source: str
    target: str
    apply: Transformer


@dataclass
class MigrateResult:
    path: Path
    from_version: str
    to_version: str
    steps: list[Step]
    patch: list[dict[str, Any]]
    snapshot: Path | None
    written: bool


def _migrate_1_0_to_1_1(document: dict[str, Any]) -> dict[str, Any]:
    """v1.1 通用化：移除 profiles，stage 迁到 x-cpu-*，关闭 axi 端口 kind。"""
    document.pop("profiles", None)
    for module in document.get("modules") or []:
        if not isinstance(module, dict):
            continue
        if "stage" in module:
            module["x-cpu-stage"] = module.pop("stage")
        if "stage_index" in module:
            module["x-cpu-stage_index"] = module.pop("stage_index")
        for port in module.get("ports") or []:
            if isinstance(port, dict) and port.get("kind") == "axi":
                port["kind"] = "handshake"  # v1.1 端口 kind 收敛；AXI 改由 interfaces 表达
    document["schema_version"] = "1.1.0"
    return document


STEPS: tuple[Step, ...] = (
    Step("1.0.0", "1.1.0", _migrate_1_0_to_1_1),
)


def _schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate(document: dict[str, Any]) -> None:
    try:
        Draft202012Validator(_schema()).validate(document)
    except ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise MigrationError(f"迁移结果不符合 {SCHEMA_VERSION} schema（{location}）：{exc.message}") from exc


def migrate_document(
    document: dict[str, Any],
    from_version: str | None = None,
) -> tuple[dict[str, Any], list[Step]]:
    working = copy.deepcopy(document)
    current = str(working.get("schema_version") or from_version or "")
    if not current:
        raise MigrationError("缺少 schema_version，无法确定迁移起点")
    if from_version and from_version != current and current != SCHEMA_VERSION:
        raise MigrationError(f"--from {from_version} 与文件中的 schema_version {current} 不一致")
    applied: list[Step] = []
    while current != SCHEMA_VERSION:
        step = next((candidate for candidate in STEPS if candidate.source == current), None)
        if step is None:
            raise MigrationError(f"没有从 {current} 到 {SCHEMA_VERSION} 的迁移路径")
        working = step.apply(working)
        _validate(working)
        current = step.target
        applied.append(step)
    return working, applied


def json_patch(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    """最小 JSON Patch（add/remove/replace），用于 dry-run 预览。"""
    if isinstance(before, dict) and isinstance(after, dict):
        operations: list[dict[str, Any]] = []
        for key in before:
            if key not in after:
                operations.append({"op": "remove", "path": f"{path}/{key}"})
        for key, value in after.items():
            child = f"{path}/{key}"
            if key not in before:
                operations.append({"op": "add", "path": child, "value": value})
            else:
                operations.extend(json_patch(before[key], value, child))
        return operations
    if before != after:
        return [{"op": "replace", "path": path or "", "value": after}]
    return []


def migrate_file(
    path: Path,
    *,
    dry_run: bool = False,
    from_version: str | None = None,
    now: datetime | None = None,
) -> MigrateResult:
    path = Path(path)
    if not path.is_file():
        raise MigrationError(f"未找到 {path}")
    original = path.read_text(encoding="utf-8")
    try:
        raw = yaml.safe_load(original)
    except yaml.YAMLError as exc:
        raise MigrationError(f"{path} 不是合法 YAML：{exc}") from exc
    if not isinstance(raw, dict):
        raise MigrationError(f"{path} 顶层必须是 mapping")

    migrated, steps = migrate_document(raw, from_version)
    patch = json_patch(raw, migrated)
    snapshot: Path | None = None
    written = False
    if steps and not dry_run:
        stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S%fZ")
        snapshot = _SNAPSHOT_ROOT / stamp / path.name
        atomic_write(snapshot, original)
        atomic_write(path, yaml.safe_dump(migrated, sort_keys=False, allow_unicode=True))
        written = True
    return MigrateResult(
        path=path,
        from_version=str(raw.get("schema_version") or from_version or ""),
        to_version=SCHEMA_VERSION,
        steps=steps,
        patch=patch,
        snapshot=snapshot,
        written=written,
    )
