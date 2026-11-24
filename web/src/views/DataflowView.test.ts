import { describe, expect, it } from "vitest";
import { sampleGraph } from "../test/fixtures";
import { buildFlowElements, dataflowSubset } from "./DataflowView";

describe("数据流视图子集", () => {
  it("排除时钟节点与时钟边，只留模块与数据边", () => {
    const subset = dataflowSubset(sampleGraph);
    expect(subset.nodes.map((node) => node.id)).toEqual(["mod:fifo", "mod:uart"]);
    expect(subset.edges.map((edge) => edge.id)).toEqual(["mod:fifo.pop->mod:uart.cfg"]);
  });

  it("为每个可见节点算出 dagre 坐标，且边两端都在子集内", () => {
    const { nodes, edges } = buildFlowElements(sampleGraph);
    expect(nodes).toHaveLength(2);
    const ids = new Set(nodes.map((node) => node.id));
    expect(edges.every((edge) => ids.has(edge.source) && ids.has(edge.target))).toBe(true);
    for (const node of nodes) {
      expect(Number.isFinite(node.position.x)).toBe(true);
      expect(Number.isFinite(node.position.y)).toBe(true);
    }
  });

  it("trace_summary 的利用率按边 id 挂到边数据上", () => {
    const summary = {
      schema_version: "1.0.0" as const,
      trace: "trace.jsonl",
      flavor: "core",
      cycles: 10,
      timescale_ns: 1,
      nodes: [],
      edges: [
        {
          id: "mod:fifo.pop->mod:uart.cfg",
          bytes: 10,
          bits_per_cycle: 8,
          gbps: 0.05,
          toggles: 10,
          toggle_rate: 0.5,
          utilization: 0.83,
        },
      ],
      warnings: [],
    };
    const { edges } = buildFlowElements(sampleGraph, undefined, summary);
    expect(edges[0]?.data?.utilization).toBe(0.83);
  });
});
