from __future__ import annotations

import subprocess
from pathlib import Path

from slc.gitw import count_statuses, parse_porcelain_z, read_git_state


def test_parse_porcelain_z_rename_skips_original_path():
    raw = "R  b.txt\0a.txt\0A  dir/c d.txt\0?? new.txt\0UU merged.txt\0"
    assert parse_porcelain_z(raw) == [
        ("R ", "b.txt"),
        ("A ", "dir/c d.txt"),
        ("??", "new.txt"),
        ("UU", "merged.txt"),
    ]


def test_count_statuses_maps_rename_to_modified():
    entries = [("R ", "b.txt"), ("A ", "c"), ("D ", "d"), ("UU", "e"), ("??", "f"), (" M", "g")]
    counts = count_statuses(entries)
    assert counts == {"M": 2, "A": 1, "D": 1, "UU": 1, "??": 1}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, timeout=20)


def test_read_git_state_tracks_branch_and_counts(tmp_path: Path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "slc test")
    (tmp_path / "a.txt").write_text("1", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "init")

    clean = read_git_state(tmp_path)
    assert clean is not None
    assert clean.dirty is False
    assert clean.counts["M"] == 0

    (tmp_path / "a.txt").write_text("2", encoding="utf-8")
    (tmp_path / "b.txt").write_text("new", encoding="utf-8")
    dirty = read_git_state(tmp_path)
    assert dirty is not None
    assert dirty.dirty is True
    assert dirty.counts["M"] == 1
    assert dirty.counts["??"] == 1


def test_read_git_state_returns_none_outside_repo(tmp_path: Path):
    assert read_git_state(tmp_path) is None
