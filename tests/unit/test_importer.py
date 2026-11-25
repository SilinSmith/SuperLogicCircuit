"""P1 importer：ANSI/非 ANSI 模块头、参数、`ifdef 跳过与 W14。"""

from __future__ import annotations

from slc.importer import import_verilog


def codes(diagnostics) -> list[str]:
    return [item.code for item in diagnostics]


def test_ansi_module_with_params_and_ports() -> None:
    source = """
    module uart #(
        parameter int WIDTH = 8,
        parameter DEPTH = 16
    ) (
        input  wire             clk,
        input  wire             rst_n,
        input  wire [WIDTH-1:0] din,
        output reg  [7:0]       dout,
        output                  valid
    );
    endmodule
    """
    skeleton, diagnostics = import_verilog(source, source_name="uart.v")
    assert skeleton is not None
    module = skeleton["modules"][0]
    assert module["name"] == "uart"
    assert module["params"] == [
        {"name": "WIDTH", "default": 8},
        {"name": "DEPTH", "default": 16},
    ]
    ports = {port["name"]: port for port in module["ports"]}
    assert ports["clk"]["dir"] == "input"
    assert ports["din"].get("width") == "WIDTH"  # [WIDTH-1:0] 归一为参数表达式
    assert ports["dout"]["width"] == 8
    assert ports["valid"]["dir"] == "output"
    assert "W14" in codes(diagnostics)


def test_non_ansi_style_ports_are_read_from_body() -> None:
    source = """
    module legacy (a, b, c);
      input a;
      input [3:0] b;
      output c;
    endmodule
    """
    skeleton, diagnostics = import_verilog(source)
    assert skeleton is not None
    ports = {port["name"]: port for port in skeleton["modules"][0]["ports"]}
    assert ports["a"] == {"name": "a", "dir": "input"}
    assert ports["b"]["width"] == 4
    assert ports["c"]["dir"] == "output"
    assert "W14" in codes(diagnostics)


def test_ifdef_wrapped_ports_are_skipped_with_I05() -> None:
    source = """
    module conditional (
      input a,
    `ifdef WIDE
      input [7:0] b,
    `endif
      output c
    );
    endmodule
    """
    skeleton, diagnostics = import_verilog(source)
    assert skeleton is not None
    names = {port["name"] for port in skeleton["modules"][0]["ports"]}
    assert names == {"a", "c"}
    assert "I05" in codes(diagnostics)


def test_missing_header_is_E09() -> None:
    skeleton, diagnostics = import_verilog("assign a = b;")
    assert skeleton is None
    assert diagnostics[0].code == "E09"


def test_module_without_ports() -> None:
    skeleton, diagnostics = import_verilog("module top;\nendmodule\n")
    assert skeleton is not None
    assert skeleton["modules"][0]["ports"] == []
    assert "W14" in codes(diagnostics)


def test_uppercase_module_name_gets_legal_project_name() -> None:
    skeleton, _ = import_verilog("module MyCore (input clk);\nendmodule\n")
    assert skeleton is not None
    assert skeleton["project"]["name"] == "mycore"
    assert skeleton["modules"][0]["name"] == "MyCore"


def test_unresolved_non_ansi_name_is_reported_in_W14() -> None:
    skeleton, diagnostics = import_verilog("module m (a, b);\ninput a;\nendmodule\n")
    assert skeleton is not None
    message = next(item.message for item in diagnostics if item.code == "W14")
    assert "b" in message
