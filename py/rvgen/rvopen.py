"""rvgen:// URL 构造与三平台拉起（P5）。

不注册全局 URI Scheme；注册脚本位于 `scripts/`，由用户自行执行。
协议未注册时返回 False，调用方打印手动命令并记 I06。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, urlencode

SCHEME = "rvgen"


def url_for(file: str | Path, line: int | None = None, node_id: str | None = None) -> str:
    params: dict[str, str] = {"file": str(file)}
    if line is not None:
        params["line"] = str(line)
    if node_id is not None:
        params["node"] = node_id
    return f"{SCHEME}://open?" + urlencode(params, quote_via=quote)


def command_for(file: str | Path, line: int | None = None) -> list[str]:
    """协议未注册时的回退命令（复制给用户执行）。"""
    target = f"{file}:{line}" if line is not None else str(file)
    return ["code", "--goto", target]


def open_target(file: str | Path, line: int | None = None) -> bool:
    url = url_for(file, line)
    try:
        if sys.platform.startswith("win"):
            os.startfile(url)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", url], check=True, timeout=10)
        else:
            subprocess.run(["xdg-open", url], check=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return True
