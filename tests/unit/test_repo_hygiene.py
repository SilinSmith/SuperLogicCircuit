"""仓库卫生：样例与夹具目录中的文件必须全部入库。

`.gitignore` 的生成物规则（`layout.json`、`trace_summary.json`）曾把同名样例一起忽略，
本地有文件、CI 干净检出却没有，导致测试在 CI 才失败。这里比对磁盘与 git 索引。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIRS = ("tests/fixtures", "web/public/sample")


def _tracked_files() -> set[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip("当前目录不是 git 工作区")
    return {item.decode("utf-8") for item in completed.stdout.split(b"\0") if item}


@pytest.mark.skipif(shutil.which("git") is None, reason="需要 git")
def test_sample_files_are_tracked() -> None:
    tracked = _tracked_files()
    untracked = [
        path.relative_to(ROOT).as_posix()
        for directory in SAMPLE_DIRS
        for path in (ROOT / directory).rglob("*")
        if path.is_file() and path.relative_to(ROOT).as_posix() not in tracked
    ]
    assert not untracked, f"样例文件未入库（检查 .gitignore 是否忽略）：{untracked}"
