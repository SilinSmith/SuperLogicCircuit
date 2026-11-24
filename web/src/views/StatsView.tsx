import { useMemo } from "react";
import type { NodeGraph } from "../../contracts/node_graph";
import { EChart } from "../components/EChart";
import {
  bandwidthSeries,
  edgeKindSeries,
  nodeTypeSeries,
  utilizationSeries,
  type TraceSummary,
} from "../lib/stats";

function barOption(title: string, data: { label: string; value: number }[]) {
  return {
    backgroundColor: "transparent",
    title: { text: title, textStyle: { color: "#e6ecf5", fontSize: 13 } },
    tooltip: { trigger: "axis" },
    grid: { left: 48, right: 20, top: 48, bottom: 56 },
    xAxis: {
      type: "category",
      data: data.map((item) => item.label),
      axisLabel: { color: "#93a1b8", fontSize: 10, interval: 0, rotate: 24 },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: "#93a1b8", fontSize: 10 },
      splitLine: { lineStyle: { color: "#2b3750" } },
    },
    series: [
      {
        type: "bar",
        data: data.map((item) => item.value),
        itemStyle: { color: "#4f8cff" },
      },
    ],
  };
}

export interface StatsViewProps {
  graph: NodeGraph;
  summary: TraceSummary | null;
  summaryError?: string | null;
}

export function StatsView({ graph, summary, summaryError }: StatsViewProps) {
  const utilization = useMemo(() => utilizationSeries(summary), [summary]);
  const bandwidth = useMemo(() => bandwidthSeries(graph), [graph]);
  const edges = useMemo(() => edgeKindSeries(graph), [graph]);
  const staticNodes = useMemo(() => nodeTypeSeries(graph), [graph]);

  return (
    <div className="stats-view" data-testid="stats-view">
      <section className="stats-view__chart">
        <EChart
          label="带宽 bits/cycle"
          testId="chart-bandwidth"
          option={barOption("边带宽（bit/cycle，权威口径）", bandwidth)}
        />
      </section>
      <section className="stats-view__chart">
        <EChart
          label={summary ? "节点利用率" : "节点类型分布"}
          testId="chart-nodes"
          option={
            summary
              ? barOption("节点利用率（%，来自 trace_summary）", utilization)
              : barOption("节点类型分布（静态）", staticNodes)
          }
        />
      </section>
      <section className="stats-view__chart">
        <EChart label="边类型分布" testId="chart-edges" option={barOption("边类型分布", edges)} />
      </section>
      <p className="stats-view__hint">
        {summary
          ? `trace_summary：${summary.cycles} cycles，warnings=${summary.warnings.join(",") || "无"}`
          : summaryError
            ? `trace_summary 读取失败：${summaryError}`
            : "未提供 trace_summary.json，节点图表退化为静态分布；运行 rvgen trace summary 后刷新。"}
      </p>
    </div>
  );
}
