"""`slc init` 的内置样例（只依赖核心 schema 与插件配置）。"""

from __future__ import annotations

from typing import Final

MINIMAL: Final[str] = """\
schema_version: '1.1.0'
project:
  name: demo_core
  top: top
  default_clock: clk
  reset: {name: rst_n, polarity: active_low, sync: true, levels: 2}
clocks:
  - {name: clk, freq_hz: 50000000, domain_id: sys, source: pad}
modules:
  - name: core
    kind: module
    clock: clk
    ports:
      - {name: clk, dir: input, kind: clock}
      - {name: rst_n, dir: input, kind: reset}
      - {name: din, dir: input, width: 8}
      - {name: dout, dir: output, width: 8}
top:
  ports:
    - {name: clk, dir: input, role: clock}
    - {name: rst_n, dir: input, role: reset, polarity: active_low}
    - {name: din, dir: input, to: [core.din]}
    - {name: dout, dir: output, from: core.dout}
"""

UART: Final[str] = """\
schema_version: '1.1.0'
project:
  name: uart_example
  top: top
  default_clock: clk
  reset: {name: rst_n, polarity: active_low, sync: true, levels: 2}
clocks:
  - {name: clk, freq_hz: 50000000, domain_id: sys, source: pad}
modules:
  - name: uart
    kind: module
    clock: clk
    params:
      - {name: WIDTH, default: 8}
    ports:
      - {name: clk, dir: input, kind: clock}
      - {name: cfg, dir: input, width: WIDTH}
      - {name: rxd, dir: input, width: 1}
      - {name: tx, dir: output, width: 1}
  - name: fifo
    kind: memory
    clock: clk
    ports:
      - {name: clk, dir: input, kind: clock}
      - {name: push, dir: input, width: 8}
      - {name: pop, dir: output, width: 8}
  - name: baud_gen
    kind: clock_gen
    clock: clk
    ports:
      - {name: clk, dir: input, kind: clock}
      - {name: tick, dir: output, width: 1}
top:
  ports:
    - {name: clk, dir: input, role: clock}
    - {name: cfg, dir: input, to: [uart.cfg]}
    - {name: rxd, dir: input, to: [uart.rxd]}
    - {name: push, dir: input, to: [fifo.push]}
    - {name: tx, dir: output, from: uart.tx}
    - {name: pop, dir: output, from: fifo.pop}
    - {name: baud_tick, dir: output, from: baud_gen.tick}
"""

RV32I: Final[str] = """\
schema_version: '1.1.0'
project:
  name: rv32i_demo
  top: top
  default_clock: clk
  reset: {name: rst_n, polarity: active_low, sync: true, levels: 2}
clocks:
  - {name: clk, freq_hz: 50000000, domain_id: sys, source: pad}
plugins:
  cpu:
    enabled: true
    lanes: [IF, ID, EX, MEM, WB]
modules:
  - name: if_stage
    kind: module
    clock: clk
    x-cpu-stage: IF
    x-cpu-stage_index: 0
    ports:
      - {name: clk, dir: input, kind: clock}
      - {name: rst_n, dir: input, kind: reset}
      - {name: din, dir: input, width: 32}
      - {name: dout, dir: output, width: 32}
  - name: id_stage
    kind: module
    clock: clk
    x-cpu-stage: ID
    x-cpu-stage_index: 1
    ports:
      - {name: clk, dir: input, kind: clock}
      - {name: rst_n, dir: input, kind: reset}
      - {name: din, dir: input, width: 32, connect: if_stage.dout}
      - {name: dout, dir: output, width: 32}
  - name: ex_stage
    kind: module
    clock: clk
    x-cpu-stage: EX
    x-cpu-stage_index: 2
    ports:
      - {name: clk, dir: input, kind: clock}
      - {name: rst_n, dir: input, kind: reset}
      - {name: din, dir: input, width: 32, connect: id_stage.dout}
      - {name: dout, dir: output, width: 32}
  - name: mem_stage
    kind: module
    clock: clk
    x-cpu-stage: MEM
    x-cpu-stage_index: 3
    ports:
      - {name: clk, dir: input, kind: clock}
      - {name: rst_n, dir: input, kind: reset}
      - {name: din, dir: input, width: 32, connect: ex_stage.dout}
      - {name: dout, dir: output, width: 32}
  - name: wb_stage
    kind: module
    clock: clk
    x-cpu-stage: WB
    x-cpu-stage_index: 4
    ports:
      - {name: clk, dir: input, kind: clock}
      - {name: rst_n, dir: input, kind: reset}
      - {name: din, dir: input, width: 32, connect: mem_stage.dout}
      - {name: dout, dir: output, width: 32}
  - name: icache
    kind: memory
    clock: clk
    x-cpu-ways: 2
    x-cpu-sets: 256
    ports:
      - {name: clk, dir: input, kind: clock}
      - {name: rst_n, dir: input, kind: reset}
      - {name: req, dir: input, width: 32, default: "'0"}
      - {name: ready, dir: output, width: 1}
  - name: dcache
    kind: memory
    clock: clk
    x-cpu-ways: 2
    x-cpu-sets: 256
    ports:
      - {name: clk, dir: input, kind: clock}
      - {name: rst_n, dir: input, kind: reset}
      - {name: req, dir: input, width: 32, default: "'0"}
      - {name: ready, dir: output, width: 1}
top:
  ports:
    - {name: clk, dir: input, role: clock}
    - {name: rst_n, dir: input, role: reset, polarity: active_low}
    - {name: instr, dir: input, to: [if_stage.din]}
    - {name: result, dir: output, from: wb_stage.dout}
    - {name: icache_ready, dir: output, from: icache.ready}
    - {name: dcache_ready, dir: output, from: dcache.ready}
"""

PRESETS: Final[dict[str, str]] = {"minimal": MINIMAL, "uart": UART, "rv32i": RV32I}
