import { describe, expect, it } from "vitest";
import type { NodeGraph } from "../../contracts/node_graph";
import { sampleGraph } from "../test/fixtures";
import { availablePluginViews } from "./registry";

const cpuGraph: NodeGraph = {
  ...sampleGraph,
  nodes: [
    ...sampleGraph.nodes,
    {
      id: "mod:cpu_fetch",
      type: "module_node",
      label: "cpu_fetch",
      "x-cpu-stage": "IF",
      "x-cpu-stage_index": 0,
    },
    {
      id: "p_cpu:icache",
      type: "p_cpu:cache_node",
      label: "icache",
      "x-cpu-ways": 2,
      "x-cpu-sets": 256,
    },
  ],
};

describe("plugin 视图注册", () => {
  it("通用图不出现 CPU 视图", () => {
    expect(availablePluginViews(sampleGraph)).toHaveLength(0);
  });

  it("存在 x-cpu-stage 或 p_cpu 节点时注册流水线与 Cache", () => {
    expect(availablePluginViews(cpuGraph).map((view) => view.id)).toEqual([
      "cpu-pipeline",
      "cpu-cache",
    ]);
  });
});
