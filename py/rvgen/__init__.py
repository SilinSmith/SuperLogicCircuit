"""rvgen：声明式 Verilog/IP 工程脚手架。

P0 只提供地基：契约、诊断、原子写、plugin 发现与 CLI 骨架。
语义核心（loader/model/graph/emitter）从 P1 开始实现。
"""

from __future__ import annotations

__version__ = "1.0.1"

__all__ = ["__version__"]
