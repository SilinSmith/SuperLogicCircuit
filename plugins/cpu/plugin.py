"""CPU 示例 plugin 的装配入口。"""

from __future__ import annotations

from rvgen.plugins import Plugin

from .rules import validate
from .schema import CPU_SCHEMA
from .trace import TRACE_FLAVORS
from .views import VIEWS


def cpu_plugin() -> Plugin:
    return Plugin(
        id="cpu",
        schema=CPU_SCHEMA,
        rules=(validate,),
        views=VIEWS,
        trace_flavors=TRACE_FLAVORS,
        node_types=("p_cpu:pipeline_slot_node", "p_cpu:cache_node"),
        kinds=("cache", "pipeline_slot"),
    )
