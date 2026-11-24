import type { NodeGraph } from "../../contracts/node_graph";

export interface SeriesDatum {
  label: string;
  value: number;
}

export interface TraceSummary {
  schema_version: "1.0.0";
  trace: string;
  flavor: string;
  cycles: number;
  timescale_ns: number;
  nodes: { id: string; active_cycles: number; util: number }[];
  edges: {
    id: string;
    bytes: number;
    bits_per_cycle: number;
    gbps: number | null;
    toggles: number;
    toggle_rate: number | null;
    utilization: number | null;
  }[];
  warnings: string[];
}

export function parseTraceSummary(raw: unknown): TraceSummary {
  if (typeof raw !== "object" || raw === null) throw new Error("trace_summary 必须是对象");
  const summary = raw as Partial<TraceSummary>;
  if (summary.schema_version !== "1.0.0") throw new Error("trace_summary schema_version 不支持");
  if (!Array.isArray(summary.nodes) || !Array.isArray(summary.edges)) {
    throw new Error("trace_summary 缺少 nodes/edges");
  }
  return summary as TraceSummary;
}

export function nodeTypeSeries(graph: NodeGraph): SeriesDatum[] {
  const counts = new Map<string, number>();
  for (const node of graph.nodes) {
    const key = node.type.startsWith("p_") ? node.type : node.type.replace("_node", "");
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()].map(([label, value]) => ({ label, value }));
}

export function edgeKindSeries(graph: NodeGraph): SeriesDatum[] {
  const counts = new Map<string, number>();
  for (const edge of graph.edges) {
    counts.set(edge.kind, (counts.get(edge.kind) ?? 0) + 1);
  }
  return [...counts.entries()].map(([label, value]) => ({ label, value }));
}

export function bandwidthSeries(graph: NodeGraph): SeriesDatum[] {
  return graph.edges
    .filter((edge) => typeof edge.width_bits === "number" && edge.kind !== "clock")
    .map((edge) => ({
      label: edge.id.length > 26 ? `${edge.id.slice(0, 24)}…` : edge.id,
      value: edge.width_bits ?? 0,
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 12);
}

export function utilizationSeries(summary: TraceSummary | null | undefined): SeriesDatum[] {
  if (!summary) return [];
  return summary.nodes
    .filter((node) => node.util > 0)
    .map((node) => ({ label: node.id, value: Number((node.util * 100).toFixed(2)) }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 12);
}
