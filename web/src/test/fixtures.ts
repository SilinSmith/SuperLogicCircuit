import type { GraphEdge, GraphNode, NodeGraph } from "../../contracts/node_graph";

export const uartNode: GraphNode = {
  id: "mod:uart",
  type: "module_node",
  label: "uart",
  module: "uart",
  clock: "clk",
  domain: "sys",
  ports: [
    { name: "clk", dir: "input", width_bits: 1, kind: "clock" },
    { name: "cfg", dir: "input", width_expr: "WIDTH", width_bits: 8, kind: "data" },
    { name: "rxd", dir: "input", width_bits: 1, kind: "data" },
    { name: "tx", dir: "output", width_bits: 1, kind: "data" },
  ],
  loc: { file: "rvgen.yaml", line: 23, end_line: 33 },
};

export const fifoNode: GraphNode = {
  id: "mod:fifo",
  type: "module_node",
  label: "fifo",
  module: "fifo",
  clock: "clk",
  domain: "sys",
  ports: [
    { name: "clk", dir: "input", width_bits: 1, kind: "clock" },
    { name: "push", dir: "input", width_bits: 8, kind: "data" },
    { name: "pop", dir: "output", width_bits: 8, kind: "data" },
  ],
  loc: { file: "rvgen.yaml", line: 33, end_line: 40 },
};

export const clockNode: GraphNode = {
  id: "clk:clk",
  type: "clock_node",
  label: "clk",
  clock: "clk",
  domain: "sys",
  loc: { file: "rvgen.yaml", line: 8, end_line: 12 },
};

export const dataEdge: GraphEdge = {
  id: "mod:fifo.pop->mod:uart.cfg",
  source: "mod:fifo",
  target: "mod:uart",
  source_port: "pop",
  target_port: "cfg",
  kind: "data",
  width_bits: 8,
  bandwidth: { source: "derived", width_bits: 8, clock: "clk", freq_hz: 50_000_000 },
};

export const clockEdge: GraphEdge = {
  id: "clk:clk->mod:uart",
  source: "clk:clk",
  target: "mod:uart",
  kind: "clock",
  width_bits: null,
};

export const sampleGraph: NodeGraph = {
  schema_version: "1.0.0",
  generated_by: "rvgen 1.0.0",
  source_digest: "sha256:0123456789abcdef",
  nodes: [clockNode, fifoNode, uartNode],
  edges: [clockEdge, dataEdge],
};
