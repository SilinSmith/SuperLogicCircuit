from __future__ import annotations

import os

import pytest

from slc.atomic import AtomicWriteError, atomic_write
from slc.diag import DiagnosticSink


def test_atomic_write_str_and_bytes(tmp_path) -> None:
    target = tmp_path / "rtl" / "uart.v"
    atomic_write(target, "module uart;\nendmodule\n")
    assert target.read_text(encoding="utf-8") == "module uart;\nendmodule\n"

    atomic_write(target, b"module uart2;\nendmodule\n")
    assert target.read_bytes() == b"module uart2;\nendmodule\n"


def test_atomic_write_backs_up_existing(tmp_path) -> None:
    target = tmp_path / "top.v"
    target.write_text("old\n", encoding="utf-8")
    bak_dir = tmp_path / "bak"
    sink = DiagnosticSink()

    atomic_write(target, "new\n", bak_dir=bak_dir, sink=sink)

    assert target.read_text(encoding="utf-8") == "new\n"
    backups = list(bak_dir.iterdir())
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "old\n"
    if os.name == "nt":
        assert any(item.code == "I01" for item in sink.items)


def test_atomic_write_failure_keeps_tmp(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("slc.atomic.time.sleep", lambda _seconds: None)
    target = tmp_path / "blocked.v"
    target.mkdir()

    with pytest.raises(AtomicWriteError) as caught:
        atomic_write(target, "data\n", retries=1)

    assert caught.value.code == "E12"
    assert caught.value.tmp_path.exists()
    assert caught.value.path == target.resolve()
