"""init / import / gen cdc / gen fuse-soc 的 CLI 接线。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import yaml

from slc.cli import main


def _iverilog() -> str | None:
    return shutil.which("iverilog")


def test_init_minimal_generates_compilable_project(tmp_path, monkeypatch, capsys) -> None:
    project = tmp_path / "demo"
    assert main(["init", str(project), "--preset", "minimal"]) == 0
    assert "initialized" in capsys.readouterr().out
    assert (project / "slc.yaml").exists()
    assert (project / "node_graph.json").exists()
    assert (project / "rtl" / "core.v").exists()
    assert (project / "rtl" / "top.v").exists()

    monkeypatch.chdir(project)
    assert main(["check", "--strict"]) == 0
    assert main(["sync", "--check"]) == 0

    compiler = _iverilog()
    if compiler:
        result = subprocess.run(
            [compiler, "-g2005", "-o", str(tmp_path / "demo.out"), "-s", "top", "rtl/core.v", "rtl/top.v"],
            cwd=project,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


def test_init_refuses_existing_declaration(tmp_path, monkeypatch, capsys) -> None:
    project = tmp_path / "demo"
    assert main(["init", str(project)]) == 0
    capsys.readouterr()
    assert main(["init", str(project)]) == 1
    assert "E00" in capsys.readouterr().err


def test_init_rv32i_passes_strict(tmp_path, monkeypatch) -> None:
    project = tmp_path / "rv32i"
    assert main(["init", str(project), "--preset", "rv32i"]) == 0
    monkeypatch.chdir(project)
    assert main(["check", "--strict"]) == 0


def test_import_writes_skeleton(tmp_path, monkeypatch, capsys) -> None:
    verilog = tmp_path / "blk.v"
    verilog.write_text(
        "module blk #(parameter WIDTH = 8) (input wire clk, input wire [WIDTH-1:0] din, output wire dout);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    out = tmp_path / "slc.yaml"
    assert main(["import", str(verilog), "-o", str(out)]) == 0
    assert "W14" in capsys.readouterr().err
    document = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert document["project"]["name"] == "blk"
    din = next(port for port in document["modules"][0]["ports"] if port["name"] == "din")
    assert din["width"] == "WIDTH"


def test_gen_cdc_writes_five_modules(tmp_path, capsys) -> None:
    out = tmp_path / "cdc"
    assert main(["gen", "cdc", "--out", str(out)]) == 0
    capsys.readouterr()
    names = sorted(path.name for path in out.glob("*.v"))
    assert names == ["async_fifo.v", "gray_bus.v", "handshake.v", "pulse_sync.v", "two_ff.v"]
    assert "module two_ff" in (out / "two_ff.v").read_text(encoding="utf-8")


def test_gen_fuse_soc_writes_core(tmp_path, monkeypatch, capsys) -> None:
    project = tmp_path / "demo"
    assert main(["init", str(project), "--preset", "uart"]) == 0
    capsys.readouterr()
    monkeypatch.chdir(project)
    assert main(["gen", "fuse-soc", "--out", "build"]) == 0
    core = project / "build" / "uart_example.core"
    document = yaml.safe_load(core.read_text(encoding="utf-8"))
    assert document["CAPI=2"] == 2
    assert document["name"] == "slc:ip:uart_example:1.0.0"
    assert "rtl/uart.v" in document["filesets"]["rtl"]["files"]
    assert document["parameters"]["WIDTH"]["default"] == 8
    assert document["targets"]["default"] == {"filesets": ["rtl"]}
