"""CPU plugin 的局部配置 schema（只约束 plugins.cpu 块，不进入核心 schema）。"""

from __future__ import annotations

from typing import Any

CPU_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "enabled": {"type": "boolean"},
        "lanes": {
            "type": "array",
            "items": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_]*$"},
        },
    },
    "additionalProperties": True,
}
