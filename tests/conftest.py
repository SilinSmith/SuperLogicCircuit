"""pytest 全局开关。"""

from __future__ import annotations


def pytest_addoption(parser) -> None:
    parser.addoption("--update-golden", action="store_true", default=False, help="重写 tests/golden 下的黄金文件")
