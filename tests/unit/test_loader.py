"""P1 loader：版本兼容、schema 诊断路径、行号与 YAML 异常。"""

from __future__ import annotations

from pathlib import Path

import pytest

from rvgen.diag import DiagnosticSink
from rvgen.loader import load, load_data, load_text


def _yaml(version: str = "1.1.0", module_name: str = "uart") -> str:
    return f"""
schema_version: '{version}'
project:
  name: demo_proj
  top: top
  default_clock: clk
  reset: {{name: rst_n, polarity: active_low, sync: true, levels: 2}}
clocks:
  - name: clk
    freq_hz: 50000000
    domain_id: sys
    source: pad
modules:
  - name: {module_name}
    kind: module
    clock: clk
    ports:
      - {{name: clk, dir: input, kind: clock}}
      - {{name: d, dir: input, width: 8, default: "8'h0"}}
top:
  ports: []
"""


def test_load_text_returns_model_and_line_numbers() -> None:
    model, diagnostics = load_text(_yaml())
    assert diagnostics == []
    assert model is not None
    assert model.modules[0].line is not None
    assert model.clocks[0].line is not None
    assert model.source_name == "rvgen.yaml"


def test_missing_file_sets_io_failure(tmp_path: Path) -> None:
    sink = DiagnosticSink()
    model, diagnostics = load(tmp_path / "nope.yaml", sink=sink)
    assert model is None
    assert sink.io_failure is True
    assert diagnostics[0].code == "E09"


def test_invalid_yaml_and_non_mapping(tmp_path: Path) -> None:
    model, diagnostics = load_text("a: [\n")
    assert model is None
    assert diagnostics[0].code == "E09"

    model, diagnostics = load_text("- 1\n- 2\n")
    assert model is None
    assert "mapping" in diagnostics[0].message


@pytest.mark.parametrize("version", ["", "1.1", "1.1.0.0", "v1.1.0"])
def test_non_semver_is_E09(version: str) -> None:
    model, diagnostics = load_text(_yaml(version))
    assert model is None
    assert "semver" in diagnostics[0].message


def test_major_mismatch_is_refused() -> None:
    model, diagnostics = load_text(_yaml("2.0.0"))
    assert model is None
    assert "主版本" in diagnostics[0].message


@pytest.mark.parametrize("version", ["1.2.0", "1.0.0", "1.1.1"])
def test_minor_patch_loads_with_I02(version: str) -> None:
    model, diagnostics = load_text(_yaml(version))
    assert model is not None
    assert model.schema_version == version
    assert "I02" in [item.code for item in diagnostics]


def test_schema_error_reports_dotted_path() -> None:
    text = _yaml().replace("    kind: module\n", "    kind: module\n    stage: EX\n")
    model, diagnostics = load_text(text)
    assert model is None
    error = next(item for item in diagnostics if item.code == "E09")
    assert error.where.json_path == "modules.uart.stage"
    assert "x-" in (error.hint or "")


def test_missing_required_field_reports_field_name() -> None:
    text = _yaml().replace("project:\n", "project_typo:\n")
    model, diagnostics = load_text(text)
    assert model is None
    assert any("project" in item.message for item in diagnostics if item.code == "E09")


def test_deep_anchor_nesting_is_W10() -> None:
    lines = ["schema_version: '1.1.0'"]
    lines.append("base: &a0 {v: 1}")
    for index in range(1, 12):
        lines.append(f"level{index}: &a{index} {{inner: *a{index - 1}}}")
    model, diagnostics = load_text("\n".join(lines) + "\n")
    assert model is None
    assert "W10" in [item.code for item in diagnostics]


def test_load_data_matches_load_text_semantics() -> None:
    import yaml

    document = yaml.safe_load(_yaml())
    model, diagnostics = load_data(document)
    assert model is not None
    assert diagnostics == []
    assert model.modules[0].line is None
