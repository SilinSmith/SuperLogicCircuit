from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

from slc.cli import main

REPO_ROOT = Path(__file__).resolve().parents[2]
VALID = REPO_ROOT / "tests" / "fixtures" / "schema" / "valid"


def _valid_project(tmp_path: Path, *, graph: bool = True, layout: bool = True) -> Path:
    shutil.copy(VALID / "slc.yaml", tmp_path / "slc.yaml")
    if graph:
        shutil.copy(VALID / "node_graph.json", tmp_path / "node_graph.json")
    if layout:
        shutil.copy(VALID / "layout.json", tmp_path / "layout.json")
    return tmp_path


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_check_valid_project_returns_zero(tmp_path, monkeypatch, capsys) -> None:
    _valid_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main(["check"]) == 0
    captured = capsys.readouterr()
    assert "E09" not in captured.err


def test_check_reports_E09_with_json_path(tmp_path, monkeypatch, capsys) -> None:
    _valid_project(tmp_path, graph=False, layout=False)
    data = yaml.safe_load((tmp_path / "slc.yaml").read_text(encoding="utf-8"))
    data["modules"][0]["stage"] = "IF"
    _write_yaml(tmp_path / "slc.yaml", data)
    monkeypatch.chdir(tmp_path)

    assert main(["check"]) == 1
    err = capsys.readouterr().err
    assert "E09" in err
    assert "modules.uart.stage" in err


def test_check_json_format_goes_to_stdout(tmp_path, monkeypatch, capsys) -> None:
    _valid_project(tmp_path, graph=False, layout=False)
    data = yaml.safe_load((tmp_path / "slc.yaml").read_text(encoding="utf-8"))
    data["modules"][0]["stage"] = "IF"
    _write_yaml(tmp_path / "slc.yaml", data)
    monkeypatch.chdir(tmp_path)

    assert main(["check", "--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    diagnostic = payload["diagnostics"][0]
    assert diagnostic["code"] == "E09"
    assert "modules.uart" in diagnostic["location"]["json_path"]


def test_check_strict_turns_version_warning_into_exit_2(tmp_path, monkeypatch) -> None:
    _valid_project(tmp_path)
    graph_path = tmp_path / "node_graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["generated_by"] = "slc 9.9.9"
    graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["check"]) == 0
    assert main(["check", "--strict"]) == 2


def test_check_contract_self_lint_at_repo_root(monkeypatch) -> None:
    monkeypatch.chdir(REPO_ROOT)
    assert main(["check"]) == 0


def test_check_missing_project_returns_E00(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["check"]) == 1
    err = capsys.readouterr().err
    assert "E00" in err
    assert "未找到" in err


def test_check_does_not_write_files(tmp_path, monkeypatch) -> None:
    _valid_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}
    assert main(["check"]) == 0
    after = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}
    assert before == after


def test_check_semantic_diff_and_fix(tmp_path, monkeypatch, capsys) -> None:
    _valid_project(tmp_path)
    graph_path = tmp_path / "node_graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    uart = next(node for node in graph["nodes"] if node["id"] == "mod:uart")
    cfg = next(port for port in uart["ports"] if port["name"] == "cfg")
    cfg["width_bits"] = 99
    graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["check"]) == 1
    err = capsys.readouterr().err
    assert "E16" in err
    assert "nodes.mod:uart.ports.cfg.width_bits" in err

    assert main(["check", "--fix"]) == 0
    assert main(["check"]) == 0
    fixed = json.loads(graph_path.read_text(encoding="utf-8"))
    uart_fixed = next(node for node in fixed["nodes"] if node["id"] == "mod:uart")
    cfg_fixed = next(port for port in uart_fixed["ports"] if port["name"] == "cfg")
    assert cfg_fixed["width_bits"] == 8


def test_check_invalid_node_graph_json(tmp_path, monkeypatch, capsys) -> None:
    _valid_project(tmp_path)
    (tmp_path / "node_graph.json").write_text("{not json", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["check"]) == 1
    err = capsys.readouterr().err
    assert "E09" in err
    assert "node_graph.json" in err


def test_check_invalid_layout_json(tmp_path, monkeypatch, capsys) -> None:
    _valid_project(tmp_path)
    layout_path = tmp_path / "layout.json"
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    layout["views"]["dataflow"]["viewport"]["zoom"] = 0
    layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["check"]) == 1
    assert "E09" in capsys.readouterr().err


def test_check_without_node_graph_is_allowed(tmp_path, monkeypatch) -> None:
    _valid_project(tmp_path, graph=False)
    monkeypatch.chdir(tmp_path)
    assert main(["check"]) == 0


def test_sync_check_is_clean_after_sync(tmp_path, monkeypatch) -> None:
    _valid_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main(["sync"]) == 0
    assert main(["sync", "--check"]) == 0


def test_sync_check_detects_stale_outputs(tmp_path, monkeypatch, capsys) -> None:
    _valid_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main(["sync", "--check"]) == 1
    err = capsys.readouterr().err
    assert "E15" in err
    assert "生成物落后" in err
