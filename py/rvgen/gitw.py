"""Git 状态只读解析（P5）。

只调用 `git rev-parse` 与 `git status --porcelain -z`，不执行任何写类 git 命令。
路径一律按 `\\0` 分隔解析，不假设 `core.quotePath=false`。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_COUNT_KEYS = ("M", "A", "D", "UU", "??")


@dataclass(frozen=True)
class GitState:
    branch: str
    head: str
    dirty: bool
    counts: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "head": self.head,
            "dirty": self.dirty,
            "counts": dict(self.counts),
        }


def _git(root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.decode("utf-8", "replace")


def parse_porcelain_z(raw: str) -> list[tuple[str, str]]:
    """解析 `git status --porcelain -z`。

    `-z` 下重命名/复制条目为 `XY new\\0old\\0`，原路径紧随其后，这里跳过。
    """
    entries = raw.split("\0")
    result: list[tuple[str, str]] = []
    index = 0
    while index < len(entries):
        token = entries[index]
        index += 1
        if len(token) < 4:
            continue
        status, path = token[:2], token[3:]
        result.append((status, path))
        if status[0] in "RC":
            index += 1
    return result


def count_statuses(entries: list[tuple[str, str]]) -> dict[str, int]:
    counts = {key: 0 for key in _COUNT_KEYS}
    for status, _path in entries:
        if status == "??":
            counts["??"] += 1
            continue
        if "U" in status or status in {"AA", "DD"}:
            counts["UU"] += 1
            continue
        primary = status[0] if status[0] != " " else status[1]
        if primary in "RC":
            primary = "M"
        if primary in counts:
            counts[primary] += 1
    return counts


def read_git_state(root: Path) -> GitState | None:
    """读取分支/HEAD/脏状态；git 缺失或不在仓库内时返回 None。"""
    root = Path(root)
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    head = _git(root, "rev-parse", "--short", "HEAD")
    status = _git(root, "status", "--porcelain", "-z")
    if branch is None or head is None or status is None:
        return None
    entries = parse_porcelain_z(status)
    return GitState(
        branch=branch.strip(),
        head=head.strip(),
        dirty=bool(entries),
        counts=count_statuses(entries),
    )
