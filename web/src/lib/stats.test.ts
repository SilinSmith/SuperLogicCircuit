import { describe, expect, it } from "vitest";
import { sampleGraph } from "../test/fixtures";
import {
  bandwidthSeries,
  edgeKindSeries,
  nodeTypeSeries,
  parseTraceSummary,
  utilizationSeries,
} from "./stats";

const summaryRaw = {
  schema_version: "1.0.0",
  trace: "run.jsonl",
  flavor: "core",
  cycles: 10,
  timescale_ns: 1,
  nodes: [
    { id: "mod:uart", active_cycles: 6, util: 0.6 },
    { id: "mod:fifo", active_cycles: 9, util: 0.9 },
  ],
  edges: [],
  warnings: [],
};

describe("统计聚合", () => {
  it("节点/边类型计数", () => {
    expect(nodeTypeSeries(sampleGraph)).toEqual(
      expect.arrayContaining([
        { label: "module", value: 2 },
        { label: "clock", value: 1 },
      ]),
    );
    expect(edgeKindSeries(sampleGraph)).toEqual(
      expect.arrayContaining([
        { label: "data", value: 1 },
        { label: "clock", value: 1 },
      ]),
    );
  });

  it("带宽序列排除时钟边", () => {
    const series = bandwidthSeries(sampleGraph);
    expect(series).toHaveLength(1);
    expect(series[0].value).toBe(8);
  });

  it("利用率按百分比降序，无 summary 时为空", () => {
    expect(utilizationSeries(null)).toEqual([]);
    const series = utilizationSeries(parseTraceSummary(summaryRaw));
    expect(series[0]).toEqual({ label: "mod:fifo", value: 90 });
  });

  it("拒绝不支持的 summary 版本", () => {
    expect(() => parseTraceSummary({ ...summaryRaw, schema_version: "2.0.0" })).toThrow();
  });
});
