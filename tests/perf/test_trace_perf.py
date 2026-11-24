"""100 万行 trace 归一化性能校准（默认跳过；RVGEN_PERF=1 时运行）。"""

from __future__ import annotations

import os
import time

import pytest

from rvgen.diag import DiagnosticSink
from rvgen.trace import normalize

pytestmark = pytest.mark.skipif(os.environ.get("RVGEN_PERF") != "1", reason="RVGEN_PERF=1 才跑性能校准")

ROWS = 1_000_000


def test_normalize_one_million_rows_under_25s(tmp_path):
    src = tmp_path / "big.tsv"
    row = "10\t{cycle}\t0x{loc:08x}\tEXEC\tid=1\tarc=mod:a.out->mod:b.in:1\n"
    with src.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("#rvgen-meta\tschema=core\ttimescale=ns\n")
        chunk = []
        for cycle in range(ROWS):
            chunk.append(row.format(cycle=cycle, loc=cycle))
            if len(chunk) >= 10_000:
                handle.write("".join(chunk))
                chunk.clear()
        handle.write("".join(chunk))

    sink = DiagnosticSink()
    started = time.perf_counter()
    result = normalize(src, tmp_path / "big.jsonl", "core", sink=sink)
    elapsed = time.perf_counter() - started
    assert not sink.has_errors()
    assert result.rows == ROWS
    assert elapsed < 25.0, f"归一化耗时 {elapsed:.2f}s 超过 25s"
    sys_out = f"rows={result.rows} elapsed={elapsed:.2f}s size={(tmp_path / 'big.jsonl').stat().st_size / 1e6:.1f}MB"
    print(sys_out)
