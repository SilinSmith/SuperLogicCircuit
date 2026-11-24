"""CPU plugin 注册的视图（渲染器由 P4 前端消费，P1 只登记 id）。"""

from __future__ import annotations

VIEWS: tuple[str, ...] = ("pipeline_slot", "cache_state")
