"""统一诊断模型与退出码口径。

退出码只此一套：0 成功；1 存在 E 或 CLI 用法错误；2 仅 W 且 --strict；3 环境/IO。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import IO, Literal, Sequence

Severity = Literal["E", "W", "I"]

_SEVERITY_WORD: dict[Severity, str] = {
    "E": "error",
    "W": "warning",
    "I": "info",
}

_GITHUB_LEVEL: dict[Severity, str] = {
    "E": "error",
    "W": "warning",
    "I": "notice",
}


@dataclass(frozen=True)
class Location:
    file: str | None = None
    line: int | None = None
    col: int | None = None
    json_path: str | None = None
    node_id: str | None = None

    def as_text(self) -> str:
        if self.file and self.line is not None:
            base = f"{self.file}:{self.line}"
            if self.col is not None:
                base += f":{self.col}"
        elif self.file:
            base = self.file
        elif self.node_id:
            base = f"node:{self.node_id}"
        elif self.json_path:
            base = self.json_path
        else:
            return "-"

        if self.json_path and self.file:
            return f"{base} ({self.json_path})"
        if self.json_path and not self.file:
            return self.json_path
        return base

    def as_dict(self) -> dict[str, object]:
        data: dict[str, object] = {}
        for key in ("file", "line", "col", "json_path", "node_id"):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        return data


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: Severity
    message: str
    where: Location = field(default_factory=Location)
    hint: str | None = None

    def as_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "code": self.code,
            "severity": _SEVERITY_WORD[self.severity],
            "message": self.message,
            "location": self.where.as_dict(),
        }
        if self.hint:
            data["hint"] = self.hint
        return data

    def render_text(self) -> str:
        line = f"{self.where.as_text()}: {self.code} {_SEVERITY_WORD[self.severity]} {self.message}"
        if self.hint:
            line += f"\n  hint: {self.hint}"
        return line

    def render_github(self) -> str:
        level = _GITHUB_LEVEL[self.severity]
        parts: list[str] = []
        if self.where.file:
            escaped_file = self.where.file.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            parts.append(f"file={escaped_file}")
        if self.where.line is not None:
            parts.append(f"line={self.where.line}")
        if self.where.col is not None:
            parts.append(f"col={self.where.col}")
        message = self.message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        prefix = f"::{level} " + ",".join(parts) if parts else f"::{level}"
        return f"{prefix}::{self.code} {message}"


class DiagnosticSink:
    """收集诊断，不直接打印；由 CLI 决定渲染目标。"""

    def __init__(self) -> None:
        self.items: list[Diagnostic] = []
        self.io_failure = False

    def add(self, diagnostic: Diagnostic) -> None:
        self.items.append(diagnostic)

    def error(
        self,
        code: str,
        message: str,
        where: Location | None = None,
        hint: str | None = None,
    ) -> None:
        self.add(Diagnostic(code=code, severity="E", message=message, where=where or Location(), hint=hint))

    def warning(
        self,
        code: str,
        message: str,
        where: Location | None = None,
        hint: str | None = None,
    ) -> None:
        self.add(Diagnostic(code=code, severity="W", message=message, where=where or Location(), hint=hint))

    def info(
        self,
        code: str,
        message: str,
        where: Location | None = None,
        hint: str | None = None,
    ) -> None:
        self.add(Diagnostic(code=code, severity="I", message=message, where=where or Location(), hint=hint))

    def extend(self, diagnostics: Sequence[Diagnostic]) -> None:
        self.items.extend(diagnostics)

    def has_errors(self) -> bool:
        return any(item.severity == "E" for item in self.items)

    def has_warnings(self) -> bool:
        return any(item.severity == "W" for item in self.items)

    def exit_code(self, *, strict: bool = False) -> int:
        if self.io_failure:
            return 3
        if self.has_errors():
            return 1
        if strict and self.has_warnings():
            return 2
        return 0

    def render(self, output_format: str = "text", *, stream: IO[str] | None = None) -> str:
        if output_format == "json":
            text = json.dumps({"diagnostics": [item.as_dict() for item in self.items]}, ensure_ascii=False, indent=2)
        elif output_format == "github":
            text = "\n".join(item.render_github() for item in self.items)
        else:
            text = "\n".join(item.render_text() for item in self.items)

        if stream is not None and text:
            stream.write(text)
            if not text.endswith("\n"):
                stream.write("\n")
        return text
