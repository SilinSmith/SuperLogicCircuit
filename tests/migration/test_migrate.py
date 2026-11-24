from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from rvgen.cli import main
from rvgen.migrate import MigrationError, migrate_document, migrate_file

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "v1.0.0.yaml"


def _load() -> dict:
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def test_migrate_document_moves_legacy_fields():
    migrated, steps = migrate_document(_load())
    assert [(step.source, step.target) for step in steps] == [("1.0.0", "1.1.0")]
    assert "profiles" not in migrated
    module = migrated["modules"][0]
    assert "stage" not in module and "stage_index" not in module
    assert module["x-cpu-stage"] == "EX"
    assert module["x-cpu-stage_index"] == 2
    assert module["ports"][1]["kind"] == "handshake"
    assert migrated["schema_version"] == "1.1.0"


def test_migrate_document_is_idempotent():
    migrated, _ = migrate_document(_load())
    again, steps = migrate_document(migrated)
    assert steps == []
    assert again == migrated


def test_migrate_document_rejects_unknown_start():
    with pytest.raises(MigrationError, match="没有从"):
        migrate_document({"schema_version": "0.9.0"})


def test_dry_run_writes_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "rvgen.yaml"
    shutil.copy2(FIXTURE, target)
    original = target.read_text(encoding="utf-8")

    result = migrate_file(target, dry_run=True)

    assert result.written is False
    assert result.snapshot is None
    assert target.read_text(encoding="utf-8") == original
    assert not (tmp_path / ".rvgen").exists()
    assert {"op": "remove", "path": "/profiles"} in result.patch
    module_ops = [op for op in result.patch if op["path"] == "/modules"]
    assert module_ops and module_ops[0]["value"][0]["x-cpu-stage"] == "EX"
    assert module_ops[0]["value"][0]["ports"][1]["kind"] == "handshake"
    json.dumps(result.patch)


def test_migrate_file_snapshots_then_writes(tmp_path: Path):
    target = tmp_path / "rvgen.yaml"
    shutil.copy2(FIXTURE, target)
    original = target.read_text(encoding="utf-8")

    result = migrate_file(target)

    assert result.written is True
    assert result.snapshot is not None
    assert result.snapshot.read_text(encoding="utf-8") == original
    migrated = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert migrated["schema_version"] == "1.1.0"
    assert migrated["modules"][0]["x-cpu-stage"] == "EX"


def test_cli_migrate_writes_and_reports(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    shutil.copy2(FIXTURE, tmp_path / "rvgen.yaml")
    assert main(["migrate"]) == 0
    output = capsys.readouterr().out
    assert "1.0.0 → 1.1.0" in output
    assert "snapshot:" in output


def test_cli_migrate_missing_file_returns_3(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["migrate"]) == 3
