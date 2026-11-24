"""P1 黄金文件框架：目前只覆盖 node_graph（top.v/trace 属 P2/P4）。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from rvgen.cli import main
from rvgen.diag import DiagnosticSink
from rvgen.graph import build
from rvgen.loader import load

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "golden" / "uart" / "rvgen.yaml"
GOLDEN_DIR = ROOT / "golden"


def _render(graph) -> str:
    return json.dumps(graph.document, ensure_ascii=False, indent=2) + "\n"


def test_node_graph_matches_golden(pytestconfig) -> None:
    model, diagnostics = load(FIXTURE)
    assert model is not None, [item.message for item in diagnostics]
    assert not [item for item in diagnostics if item.severity == "E"]
    sink = DiagnosticSink()
    graph = build(model, sink)
    assert not sink.has_errors(), [item.message for item in sink.items if item.severity == "E"]
    golden = GOLDEN_DIR / "node_graph.json"
    text = _render(graph)
    if pytestconfig.getoption("--update-golden"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(text, encoding="utf-8", newline="\n")
    assert golden.exists(), "运行 pytest --update-golden 生成黄金文件"
    assert text == golden.read_text(encoding="utf-8")


def test_cli_graph_write_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    shutil.copy(FIXTURE, project / "rvgen.yaml")
    monkeypatch.chdir(project)

    assert main(["graph", "--write"]) == 0
    first = (project / "node_graph.json").read_bytes()
    assert main(["graph", "--write"]) == 0
    second = (project / "node_graph.json").read_bytes()
    assert first == second
    assert first.endswith(b"\n")
    golden = (GOLDEN_DIR / "node_graph.json").read_bytes()
    assert first == golden
