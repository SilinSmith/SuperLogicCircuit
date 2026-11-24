from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "mutation_score.py"


def _module():
    spec = importlib.util.spec_from_file_location("mutation_score", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mutation_score_math():
    module = _module()
    assert module.mutation_score({"killed": 8, "survived": 2}) == pytest.approx(80.0)
    assert module.mutation_score({"killed": 0, "survived": 0}) == 100.0
    assert module.mutation_score({"killed": 3, "survived": 1, "timeout": 1, "suspicious": 1}) == 50.0


def test_cli_gate(tmp_path: Path, capsys):
    module = _module()
    stats = tmp_path / "stats.json"
    stats.write_text(json.dumps({"killed": 9, "survived": 1}), encoding="utf-8")
    assert module.main(["--stats", str(stats), "--min", "80"]) == 0
    assert "90.0%" in capsys.readouterr().out
    assert module.main(["--stats", str(stats), "--min", "95"]) == 1
    assert module.main(["--stats", str(tmp_path / "missing.json")]) == 1
