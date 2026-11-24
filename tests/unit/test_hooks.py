from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"


def _sh() -> str:
    candidates = [shutil.which("sh"), r"C:\Program Files\Git\bin\sh.exe", "/bin/sh"]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    pytest.skip("找不到 sh，跳过硬编码 hook 测试")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, timeout=20)


def _install(tmp_path: Path, hook: str) -> None:
    target = tmp_path / ".git" / "hooks" / hook
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(HOOKS / hook, target)
    if os.name != "nt":
        target.chmod(0o755)


def _init_repo(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "rvgen test")
    (tmp_path / "a.txt").write_text("1", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "init")


def test_post_commit_creates_git_event(tmp_path: Path):
    assert _sh()
    _init_repo(tmp_path)
    _install(tmp_path, "post-commit")

    (tmp_path / "a.txt").write_text("2", encoding="utf-8")
    _git(tmp_path, "commit", "-qam", "second")

    assert (tmp_path / ".rvgen" / ".git-event").exists()


def test_post_checkout_creates_git_event_only_on_branch_switch(tmp_path: Path):
    assert _sh()
    _init_repo(tmp_path)
    _install(tmp_path, "post-checkout")

    _git(tmp_path, "checkout", "-q", "-b", "feature")
    event = tmp_path / ".rvgen" / ".git-event"
    assert event.exists()

    event.unlink()
    _git(tmp_path, "checkout", "-q", "--", "a.txt")  # 文件 checkout，不是分支切换
    assert not event.exists()
